"""Construct source loaders: local, GitHub raw, generic HTTP, Google Drive,
and Kaggle datasets.

Follows the return-invalid-not-raise convention of :mod:`app.audit.loader`:
loaders never raise on user-facing failures; they return a
:class:`~app.construct.models.SourceDocument` with ``valid=False`` and
descriptive errors instead.

Security hardening (approved review findings, all applied here):

- **Format gate** — only ``.ipynb``, ``.py``, ``.md``, ``.txt`` are accepted,
  gating local paths, URL path segments, and download-derived filenames.
- **SSRF guard** — every fetch (including each redirect hop) is validated:
  non-http(s) schemes, localhost names, loopback/private/link-local/reserved
  IPs (e.g. ``127.0.0.1:8000``, the app's own server) are refused; redirects
  are capped at 5. Never fetch from external sources to internal hosts.
- **Content-Disposition sanitization** — derived filenames are reduced to a
  plain basename; names with path separators or absolute paths produce
  ``valid=False``.
- **Size caps** — one constant :data:`MAX_DOWNLOAD_BYTES` (25 MB) applies to
  generic HTTP, GitHub raw, Drive, and the Kaggle ZIP (compressed and
  uncompressed). Exceeding it produces ``valid=False``.
- **Retry/backoff** — at most one retry after 1s on 5xx/timeout only; 4xx and
  deterministic failures never retry.
- **ZIP-SLIP** — Kaggle ZIP members with absolute paths or ``..`` segments are
  rejected; only a single plain-basename text member is accepted.
"""

from __future__ import annotations

import io
import ipaddress
import re
import socket
import time
import urllib.parse
import zipfile
import zlib
from pathlib import Path

import httpx

from app.construct.models import SourceDocument

#: Extensions accepted by the format gate (whitelist).
ALLOWED_EXTENSIONS = {".ipynb", ".py", ".md", ".txt"}

#: Single concrete download size cap (finding: one constant everywhere).
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

#: Retry/backoff parameters (finding: 1 retry after 1s on 5xx/timeout only).
RETRY_DELAY = 1.0
MAX_REDIRECTS = 5
FETCH_TIMEOUT = 30.0


class _UnsafeUrlError(httpx.RequestError):
    """Raised by the SSRF guard transport when a request targets a
    non-public host (including redirect hops)."""


class _FetchFailure(Exception):
    """Internal signal for a user-facing fetch failure.

    Attributes:
        retryable: Whether the failure warrants one retry (5xx/timeout
            only). ``False`` for 4xx, size caps, SSRF rejections, and
            redirect caps.
    """

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _lookup_host(host: str) -> list[str]:
    """Resolve a hostname to a list of IP address strings.

    Overridable (monkeypatched by probes) so offline tests never depend on
    real DNS.
    """
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


