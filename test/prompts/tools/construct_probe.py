#!/usr/bin/env python3
"""Ad-hoc construct-core probe: loaders, scaffold, writer, export.

Runs fully offline with ``httpx.MockTransport`` canned responses and
in-memory ZIPs — no real network, no test framework (strict TDD inactive).
It asserts the approved review findings folded into the construct core:

- Loader result contract: missing file -> invalid; format gate rejects
  ``.sh``/``.pdf``/``.exe``
- GitHub blob -> raw normalization; 404 -> invalid
- Generic HTTP: Content-Disposition parsing (incl. RFC 5987), traversal
  sanitization, size cap, retry-once on 5xx/timeout (never 4xx)
- SSRF guard: loopback/private/link-local/localhost/scheme rejections
- Drive: 4 URL forms, confirm-token second GET, permission -> invalid
- Kaggle: single-file, ZIP unwrap, ambiguous ZIP, zip-slip rejection,
  member/total size caps
- Scaffold: 8 headers in canonical order, env-pin + seeds cells,
  nbformat.validate passes, source does not alter skeleton
- Writer: strict ===MARKDOWN===/===CODE=== parse (missing MARKDOWN,
  off-format, escaped markers), retry-once, ProviderError retry,
  ast.parse reject, failure continues, progress_cb per section
- Export: versioned names (name-v2.ipynb), atomic write, dir creation,
  .py opt-in, unsafe names rejected

Usage:
    cd test/prompts
    python3 tools/construct_probe.py

Exit code 0 when all checks pass, 1 otherwise.
"""

import asyncio
import io
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import nbformat

# Allow running as a plain script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.utils import LLMProvider, ProviderError
from app.construct import loaders
from app.construct.export import flatten_to_py, save_notebook
from app.construct.loaders import (
    MAX_DOWNLOAD_BYTES,
    derive_filename,
    load_drive,
    load_github,
    load_http,
    load_kaggle,
    load_local,
    normalize_github_url,
    sanitize_filename,
    validate_public_url,
)
from app.construct.models import SourceDocument
from app.construct.scaffold import CANONICAL_HEADERS, build_scaffold
from app.construct.writer import draft_sections, parse_section_output

# ---- offline DNS: any hostname resolves to a public IP ---------------------
loaders._lookup_host = lambda host: ["1.2.3.4"]

RESULTS = []


def check(name, condition, detail=""):
    """Record a single probe check."""
    RESULTS.append((name, bool(condition)))
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def canned_response(content, status=200, headers=None):
    return httpx.Response(status, content=content, headers=headers or {})


def invalid_err(result, expected_substring):
    return (
        not result.valid
        and any(expected_substring in e for e in result.validation_errors)
    )


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------

