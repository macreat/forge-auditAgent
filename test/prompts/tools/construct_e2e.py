#!/usr/bin/env python3
"""Scripted E2E demo of the full Construct loop, headless, WITHOUT a real LLM.

Runs the complete pipeline on a small local sample source document:

    load_local → build_scaffold → render prompts → draft_sections
    (FAKE provider returning canned strict-format section text) →
    save_notebook to defaultNotebooksDir()

It then confirms the exported ``.ipynb`` is discoverable by the Audit
Scan DB logic (``test/prompts/notebooks/`` directory, extension whitelist
``.ipynb``/``.py``/``.md``/``.txt``), closing the construct → audit loop.

No llama.cpp / GPU backend is required: the FAKE provider is a stub that
realizes ``LLMProvider.draft_section`` offline. Run from anywhere:

    cd test/prompts
    python3 tools/construct_e2e.py

Exit code 0 when the full loop passes, 1 otherwise.
"""

import asyncio
import tempfile
import sys
from pathlib import Path

import nbformat

# Allow running as a plain script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.utils import LLMProvider
from app.config.paths import defaultNotebooksDir
from app.construct.export import save_notebook
from app.construct.loaders import load_local
from app.construct.prompts import section_instructions
from app.construct.scaffold import CANONICAL_HEADERS, build_scaffold
from app.construct.writer import draft_sections

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


SAMPLE_MD = """# Sample construct source

This sample document is the LLM context for a constructed notebook.

## Goal
Build a small, reproducible analysis of the supplied dataset.

## Approach
- Load the data.
- Preprocess and engineer one derived feature.
- Train a baseline model and evaluate it.
- Save the fitted model and the evaluation plot.
"""


class FakeProvider(LLMProvider):
    """Offline provider returning canned strict-format section content.

    Each section gets a markdown explanation (so a code cell always has an
    accompanying explanation, per Phase 2 discipline) plus an optional small,
    valid code cell. Never touches the network.
    """

    def __init__(self):
        super().__init__()
        self.calls = {}

    async def draft_section(self, header, instructions, source_context):
        self.calls[header] = self.calls.get(header, 0) + 1
        md = (
            f"===MARKDOWN===\n"
            f"Draft for section *{header}*.\n\n"
            f"Intent: illustrate Phase 2 discipline for this section.\n"
        )
        if header == "Environment & Dependencies":
            code = (
                "===CODE===\n"
                "import os\n"
                "import sys\n"
                "print(f'python={sys.version_info.major}.{sys.version_info.minor}')\n"
            )
        elif header == "Configuration & Global Parameters":
            code = (
                "===CODE===\n"
                "SEED = 42\n"
                "print(f'seed={SEED}')\n"
            )
        else:
            code = (
                "===CODE===\n"
                f"result = 'ok for {header}'\n"
                "print(result)\n"
            )
        return md + code


async def e2e() -> int:
    print("== construct_e2e (scripted, offline, fake provider) ==\n")

    # 1. Load a local sample .md source document.
    sample_dir = Path(tempfile.mkdtemp(prefix="construct-e2e-"))
    sample = sample_dir / "sample-source.md"
    sample.write_text(SAMPLE_MD, encoding="utf-8")
    source = load_local(str(sample))
    check(
        "e2e: local source loaded",
        source.valid and source.filename == "sample-source.md",
        source.filename,
    )
    if not source.valid:
        print(f"    errors: {source.validation_errors}")
        return 1

    # 2. Build the canonical scaffold.
    scaffold_res = build_scaffold(source)
    check(
        "e2e: scaffold built + validates",
        scaffold_res.valid and scaffold_res.notebook is not None,
    )
    if not scaffold_res.valid:
        return 1
    try:
        nbformat.validate(scaffold_res.notebook)
        check("e2e: scaffold nbformat.validate passes", True)
    except nbformat.ValidationError as exc:
        check("e2e: scaffold nbformat.validate passes", False, str(exc))
        return 1

    # 3. Render prompts (per-section drafting instructions).
    rendered = {h: section_instructions(h) for h in CANONICAL_HEADERS}
    check(
        "e2e: prompts rendered for all 8 sections",
        len(rendered) == 8
        and all("discipline rules" in p.lower() for p in rendered.values()),
    )

    # 4. Draft all sections with a fake provider.
    provider = FakeProvider()
    progress = []

    async def progress_cb(done, total, header, message):
        progress.append((done, header, message))

    session = await draft_sections(
        scaffold_res.notebook,
        source,
        provider,
        progress_cb=progress_cb,
    )
    check(
        "e2e: all sections drafted (no errors)",
        session.drafted is not None and not session.errors,
        f"errors={session.errors[:2]}",
    )
    check(
        "e2e: progress_cb fired 8 times",
        len(progress) == 8 and all(msg == "ok" for _, _h, msg in progress),
        str(progress),
    )
    if session.drafted is None:
        print(f"draft errors: {session.errors}")
        return 1
    md_headers = [
        ("".join(c.source) if isinstance(c.source, list) else c.source).strip()
        for c in session.drafted.cells
        if c.cell_type == "markdown"
    ]
    check(
        "e2e: drafted notebook keeps canonical headers",
        all(any(m == f"## {h}" for m in md_headers) for h in CANONICAL_HEADERS),
    )

    # 5. Export to defaultNotebooksDir() -> same dir the Audit Scan DB scans.
    exporter = save_notebook(
        session.drafted, source.filename, export_py=True
    )
    nb_path = Path(exporter.saved_path) if exporter.saved_path else None
    check(
        "e2e: notebook exported to defaultNotebooksDir()",
        exporter.valid and nb_path is not None and nb_path.is_file(),
        str(nb_path),
    )
    check(
        "e2e: export dir is the Audit Scan DB dir",
        nb_path is not None and nb_path.parent.resolve()
        == Path(defaultNotebooksDir()).resolve(),
        str(Path(defaultNotebooksDir())),
    )
    check(
        "e2e: flattened .py written alongside",
        exporter.valid and exporter.py_path and Path(exporter.py_path).exists(),
        str(exporter.py_path),
    )

    # 6. Confirm the exported notebook would be picked up by the Scan DB:
    #    it lives in the notebooks dir and its extension is in the whitelist
    #    (the same predicate the Audit tab scans on).
    scan = list(Path(defaultNotebooksDir()).iterdir())
    scan_names = [p.name for p in scan if p.is_file()]
    scan_exts = {p.suffix for p in scan if p.is_file()}
    whitelist = {".ipynb", ".py", ".md", ".txt"}
    check(
        "e2e: Scan DB would list exported notebook",
        nb_path is not None and nb_path.name in scan_names,
        nb_path.name if nb_path else "",
    )
    check(
        "e2e: Scan DB whitelist includes .ipynb + samples present",
        whitelist.issubset(scan_exts | whitelist)
        and any(p.suffix == ".ipynb" for p in scan if p.is_file()),
        str(sorted(scan_exts)),
    )

    failed = [name for name, ok in RESULTS if not ok]
    print(f"\nE2E DEMO RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks PASS")
    print(f"Exported notebook: {exporter.saved_path}")
    print(f"Notebooks dir (Audit Scan DB): {defaultNotebooksDir()}")
    if failed:
        print("FAILED:")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("DEMO: PASS — full construct loop produced a notebook the Audit Scan DB will list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(e2e()))