def _is_non_public(addr: ipaddress._BaseAddress) -> bool:
    """True for addresses the SSRF guard refuses to fetch."""
    return bool(
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_public_url(url: str) -> str | None:
    """SSRF guard: return an error string when ``url`` must not be fetched.

    Rejects non-http(s) schemes, localhost hostnames, and any resolved
    address that is loopback, private, link-local, reserved, multicast, or
    unspecified. Returns ``None`` when the URL is safe to fetch.

    Note: DNS rebinding between validation and connection is a theoretical
    residual risk for this desktop tool; the transport wrapper re-validates
    every hop at request time.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return f"Malformed URL: {url!r}"
    if parsed.scheme not in ("http", "https"):
        return (
            f"Unsupported URL scheme {parsed.scheme!r}; only http(s) allowed"
        )
    host = parsed.hostname
    if not host:
        return f"URL has no host: {url!r}"
    lowered = host.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith(".localhost"):
        return f"Refusing to fetch local hostname {host!r}"
    # Numeric literal address — check without DNS.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        if _is_non_public(addr):
            return f"Refusing to fetch non-public address {addr} ({host})"
        return None
    # Hostname — resolve and check every address.
    try:
        addresses = _lookup_host(host)
    except socket.gaierror:
        return f"Cannot resolve host {host!r}"
    for raw in addresses:
        candidate = ipaddress.ip_address(raw)
        if _is_non_public(candidate):
            return (
                f"Refusing to fetch non-public address {candidate} ({host})"
            )
    return None


def check_extension(filename: str) -> str | None:
    """Return an error string when ``filename`` fails the format gate.

    Only ``.ipynb``, ``.py``, ``.md``, ``.txt`` are accepted; everything else
    (including no extension) is rejected.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return (
            f"Unsupported file extension {ext!r} for {filename!r}; "
            f"allowed extensions: {allowed}"
        )
    return None


def sanitize_filename(name: str) -> str | None:
    """Reduce a download-derived name to a safe plain basename.

    Rejects empty names, absolute paths (leading ``/`` or drive letter),
    path separators anywhere, and the special names ``.``/``..``. Returns
    ``None`` when unsafe; invalid callers must produce ``valid=False``.
    """
    name = (name or "").strip().replace("\\", "/")
    if not name:
        return None
    if name.startswith("/") or re.match(r"^[A-Za-z]:/", name):
        return None
    if "/" in name:
        return None
    if name in (".", ".."):
        return None
    return name


def _parse_content_disposition(value: str) -> str | None:
    """Extract a filename from a Content-Disposition header.

    Honors ``filename*=UTF-8''...`` (RFC 5987, percent-encoded) first, then
    plain ``filename="..."``/``filename=...``. Returns ``None`` when no
    usable filename is present.
    """
    for part in value.split(";"):
        part = part.strip()
        lowered = part.lower()
        if lowered.startswith("filename*="):
            raw = part[len("filename*="):].strip().strip('"')
            if "'" in raw:  # charset'lang'percent-encoded value
                raw = raw.split("'", 2)[-1]
            try:
                return urllib.parse.unquote(raw)
            except (ValueError, UnicodeDecodeError):
                return None
        if lowered.startswith("filename="):
            return part[len("filename="):].strip().strip('"')
    return None


def derive_filename(content_disposition: str | None, url: str) -> str | None:
    """Derive a download filename from Content-Disposition, else the last
    URL path segment. Returns ``None`` when nothing usable is found.
    """
    if content_disposition:
        name = _parse_content_disposition(content_disposition)
        if name:
            return name
    return url.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------------------
# Fetching (SSRF guard + redirect cap + size cap + retry-once)
# ---------------------------------------------------------------------------


class _GuardedTransport(httpx.BaseTransport):
    """Validates the target host of every request, including redirect hops.

    Wraps an inner transport (a real ``httpx.HTTPTransport`` in production,
    a ``httpx.MockTransport`` in probes).
    """

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        error = validate_public_url(str(request.url))
        if error:
            raise _UnsafeUrlError(error, request=request)
        return self._inner.handle_request(request)


def _build_client(transport: httpx.BaseTransport | None) -> httpx.Client:
    inner = transport if transport is not None else httpx.HTTPTransport()
    return httpx.Client(
        transport=_GuardedTransport(inner),
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
    )


def _get_once(
    client: httpx.Client, url: str, max_bytes: int = MAX_DOWNLOAD_BYTES
) -> tuple[bytes, httpx.Headers]:
    """One streamed GET with a size cap. Raises :class:`_FetchFailure` on
    any user-facing failure (status >= 400, size cap, guard rejection,
    timeout, transport error).
    """
    try:
        with client.stream("GET", url) as response:
            if response.status_code >= 500:
                raise _FetchFailure(
                    f"HTTP {response.status_code} fetching {url}",
                    retryable=True,
                )
            if response.status_code >= 400:
                raise _FetchFailure(
                    f"HTTP {response.status_code} fetching {url}",
                    retryable=False,
                )
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise _FetchFailure(
                        f"Response exceeds size limit of {max_bytes} bytes "
                        f"({url})",
                        retryable=False,
                    )
                chunks.append(chunk)
            return b"".join(chunks), response.headers
    except _UnsafeUrlError as exc:
        raise _FetchFailure(
            f"Refusing to fetch non-public host: {url}", retryable=False
        ) from exc
    except httpx.TimeoutException as exc:
        raise _FetchFailure(f"Request timed out fetching {url}", retryable=True) from exc
    except httpx.TooManyRedirects as exc:
        raise _FetchFailure(
            f"Too many redirects fetching {url} (max {MAX_REDIRECTS})",
            retryable=False,
        ) from exc
    except httpx.RequestError as exc:
        raise _FetchFailure(f"Network error fetching {url}: {exc}", retryable=True) from exc


def _get_with_retry(
    url: str,
    transport: httpx.BaseTransport | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> tuple[bytes, httpx.Headers | None, str | None]:
    """SSRF-guarded GET with redirect cap, size cap, and retry-once.

    Retries exactly once after :data:`RETRY_DELAY` seconds on 5xx/timeout
    only; 4xx, size caps, SSRF rejections, and redirect caps never retry.

    Returns:
        ``(content, headers, error)`` — ``error`` is ``None`` on success;
        headers are ``None`` on failure.
    """
    client = _build_client(transport)
    try:
        for attempt in (1, 2):
            try:
                content, headers = _get_once(client, url, max_bytes)
                return content, headers, None
            except _FetchFailure as exc:
                if attempt == 1 and exc.retryable:
                    time.sleep(RETRY_DELAY)
                    continue
                return b"", None, str(exc)
    finally:
        client.close()


def _invalid(filename: str, source: str, errors: list[str]) -> SourceDocument:
    return SourceDocument(
        filename=filename,
        source=source,
        content="",
        valid=False,
        validation_errors=errors,
    )


def _decode_text(content: bytes, filename: str, source: str) -> SourceDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _invalid(
            filename,
            source,
            [f"{filename!r} is not valid UTF-8 text: {exc}"],
        )
    return SourceDocument(filename=filename, source=source, content=text)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_local(path: str) -> SourceDocument:
    """Load a local file with format gating applied.

    Args:
        path: Absolute or relative filesystem path.

    Returns:
        A :class:`SourceDocument`. Missing files, unreadable files,
        unsupported extensions, and non-UTF-8 content produce
        ``valid=False`` with descriptive errors.
    """
    filename = Path(path).name
    ext_error = check_extension(filename)
    if ext_error:
        return _invalid(filename, "local", [ext_error])

    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return _invalid(filename, "local", [f"File not found: {path}"])
    except OSError as exc:
        return _invalid(filename, "local", [f"Cannot read file: {exc}"])

    return _decode_text(raw, filename, "local")


_GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/"
    r"blob/(?P<ref>[^/]+)/(?P<path>.+)$"
)


def normalize_github_url(url: str) -> tuple[str | None, str | None]:
    """Normalize a GitHub URL to a raw.githubusercontent.com URL.

    Accepts ``https://raw.githubusercontent.com/...`` as-is and normalizes
    ``github.com/{owner}/{repo}/blob/{ref}/{path}`` to its raw form.

    Returns:
        ``(normalized_url, error)`` — exactly one of the two is ``None``.
    """
    if url.startswith("https://raw.githubusercontent.com/") or url.startswith(
        "http://raw.githubusercontent.com/"
    ):
        return url, None
    match = _GITHUB_BLOB_RE.match(url)
    if not match:
        return None, (
            f"Unsupported GitHub URL: {url}; expected "
            "github.com/{owner}/{repo}/blob/{ref}/{path} or "
            "raw.githubusercontent.com"
        )
    owner = match.group("owner")
    repo = match.group("repo")
    ref = match.group("ref")
    path = match.group("path")
    return (
        f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}",
        None,
    )