def probe_ssrf():
    cases = {
        "http://127.0.0.1:8000/v1/x": "non-public",
        "http://10.0.0.5/x": "non-public",
        "http://169.254.169.254/latest/meta-data": "non-public",
        "http://192.168.1.1/x": "non-public",
        "http://[::1]/x": "non-public",
        "http://localhost/x": "local hostname",
        "http://notes.localhost/x": "local hostname",
        "ftp://example.com/x": "scheme",
        "file:///etc/passwd": "scheme",
    }
    for url, keyword in cases.items():
        err = validate_public_url(url)
        check(f"ssrf: reject {url}", err is not None and keyword in err, str(err))
    check("ssrf: allow public host", validate_public_url("http://example.com/notes.md") is None)

    # Redirect hop to internal host must be refused end-to-end.
    def redirect_to_internal(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/internal"})

    result = load_http(
        "http://example.com/notes.md",
        transport=httpx.MockTransport(redirect_to_internal),
    )
    check(
        "ssrf: redirect to loopback refused",
        not result.valid and any("non-public" in e for e in result.validation_errors),
        str(result.validation_errors),
    )


# ---------------------------------------------------------------------------
# Local loader
# ---------------------------------------------------------------------------

def probe_local():
    tmp = Path(tempfile.mkdtemp(prefix="construct-local-"))
    md = tmp / "notes.md"
    md.write_text("# Notes\n\nSome content.\n", encoding="utf-8")

    result = load_local(str(md))
    check(
        "local: existing .md loads",
        result.valid and result.content.startswith("# Notes"),
        result.filename,
    )
    check("local: filename kept", result.filename == "notes.md")

    missing = load_local(str(tmp / "nope.md"))
    check("local: missing file invalid", invalid_err(missing, "File not found"), str(missing.validation_errors))

    for bad in ("notes.sh", "notes.pdf", "script.exe"):
        p = tmp / bad
        p.write_text("x")
        result = load_local(str(p))
        check(
            f"local: {bad} rejected by format gate",
            invalid_err(result, "Unsupported file extension"),
            str(result.validation_errors),
        )


# ---------------------------------------------------------------------------
# GitHub loader
# ---------------------------------------------------------------------------

def probe_github():
    normalized, err = normalize_github_url(
        "https://github.com/acme/notebooks/blob/main/notes.md"
    )
    check(
        "github: blob normalized to raw",
        err is None and normalized == "https://raw.githubusercontent.com/acme/notebooks/main/notes.md",
        str(normalized),
    )
    raw, err = normalize_github_url("https://raw.githubusercontent.com/acme/nb/main/notes.md")
    check("github: raw URL as-is", err is None and raw.endswith("notes.md"))
    _, err = normalize_github_url("https://github.com/acme/nb/raw/main/notes.md")
    check("github: unsupported URL rejected", err is not None, str(err))

    captured = {}

    def blob_handler(request):
        captured["url"] = str(request.url)
        return canned_response(b"# From GitHub\n", headers={"content-type": "text/plain"})

    result = load_github(
        "https://github.com/acme/notebooks/blob/main/notes.md",
        transport=httpx.MockTransport(blob_handler),
    )
    check(
        "github: fetch uses normalized raw URL",
        result.valid and captured["url"] == "https://raw.githubusercontent.com/acme/notebooks/main/notes.md",
        captured.get("url"),
    )
    check("github: content loaded", result.valid and "From GitHub" in result.content)

    def not_found(request):
        return canned_response(b"Not Found", status=404)

    result = load_github(
        "https://raw.githubusercontent.com/acme/nb/main/missing.md",
        transport=httpx.MockTransport(not_found),
    )
    check("github: 404 invalid with status", invalid_err(result, "HTTP 404"), str(result.validation_errors))

    result = load_github(
        "https://raw.githubusercontent.com/acme/nb/main/evil.exe",
        transport=httpx.MockTransport(blob_handler),
    )
    check("github: .exe rejected by format gate", invalid_err(result, "Unsupported file extension"))


# ---------------------------------------------------------------------------
# Generic HTTP loader
# ---------------------------------------------------------------------------

def probe_http():
    # Content-Disposition filename
    def cd_handler(request):
        return canned_response(
            b"data\n",
            headers={"content-disposition": 'attachment; filename="data.txt"'},
        )

    result = load_http("http://example.com/whatever", transport=httpx.MockTransport(cd_handler))
    check("http: Content-Disposition filename", result.valid and result.filename == "data.txt", result.filename)

    # RFC 5987 filename*
    def cd_star_handler(request):
        return canned_response(
            b"x\n", headers={"content-disposition": "attachment; filename*=UTF-8''notes%20with%20spaces.md"}
        )

    result = load_http("http://example.com/a", transport=httpx.MockTransport(cd_star_handler))
    check(
        "http: filename* decoded",
        result.valid and result.filename == "notes with spaces.md",
        result.filename,
    )

    # Last URL path segment fallback
    result = load_http(
        "http://example.com/deep/path/fallback.md",
        transport=httpx.MockTransport(lambda r: canned_response(b"x\n")),
    )
    check("http: URL path fallback", result.valid and result.filename == "fallback.md")

    # Traversal / absolute filenames -> invalid
    for evil in ('attachment; filename="../../etc/passwd"', 'attachment; filename="/abs/notes.md"'):
        result = load_http(
            "http://example.com/a",
            transport=httpx.MockTransport(
                lambda r, cd=evil: canned_response(b"x\n", headers={"content-disposition": cd})
            ),
        )
        check(
            f"http: traversal sanitized ({evil!r})",
            not result.valid and any("filename" in e for e in result.validation_errors),
            str(result.validation_errors),
        )

    # Unsupported extension from URL path
    result = load_http("http://example.com/notes.pdf", transport=httpx.MockTransport(lambda r: canned_response(b"%PDF\n")))
    check("http: .pdf rejected by format gate", invalid_err(result, "Unsupported file extension"))

    # Size cap (end-to-end through load_http): 25 MB + 1 byte
    big = b"x" * (MAX_DOWNLOAD_BYTES + 1)
    result = load_http(
        "http://example.com/big.md",
        transport=httpx.MockTransport(lambda r: canned_response(big)),
    )
    check("http: size cap exceeded -> invalid", invalid_err(result, "size limit"), str(result.validation_errors))

    # Direct helper cap probe (small cap, fast)
    ok, _headers, error = loaders._get_with_retry(
        "http://example.com/small.md",
        transport=httpx.MockTransport(lambda r: canned_response(b"1234567890" * 20)),
        max_bytes=100,
    )
    check("http: helper size cap (100B)", not ok and "size limit" in (error or ""), str(error))

    # Retry-once on 5xx, never on 4xx
    counts = {"n": 0}

    def flaky_500(request):
        counts["n"] += 1
        if counts["n"] == 1:
            return canned_response(b"boom", status=500)
        return canned_response(b"ok\n")

    result = load_http("http://example.com/flaky.md", transport=httpx.MockTransport(flaky_500))
    check("http: 5xx retried once then succeeds", result.valid and counts["n"] == 2, f"calls={counts['n']}")

    counts["n"] = 0

    def flaky_404(request):
        counts["n"] += 1
        return canned_response(b"nope", status=404)

    result = load_http("http://example.com/missing.md", transport=httpx.MockTransport(flaky_404))
    check("http: 4xx never retried", not result.valid and counts["n"] == 1, f"calls={counts['n']}")

    counts["n"] = 0

    def flaky_timeout(request):
        counts["n"] += 1
        if counts["n"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return canned_response(b"ok\n")

    result = load_http("http://example.com/slow.md", transport=httpx.MockTransport(flaky_timeout))
    check("http: timeout retried once", result.valid and counts["n"] == 2, f"calls={counts['n']}")

    # derive_filename unit checks
    check(
        "derive_filename: plain",
        derive_filename('attachment; filename="a.txt"', "http://x/fallback") == "a.txt",
    )
    check(
        "derive_filename: rfc5987",
        derive_filename("attachment; filename*=UTF-8''a%20b.txt", "http://x/f") == "a b.txt",
    )
    check(
        "derive_filename: falls back to URL segment",
        derive_filename(None, "http://x/notes.md") == "notes.md",
    )
    check("sanitize_filename: plain basename", sanitize_filename("notes.md") == "notes.md")
    check("sanitize_filename: absolute rejected", sanitize_filename("/etc/passwd") is None)
    check("sanitize_filename: traversal rejected", sanitize_filename("../../x") is None)
    check("sanitize_filename: backslash traversal rejected", sanitize_filename("..\\..\\x") is None)


# ---------------------------------------------------------------------------
# Drive loader
# ---------------------------------------------------------------------------

def probe_drive():
    ids = {
        "https://drive.google.com/uc?export=download&id=ABC123": "ABC123",
        "https://drive.google.com/uc?id=ABC123": "ABC123",
        "https://drive.google.com/open?id=ABC123": "ABC123",
        "ABC123": "ABC123",
    }
    for url, expected in ids.items():
        check(f"drive: id extraction ({url[:48]})", loaders._extract_drive_id(url) == expected)

    # Small public file: direct download
    def small(request):
        return canned_response(
            b"drive content\n",
            headers={"content-disposition": 'attachment; filename="data.txt"'},
        )

    result = load_drive("ABC123", transport=httpx.MockTransport(small))
    check(
        "drive: small public file",
        result.valid and result.filename == "data.txt" and "drive content" in result.content,
    )

    # Confirm-token interstitial: first GET returns HTML form, second with
    # confirm= token returns the file.
    requests = []

    def confirm_flow(request):
        requests.append(str(request.url))
        if "confirm=" in str(request.url):
            return canned_response(
                b"real content\n",
                headers={"content-disposition": 'attachment; filename="notes.md"'},
            )
        html = (
            b'<html><body><form action="/uc?export=download&confirm=TOK123&id=ABC123">'
            b'<button>download</button></form></body></html>'
        )
        return canned_response(html, headers={"content-type": "text/html; charset=utf-8"})

    result = load_drive("ABC123", transport=httpx.MockTransport(confirm_flow))
    check(
        "drive: confirm token triggers second GET",
        result.valid and len(requests) == 2 and "confirm=TOK123" in requests[1],
        str(requests),
    )
    check("drive: confirm content loaded", result.valid and "real content" in result.content and result.filename == "notes.md")

    # Permission-required page -> invalid
    def permission(request):
        return canned_response(
            b'<html><body>You need access. Request access or switch to an account with access.</body></html>',
            headers={"content-type": "text/html; charset=utf-8"},
        )

    result = load_drive("ABC123", transport=httpx.MockTransport(permission))
    check(
        "drive: permission required -> invalid",
        not result.valid and any("not public" in e for e in result.validation_errors),
        str(result.validation_errors),
    )

    result = load_drive("not a url nor valid", transport=httpx.MockTransport(small))
    check("drive: garbage input invalid", not result.valid)

    # No Content-Disposition -> generic .txt fallback; unsupported extension
    # in Content-Disposition -> format gate rejects.
    result = load_drive("ABC123", transport=httpx.MockTransport(lambda r: canned_response(b"x\n")))
    check("drive: no CD -> drive-{id}.txt fallback", result.valid and result.filename == "drive-ABC123.txt", result.filename)

    result = load_drive(
        "ABC123",
        transport=httpx.MockTransport(
            lambda r: canned_response(b"%PDF\n", headers={"content-disposition": 'attachment; filename="notes.pdf"'})
        ),
    )
    check("drive: .pdf in Content-Disposition rejected", not result.valid and any("Unsupported file extension" in e for e in result.validation_errors))


# ---------------------------------------------------------------------------
# Kaggle loader
# ---------------------------------------------------------------------------

def _zip_bytes(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def probe_kaggle():
    # Single-file dataset (not a ZIP)
    def single(request):
        return canned_response(
            b"# Single file\n",
            headers={"content-disposition": 'attachment; filename="readme.md"'},
        )

    result = load_kaggle("owner", "slug", transport=httpx.MockTransport(single))
    check("kaggle: single-file dataset", result.valid and result.filename == "readme.md")

    # ZIP with exactly one text member
    z = _zip_bytes([("notes.md", "# Kaggle notes\n")])

    def zip_handler(request):
        return canned_response(z, headers={"content-type": "application/zip"})

    result = load_kaggle("owner", "dataset", transport=httpx.MockTransport(zip_handler))
    check(
        "kaggle: zip unwrapped to single member",
        result.valid and result.filename == "notes.md" and "Kaggle notes" in result.content,
        f"{result.filename} {result.validation_errors}",
    )

    # Ambiguous ZIP (two text members) -> invalid, members listed
    z = _zip_bytes([("a.md", "one"), ("b.py", "two")])
    result = load_kaggle("owner", "dataset", transport=httpx.MockTransport(lambda r: canned_response(z)))
    check(
        "kaggle: ambiguous zip invalid + members listed",
        not result.valid
        and "exactly one text member" in result.validation_errors[0]
        and "a.md" in result.validation_errors[0]
        and "b.py" in result.validation_errors[0],
        str(result.validation_errors),
    )

    # ZIP with zero text members
    z = _zip_bytes([("data.csv", "a,b\n1,2\n")])
    result = load_kaggle("owner", "dataset", transport=httpx.MockTransport(lambda r: canned_response(z)))
    check(
        "kaggle: zero text members invalid",
        not result.valid and "exactly one text member" in result.validation_errors[0],
        str(result.validation_errors),
    )

    # ZIP-SLIP: member with .. segment -> invalid
    z = _zip_bytes([("../evil.md", "escape"), ("notes.md", "good")])
    result = load_kaggle("owner", "dataset", transport=httpx.MockTransport(lambda r: canned_response(z)))
    check(
        "kaggle: zip-slip member rejected",
        not result.valid and any("zip-slip" in e for e in result.validation_errors),
        str(result.validation_errors),
    )

    # ZIP-SLIP: absolute member -> invalid
    z = _zip_bytes([("/etc/passwd.md", "escape")])
    result = load_kaggle("owner", "dataset", transport=httpx.MockTransport(lambda r: canned_response(z)))
    check(
        "kaggle: absolute member rejected",
        not result.valid and any("zip-slip" in e for e in result.validation_errors),
        str(result.validation_errors),
    )

    # Size caps (patched small cap): member too big
    saved = loaders.MAX_DOWNLOAD_BYTES
    loaders.MAX_DOWNLOAD_BYTES = 1024
    try:
        z = _zip_bytes([("big.md", "x" * 2048)])
        result = load_kaggle("owner", "dataset", transport=httpx.MockTransport(lambda r: canned_response(z)))
        check(
            "kaggle: oversized member rejected by size cap",
            not result.valid
            and any(("size limit" in e) or ("uncompressed size" in e) for e in result.validation_errors),
            str(result.validation_errors),
        )
        # Total uncompressed cap
        z = _zip_bytes([("a.md", "x" * 600), ("b.md", "y" * 600)])
        result = load_kaggle("owner", "dataset", transport=httpx.MockTransport(lambda r: canned_response(z)))
        check(
            "kaggle: total uncompressed size cap",
            not result.valid and any("uncompressed size" in e for e in result.validation_errors),
            str(result.validation_errors),
        )
        # Missing owner/slug
        result = load_kaggle("", "slug", transport=httpx.MockTransport(lambda r: canned_response(b"")))
        check("kaggle: missing owner invalid", not result.valid)
    finally:
        loaders.MAX_DOWNLOAD_BYTES = saved


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------

def probe_scaffold():
    result = build_scaffold()
    check("scaffold: valid result", result.valid and result.notebook is not None)
    if not result.notebook:
        return

    nb = result.notebook
    markdown_headers = [
        "".join(c.source) if isinstance(c.source, list) else c.source
        for c in nb.cells
        if c.cell_type == "markdown"
    ]
    check(
        "scaffold: 8 headers in canonical order",
        markdown_headers == [f"## {h}" for h in CANONICAL_HEADERS],
        str(markdown_headers),
    )

    code_sources = [
        "".join(c.source) if isinstance(c.source, list) else c.source
        for c in nb.cells
        if c.cell_type == "code"
    ]
    check("scaffold: env-pin + seeds cells", len(code_sources) == 2)
    # Position: env-pin between header 1 and 2; seeds between header 2 and 3.
    kinds = ["md" if c.cell_type == "markdown" else "code" for c in nb.cells]
    hdr1 = kinds.index("md")
    hdr2 = kinds.index("md", hdr1 + 1)
    hdr3 = kinds.index("md", hdr2 + 1)
    check(
        "scaffold: env-pin in section 1",
        kinds[hdr1 + 1] == "code" and kinds[hdr2 + 1] == "code",
        str(kinds),
    )

    try:
        nbformat.validate(nb)
        check("scaffold: nbformat.validate passes", True)
    except nbformat.ValidationError as exc:
        check("scaffold: nbformat.validate passes", False, str(exc))

    # Generic skeleton: source never alters the structure. Compare structure
    # ignoring the random per-cell ``id`` fields nbformat generates.
    source = SourceDocument(
        filename="readme.md", source="local", content="# totally different content"
    )
    with_source = build_scaffold(source)

    def stripped(nb):
        from copy import deepcopy
        copy = deepcopy(nb)
        for i, cell in enumerate(copy.cells):
            cell["id"] = f"cell-{i}"
        return copy

    check(
        "scaffold: skeleton identical regardless of source",
        with_source.valid
        and nbformat.writes(stripped(with_source.notebook), version=4)
        == nbformat.writes(stripped(nb), version=4),
    )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def good_output(header):
    return (
        f"===MARKDOWN===\n# {header}\n\nExplanation of intent and expected output.\n"
        f"===CODE===\nvalue = 42\nprint(value)\n"
    )


class SequenceProvider(LLMProvider):
    """Canned-response fake provider: per-header sequence queues, retry
    counts per header, optional always-fail sections."""

    def __init__(self):
        super().__init__()
        self.outputs = {}
        self.calls = {}
        self.fail_forever = set()

    def set(self, header, sequence):
        self.outputs[header] = list(sequence)

    def set_all(self, sequence_factory):
        for header in CANONICAL_HEADERS:
            self.outputs[header] = [sequence_factory(header)]

    async def draft_section(self, header, instructions, source_context):
        self.calls[header] = self.calls.get(header, 0) + 1
        if header in self.fail_forever:
            raise ProviderError(f"simulated failure for {header}")
        queue = self.outputs.get(header) or []
        if not queue:
            raise ProviderError(f"no canned output for {header}")
        response = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(response, Exception):
            raise response
        return response


def probe_writer_parse():
    parsed = parse_section_output("===MARKDOWN===\nIntro\n===CODE===\nprint(1)")
    check(
        "parse: markdown+code blocks",
        not parsed.errors and parsed.blocks == [("markdown", "Intro"), ("code", "print(1)")],
        str(parsed.blocks),
    )

    parsed = parse_section_output("===CODE===\nprint(1)")
    check("parse: missing MARKDOWN fails", any("MARKDOWN" in e for e in parsed.errors), str(parsed.errors))

    parsed = parse_section_output("plain prose, no markers")
    check("parse: off-format fails", bool(parsed.errors), str(parsed.errors))

    parsed = parse_section_output("")
    check("parse: empty fails", bool(parsed.errors), str(parsed.errors))

    parsed = parse_section_output("===MARKDOWN===\n\\===CODE===\nliteral\n===CODE===\nx = 1")
    check(
        "parse: escaped marker kept verbatim",
        not parsed.errors and parsed.blocks[0] == ("markdown", "===CODE===\nliteral"),
        str(parsed.blocks),
    )

    parsed = parse_section_output("===MARKDOWN===\na\n===CODE===\nb\n===MARKDOWN===\nc")
    check(
        "parse: block order preserved",
        [k for k, _ in parsed.blocks] == ["markdown", "code", "markdown"],
    )

    parsed = parse_section_output("junk\n===MARKDOWN===\nx")
    check("parse: leading content flagged", any("before the first marker" in e for e in parsed.errors), str(parsed.errors))


async def probe_writer_draft():
    scaffold = build_scaffold().notebook
    source = SourceDocument(filename="notes.md", source="local", content="SOURCE CONTEXT")

    # Happy path
    provider = SequenceProvider()
    provider.set_all(good_output)
    progress = []

    async def progress_cb(done, total, header, message):
        progress.append((done, total, header, message))

    session = await draft_sections(scaffold, source, provider, progress_cb=progress_cb)
    check("writer: happy path drafts", session.drafted is not None and not session.errors)
    md_headers = [
        ("".join(c.source) if isinstance(c.source, list) else c.source).strip()
        for c in session.drafted.cells
        if c.cell_type == "markdown"
    ]
    check(
        "writer: all 8 headers present after draft",
        all(any(h == f"## {hdr}" for h in md_headers) for hdr in CANONICAL_HEADERS),
    )
    check(
        "writer: progress_cb per section in order",
        [p[0] for p in progress] == list(range(1, 9))
        and all(p[1] == 8 for p in progress)
        and all(p[3] == "ok" for p in progress),
        str(progress),
    )
    check("writer: each section drafted once (no double-run)", all(c == 1 for c in provider.calls.values()), str(provider.calls))
    try:
        nbformat.validate(session.drafted)
        check("writer: drafted notebook validates", True)
    except nbformat.ValidationError as exc:
        check("writer: drafted notebook validates", False, str(exc))

    # Retry-once: first attempt off-format, retry good.
    provider = SequenceProvider()
    for header in CANONICAL_HEADERS:
        provider.outputs[header] = ["no markers here", good_output(header)]
    session = await draft_sections(scaffold, source, provider)
    check(
        "writer: off-format retried once then accepted",
        session.drafted is not None
        and provider.calls[CANONICAL_HEADERS[0]] == 2
        and not session.errors,
        str(provider.calls),
    )

    # ProviderError retried once.
    provider = SequenceProvider()
    for header in CANONICAL_HEADERS:
        provider.outputs[header] = [ProviderError("boom"), good_output(header)]
    session = await draft_sections(scaffold, source, provider)
    check(
        "writer: ProviderError retried once",
        session.drafted is not None and provider.calls[CANONICAL_HEADERS[0]] == 2,
        str(provider.calls),
    )

    # ast.parse reject: bad code retried.
    bad_code = "===MARKDOWN===\nIntro\n===CODE===\ndef broken(:\n    pass\n"
    provider = SequenceProvider()
    for header in CANONICAL_HEADERS:
        provider.outputs[header] = [bad_code, good_output(header)]
    session = await draft_sections(scaffold, source, provider)
    check(
        "writer: ast.parse failure retried once",
        session.drafted is not None
        and provider.calls[CANONICAL_HEADERS[0]] == 2
        and not session.errors,
        str(provider.calls),
    )

    # Failure continues: one section always fails, rest draft.
    provider = SequenceProvider()
    provider.set_all(good_output)
    provider.fail_forever.add(CANONICAL_HEADERS[2])  # Data Ingestion
    session = await draft_sections(scaffold, source, provider)
    check(
        "writer: failed section recorded, run continues",
        session.drafted is not None
        and len(session.errors) == 1
        and "Data Ingestion" in session.errors[0],
        str(session.errors),
    )
    check(
        "writer: other sections still drafted",
        all(c == 1 for h, c in provider.calls.items() if h != CANONICAL_HEADERS[2]),
        str(provider.calls),
    )

    # All sections fail -> no drafted notebook.
    provider = SequenceProvider()
    provider.set_all(good_output)
    provider.fail_forever.update(CANONICAL_HEADERS)
    session = await draft_sections(scaffold, source, provider)
    check(
        "writer: all sections failed -> no drafted notebook",
        session.drafted is None and len(session.errors) == 8,
        str(len(session.errors)),
    )

    # No valid source -> no drafting at all.
    provider = SequenceProvider()
    provider.set_all(good_output)
    session = await draft_sections(
        scaffold, SourceDocument(filename="x.md", source="local", content="", valid=False), provider
    )
    check("writer: invalid source aborts", session.drafted is None and bool(session.errors))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def probe_export():
    scaffold = build_scaffold().notebook
    # Give it one drafted code cell so .py has content.
    from nbformat import v4 as nbv4

    notebook = nbformat.v4.new_notebook(metadata=scaffold.metadata)
    notebook.cells = list(scaffold.cells) + [
        nbv4.new_markdown_cell("## Drafted"),
        nbv4.new_code_cell("print('hello')\nx = 1\n"),
    ]
    nbformat.validate(notebook)

    with tempfile.TemporaryDirectory(prefix="construct-export-") as tmp:
        out = save_notebook(notebook, "analysis.md", notebooks_dir=tmp)
        check(
            "export: fresh name saved as-is",
            out.valid and out.saved_path and Path(out.saved_path).name == "analysis.ipynb",
            str(out.saved_path),
        )
        first = Path(out.saved_path)
        check("export: file exists", first.exists())
        check(
            "export: content is valid ipynb",
            nbformat.validate(nbformat.read(first, as_version=4)) is None,
        )

        # Collision -> name-v2.ipynb, original untouched
        out2 = save_notebook(notebook, "analysis.md", notebooks_dir=tmp)
        check(
            "export: collision versioned to name-v2.ipynb",
            out2.valid and Path(out2.saved_path).name == "analysis-v2.ipynb",
            str(out2.saved_path),
        )
        check("export: original untouched", first.exists() and Path(out2.saved_path) != first)

        # .py opt-in: "analysis.py" is fresh here (only .ipynb names taken);
        # the .py versioning is independent of the .ipynb chain.
        out3 = save_notebook(notebook, "analysis.md", export_py=True, notebooks_dir=tmp)
        check(
            "export: .py opt-in written alongside",
            out3.valid and out3.py_path and Path(out3.py_path).name == "analysis.py",
            str(out3.py_path),
        )
        py_text = Path(out3.py_path).read_text(encoding="utf-8")
        check(
            "export: .py contains code cells with comments",
            "print('hello')" in py_text and "# --- code cell" in py_text,
        )

        # .py skipped by default
        check("export: .py skipped by default", out2.py_path is None)

        # Directory created when missing
        nested = Path(tmp) / "a" / "b"
        out4 = save_notebook(notebook, "notes.md", notebooks_dir=str(nested))
        check(
            "export: missing directory created",
            out4.valid and nested.is_dir() and Path(out4.saved_path).parent == nested,
        )

    # Unsafe base names
    for evil in ("../../evil", "/abs/x", ".."):
        out = save_notebook(notebook, evil, notebooks_dir="/tmp")
        check(f"export: unsafe base rejected ({evil!r})", not out.valid)

    # Invalid notebook
    out = save_notebook({"not": "a notebook"}, "notes.md", notebooks_dir="/tmp")
    check("export: invalid notebook rejected", not out.valid)

    # flatten_to_py pure function
    flat = flatten_to_py(notebook)
    check("flatten_to_py: code cells present, no markdown", "print('hello')" in flat and "Drafted" not in flat)


async def main():
    print("== construct_probe ==")
    probe_ssrf()
    probe_local()
    probe_github()
    probe_http()
    probe_drive()
    probe_kaggle()
    probe_scaffold()
    probe_writer_parse()
    await probe_writer_draft()
    probe_export()

    failed = [name for name, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:")
        for name in failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
