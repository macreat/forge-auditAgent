# Construct Source Loading Specification

## Purpose

Load a source document into the Construct pipeline from local disk or public cloud (GitHub raw, Google Drive, Kaggle, generic HTTP). Loaders are generic: any text/data file in supported formats is accepted; no domain-specific parsing. Only public files; no OAuth.

## Requirements

### Requirement: Loader result contract

Every loader MUST return an object with `valid: bool` and `validation_errors: list[str]`, mirroring `app/audit/loader.py`. Loaders MUST NOT raise on user-facing failures; they MUST set `valid=False` with descriptive errors instead.

#### Scenario: Missing file

- GIVEN a nonexistent local path
- WHEN the loader processes it
- THEN the result has `valid=False` with a "File not found" error

#### Scenario: Successful load

- GIVEN a readable supported file
- WHEN the loader processes it
- THEN the result has `valid=True` and empty errors

### Requirement: Format gating

Loaders MUST accept only `.ipynb`, `.py`, `.md`, and `.txt` files, gating local paths, URL path segments, and download-derived filenames alike. Any other extension MUST produce `valid=False`.

#### Scenario: Unsupported extension

- GIVEN a source named `notes.pdf`
- WHEN the loader processes it
- THEN the result has `valid=False` with an unsupported-extension error

### Requirement: Local path loader

The local loader MUST read a file from disk by path with format gating applied.

#### Scenario: Local markdown file

- GIVEN an existing `.md` file selected as source
- WHEN the loader processes it
- THEN it returns `valid=True` with the content

### Requirement: GitHub raw URL loader

The GitHub loader MUST accept `https://raw.githubusercontent.com/...` URLs and MUST normalize `github.com/{owner}/{repo}/blob/{ref}/{path}` to raw form. Fetching MUST use `httpx.get(timeout=30, follow_redirects=True)`.

#### Scenario: Blob URL normalized

- GIVEN a `github.com/.../blob/main/notes.md` URL
- WHEN the loader processes it
- THEN it fetches the normalized raw URL and returns `valid=True`

#### Scenario: GitHub 404

- GIVEN a raw URL returning HTTP 404
- WHEN the loader processes it
- THEN the result has `valid=False` with the status code reported

### Requirement: Google Drive public loader

The Drive loader MUST accept `uc?export=download&id={ID}`, `uc?id={ID}`, `open?id={ID}`, and a bare file ID. For files over the confirmation threshold, the first response is an HTML page with a `confirm` token in a form action; the loader MUST extract it and issue a second GET with `&confirm={token}`. Permission-required files MUST produce `valid=False`.

#### Scenario: Small public file

- GIVEN a public file under the confirmation threshold
- WHEN the loader requests `uc?export=download&id={ID}`
- THEN it receives the file directly and returns `valid=True`

#### Scenario: Confirm-token interstitial

- GIVEN a public file whose first response is an HTML confirm form
- WHEN the loader processes it
- THEN it extracts the `confirm` token, re-requests with it, and returns `valid=True`

#### Scenario: Permission required

- GIVEN a file that requires sign-in
- WHEN the loader processes it
- THEN the result has `valid=False` stating the file is not public

### Requirement: Kaggle dataset loader

The Kaggle loader MUST download public datasets via `https://www.kaggle.com/api/v1/datasets/download/{owner}/{slug}` without credentials. If the response is a ZIP (multi-file dataset), the loader MUST extract the single `.ipynb`, `.md`, or `.py` member; zero or multiple text members MUST produce `valid=False`.

#### Scenario: Single-file dataset

- GIVEN a public dataset whose download returns one file
- WHEN the loader processes it
- THEN it returns `valid=True` with the content

#### Scenario: ZIP unwrapped to one notebook

- GIVEN a multi-file dataset whose download returns a ZIP
- WHEN the loader processes it
- THEN it extracts the single `.ipynb` member and returns `valid=True`

#### Scenario: Ambiguous ZIP

- GIVEN a ZIP with zero or multiple text-ish members
- WHEN the loader processes it
- THEN the result has `valid=False` listing the discovered members

### Requirement: Generic HTTP loader

The generic loader MUST fetch any URL with `httpx.get(timeout=30, follow_redirects=True)`, derive the filename from `Content-Disposition` (`filename*=UTF-8''...`, else `filename=`, else last URL path segment), and MUST enforce a response size cap (stream; 10–50 MB range). Exceeding the cap MUST produce `valid=False`.

#### Scenario: Filename from Content-Disposition

- GIVEN a response with `Content-Disposition: attachment; filename="data.txt"`
- WHEN the loader processes it
- THEN the stored filename is `data.txt` and the result has `valid=True`

#### Scenario: Oversized response

- GIVEN a response exceeding the size cap
- WHEN the loader processes it
- THEN the result has `valid=False` stating the size limit was exceeded