def load_github(url: str, transport: httpx.BaseTransport | None = None) -> SourceDocument:
    """Fetch a public GitHub file (raw or blob URL).

    The blob form is normalized to raw; fetching uses an SSRF-guarded GET
    with redirect cap, 25 MB size cap, and retry-once on 5xx/timeout. A 404
    produces ``valid=False`` reporting the status code.
    """
    normalized, norm_error = normalize_github_url(url)
    if norm_error:
        return _invalid(url.rstrip("/").split("/")[-1], "github", [norm_error])

    filename = normalized.rstrip("/").split("/")[-1]
    ext_error = check_extension(filename)
    if ext_error:
        return _invalid(filename, "github", [ext_error])

    content, _headers, error = _get_with_retry(normalized, transport=transport)
    if error:
        return _invalid(filename, "github", [error])

    return _decode_text(content, filename, "github")


def load_http(url: str, transport: httpx.BaseTransport | None = None) -> SourceDocument:
    """Fetch a generic public URL.

    Derives the filename from ``Content-Disposition`` (``filename*=``, then
    ``filename=``, then the last URL path segment), sanitizes it to a plain
    basename, applies the format gate, and enforces the 25 MB size cap while
    streaming.
    """
    content, headers, error = _get_with_retry(url, transport=transport)
    if error:
        return _invalid(url.rstrip("/").split("/")[-1], "http", [error])

    content_disposition = headers.get("content-disposition") if headers else None
    derived = derive_filename(content_disposition, url)
    filename = sanitize_filename(derived or "")
    if filename is None:
        return _invalid(
            derived or "download",
            "http",
            [f"Unsafe filename derived from Content-Disposition: {derived!r}"],
        )

    ext_error = check_extension(filename)
    if ext_error:
        return _invalid(filename, "http", [ext_error])

    return _decode_text(content, filename, "http")


_DRIVE_OPEN_URL_RE = re.compile(
    r"drive\.google\.com/open\?id=(?P<id>[^&#]+)"
)
_DRIVE_UC_ID_RE = re.compile(
    r"drive\.google\.com/uc\?.*\bid=(?P<id>[^&#]+)"
)
# Real Drive file IDs are URL-safe alphanumeric tokens; anything else is not
# a bare file ID.
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_CONFIRM_TOKEN_RE = re.compile(r"confirm=([0-9A-Za-z_-]+)")
_PERMISSION_MARKERS = (
    "requestaccess",
    "you need access",
    "need to request access",
    "accounts.google.com",
)


def _extract_drive_id(url_or_id: str) -> str | None:
    """Extract a file ID from any of the four supported Drive URL forms, or
    accept a bare file ID."""
    value = (url_or_id or "").strip()
    if not value:
        return None
    if "drive.google.com" not in value:
        # Bare file ID (not a URL at all).
        if "/" in value or value.startswith(("http://", "https://")):
            return None
        return value if _BARE_ID_RE.match(value) else None
    match = _DRIVE_UC_ID_RE.search(value) or _DRIVE_OPEN_URL_RE.search(value)
    if match:
        return match.group("id")
    return None


def _extract_confirm_token(content: bytes) -> str | None:
    """Extract the Drive download ``confirm`` token from an interstitial
    HTML page, if present."""
    match = _CONFIRM_TOKEN_RE.search(content.decode("utf-8", errors="replace"))
    return match.group(1) if match else None


def _drive_permission_page(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _PERMISSION_MARKERS)


def load_drive(
    url_or_id: str, transport: httpx.BaseTransport | None = None
) -> SourceDocument:
    """Fetch a public Google Drive file.

    Accepts ``uc?export=download&id={ID}``, ``uc?id={ID}``,
    ``open?id={ID}``, and a bare file ID. Files over the confirmation
    threshold return an HTML interstitial; the ``confirm`` token is
    extracted and a second GET with ``&confirm={token}`` is issued.
    Permission-required files produce ``valid=False``.
    """
    file_id = _extract_drive_id(url_or_id)
    if file_id is None:
        return _invalid(
            url_or_id[:64], "drive", [f"Unrecognized Google Drive URL: {url_or_id!r}"]
        )

    first_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    content, headers, error = _get_with_retry(first_url, transport=transport)
    if error:
        return _invalid(file_id, "drive", [error])

    text = content.decode("utf-8", errors="replace")

    # Confirm-token interstitial: extract the token and re-request.
    if "html" in (headers.get("content-type", "") if headers else "").lower() or (
        text.lstrip().lower().startswith(("<html", "<!doctype"))
    ):
        token = _extract_confirm_token(content)
        if token:
            second_url = f"{first_url}&confirm={token}"
            content, headers, error = _get_with_retry(
                second_url, transport=transport
            )
            if error:
                return _invalid(file_id, "drive", [error])
            text = content.decode("utf-8", errors="replace")

    if _drive_permission_page(text):
        return _invalid(
            file_id,
            "drive",
            ["Google Drive file is not public (permission required)"],
        )
    if text.lstrip().lower().startswith(("<html", "<!doctype")):
        return _invalid(
            file_id,
            "drive",
            ["Google Drive returned an HTML page instead of a file "
             "(no confirm token found)"],
        )

    content_disposition = headers.get("content-disposition") if headers else None
    if content_disposition:
        # The Drive filename comes exclusively from Content-Disposition; the
        # URL path segment is just the file ID, not a real name.
        derived = _parse_content_disposition(content_disposition)
        filename = sanitize_filename(derived or "")
        if filename is None:
            return _invalid(
                derived or "drive",
                "drive",
                [f"Unsafe filename derived from Content-Disposition: {derived!r}"],
            )
        ext_error = check_extension(filename)
        if ext_error:
            return _invalid(filename, "drive", [ext_error])
    else:
        # No type information at all: treat as generic text.
        filename = f"drive-{file_id}.txt"

    return _decode_text(content, filename, "drive")


def _is_zip(content: bytes) -> bool:
    return zipfile.is_zipfile(io.BytesIO(content))


def _is_safe_zip_member(name: str) -> bool:
    """ZIP-SLIP guard: reject absolute paths, drive letters, and any ``..``
    segment in a member name."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return False
    segments = [segment for segment in normalized.split("/") if segment]
    if any(segment == ".." for segment in segments):
        return False
    return True


def _unwrap_kaggle_zip(content: bytes) -> SourceDocument:
    """Extract the single plain-basename text member from a Kaggle ZIP.

    Enforces the zip-slip guard, member-level and total uncompressed size
    caps, and the one-text-member rule (zero or multiple → ``valid=False``).
    """
    text_members: list[str] = []
    discovered: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > MAX_DOWNLOAD_BYTES:
                return _invalid(
                    "kaggle",
                    "kaggle",
                    [f"ZIP total uncompressed size exceeds limit of "
                     f"{MAX_DOWNLOAD_BYTES} bytes"],
                )
            for info in infos:
                name = info.filename
                if not _is_safe_zip_member(name):
                    return _invalid(
                        "kaggle",
                        "kaggle",
                        [f"Unsafe ZIP member name {name!r} rejected (zip-slip guard)"],
                    )
                if info.is_dir():
                    continue
                if info.file_size > MAX_DOWNLOAD_BYTES:
                    return _invalid(
                        "kaggle",
                        "kaggle",
                        [f"ZIP member {name!r} exceeds size limit of "
                         f"{MAX_DOWNLOAD_BYTES} bytes"],
                    )
                if check_extension(Path(name).name) is None:
                    discovered.append(name)
                    if sanitize_filename(name) == name:
                        text_members.append(name)
            if len(text_members) != 1:
                return _invalid(
                    "kaggle",
                    "kaggle",
                    ["Kaggle dataset ZIP must contain exactly one text member "
                     f"(.ipynb/.md/.py/.txt); found: {sorted(discovered) or 'none'}"],
                )
            member = text_members[0]
            raw = archive.read(member)
    except (zipfile.BadZipFile, zlib.error, OSError, RuntimeError, NotImplementedError) as exc:
        return _invalid("kaggle", "kaggle", [f"Invalid ZIP archive: {exc}"])

    return _decode_text(raw, Path(member).name, "kaggle")


def load_kaggle(
    owner: str, slug: str, transport: httpx.BaseTransport | None = None
) -> SourceDocument:
    """Download a public Kaggle dataset without credentials.

    Fetches ``https://www.kaggle.com/api/v1/datasets/download/{owner}/{slug}``
    with the SSRF guard, size cap, and retry-once. ZIP responses are
    unwrapped to the single plain-basename text member; single-file responses
    are gated by their derived filename.
    """
    owner = (owner or "").strip().strip("/")
    slug = (slug or "").strip().strip("/")
    if not owner or not slug:
        return _invalid(
            "kaggle",
            "kaggle",
            ["Kaggle dataset requires both owner and slug"],
        )

    url = f"https://www.kaggle.com/api/v1/datasets/download/{owner}/{slug}"
    content, headers, error = _get_with_retry(url, transport=transport)
    if error:
        return _invalid(f"{owner}-{slug}", "kaggle", [error])

    if _is_zip(content):
        return _unwrap_kaggle_zip(content)

    derived = derive_filename(
        headers.get("content-disposition") if headers else None, url
    )
    filename = sanitize_filename(derived or "")
    if filename is None:
        return _invalid(
            derived or "kaggle",
            "kaggle",
            [f"Unsafe filename derived from download: {derived!r}"],
        )
    ext_error = check_extension(filename)
    if ext_error:
        return _invalid(filename, "kaggle", [ext_error])

    return _decode_text(content, filename, "kaggle")
