#!/usr/bin/env python3
"""
Notebook Audit Framework — starting implementation.

Runs the six-pass review protocol against a .ipynb file.

Passes 1, 2, 5 are "mechanical": answerable by parsing the notebook's
JSON/AST directly, no reasoning required.

Passes 3, 4, 6 are "semantic": they require understanding what the code
*means* (is this actually leakage? is this metric appropriate for this
task?). This skeleton stubs them with an LLM call (Claude) so you can
plug in a real API key later — for now it just prints the prompt it
would send.

Usage:
    python audit_notebook.py path/to/notebook.ipynb
    python audit_notebook.py path/to/notebook.ipynb --focus 2 3
    python audit_notebook.py path/to/notebook.ipynb --format json
"""

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Notebook loading
# ---------------------------------------------------------------------------

def load_notebook(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cells(nb: dict):
    """Return list of (index, cell_type, source_text, execution_count)."""
    cells = []
    for i, cell in enumerate(nb.get("cells", [])):
        src = cell.get("source", "")
        text = "".join(src) if isinstance(src, list) else src
        cells.append({
            "index": i,
            "type": cell.get("cell_type"),
            "source": text,
            "exec_count": cell.get("execution_count"),
            "outputs": cell.get("outputs", []),
        })
    return cells


# ---------------------------------------------------------------------------
# Pass 1 — Structural Overview (mechanical)
# ---------------------------------------------------------------------------

CANONICAL_SECTIONS = [
    "Environment & Dependencies", "Configuration", "Data Ingestion",
    "Preprocessing", "Model", "Evaluation", "Artifact Export", "Conclusions",
]


def pass1_structural_overview(cells):
    headers = [c for c in cells if c["type"] == "markdown" and re.match(r"^\s*#{1,3}\s", c["source"])]
    red_flags = []

    if not headers:
        red_flags.append("No markdown section headers found.")

    exec_counts = [c["exec_count"] for c in cells if c["type"] == "code" and c["exec_count"] is not None]
    if exec_counts != sorted(exec_counts):
        red_flags.append("Cell execution order is not linear (out-of-order execution detected).")

    empty_outputs = [c["index"] for c in cells if c["type"] == "code" and not c["outputs"] and c["exec_count"] is not None]
    if empty_outputs:
        red_flags.append(f"Code cells with no outputs despite being executed: {empty_outputs}")

    return {
        "section_map": [h["source"].splitlines()[0].strip() for h in headers],
        "red_flags": red_flags,
    }


# ---------------------------------------------------------------------------
# Pass 2 — Reproducibility Check (mechanical)
# ---------------------------------------------------------------------------

SEED_PATTERNS = [
    r"random\.seed\(", r"np\.random\.seed\(", r"numpy\.random\.seed\(",
    r"torch\.manual_seed\(", r"tf\.random\.set_seed\(", r"set_seed\(",
]

HARDCODED_PATH_PATTERN = re.compile(r"""["'](/(?:Users|home|mnt|C:\\\\)[^"']*)["']""")


def pass2_reproducibility(cells, notebook_dir: Path):
    code = "\n".join(c["source"] for c in cells if c["type"] == "code")

    seeds_found = [p for p in SEED_PATTERNS if re.search(p, code)]
    hardcoded_paths = HARDCODED_PATH_PATTERN.findall(code)

    dep_files = [f for f in ["requirements.txt", "environment.yml", "pyproject.toml"]
                 if (notebook_dir / f).exists()]

    issues = []
    if not seeds_found:
        issues.append("No random seed calls detected.")
    if not dep_files:
        issues.append("No dependency file (requirements.txt / environment.yml / pyproject.toml) found alongside notebook.")
    if hardcoded_paths:
        issues.append(f"Hardcoded absolute paths found: {hardcoded_paths[:5]}")

    if len(issues) == 0:
        risk = "Low Risk"
    elif len(issues) == 1:
        risk = "Moderate Risk"
    else:
        risk = "High Risk"

    return {
        "seeds_found": seeds_found,
        "dependency_files_found": dep_files,
        "hardcoded_paths": hardcoded_paths,
        "issues": issues,
        "risk_score": risk,
    }


# ---------------------------------------------------------------------------
# Pass 5 — Code Quality Review (mechanical)
# ---------------------------------------------------------------------------

def _normalize(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def pass5_code_quality(cells):
    code_cells = [c for c in cells if c["type"] == "code"]
    full_code = "\n".join(c["source"] for c in code_cells)

    # unused imports via AST
    unused_imports = []
    try:
        tree = ast.parse(full_code)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names.update(alias.asname or alias.name for alias in node.names)
        used_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        unused_imports = sorted(imported_names - used_names)
    except SyntaxError as e:
        unused_imports = [f"<could not parse: {e}>"]

    # crude repeated-block detection: normalize each code cell, hash, count duplicates
    normalized_blocks = [_normalize(c["source"]) for c in code_cells if c["source"].strip()]
    block_counts = Counter(normalized_blocks)
    repeated_blocks = [block[:60] + "..." for block, count in block_counts.items() if count >= 3]

    bloated_outputs = []
    for c in code_cells:
        for out in c["outputs"]:
            text = out.get("text") or out.get("data", {}).get("text/plain", "")
            text_len = len("".join(text)) if isinstance(text, list) else len(str(text))
            if text_len > 5000:
                bloated_outputs.append(c["index"])

    return {
        "unused_imports": unused_imports,
        "repeated_blocks_ge_3": repeated_blocks,
        "bloated_output_cells": bloated_outputs,
    }


# ---------------------------------------------------------------------------
# Passes 3, 4, 6 — Semantic (require LLM reasoning)
# ---------------------------------------------------------------------------

SEMANTIC_PASS_PROMPTS = {
    3: """Review this notebook's code for DATA INTEGRITY issues:
- Is train/test split performed BEFORE any preprocessing (scaling, imputation, encoding)?
- Is there evidence of data leakage (e.g. fit_transform on full dataset before split)?
- Is missing data handled consistently across train/test?
Respond with a short data pipeline integrity report.

--- CODE ---
{code}
""",
    4: """Review this notebook's code for ML CORRECTNESS:
- Is the evaluation metric appropriate for the task and class distribution?
- Is cross-validation implemented correctly, without leakage?
- Is hyperparameter tuning done only on validation data, never test?
- Is there a baseline comparison?
Respond with a short ML correctness checklist.

--- CODE ---
{code}
""",
    6: """Review this notebook for DEPLOYMENT READINESS:
- Are model artifacts saved with versioned filenames?
- Is inference logic separable from training logic?
- Are compute/memory constraints documented?
- Any PII or data privacy concerns?
Respond with Low/Moderate/High readiness score and reasoning.

--- CODE ---
{code}
""",
}


def run_semantic_pass(pass_num: int, cells, api_key: str | None):
    code = "\n\n".join(f"# Cell {c['index']}\n{c['source']}" for c in cells if c["type"] == "code")
    prompt = SEMANTIC_PASS_PROMPTS[pass_num].format(code=code[:12000])  # truncate for safety

    if not api_key:
        return {
            "status": "skipped (no ANTHROPIC_API_KEY set)",
            "prompt_preview": prompt[:300] + "...",
        }

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return {"status": "completed", "result": text}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

PASS_NAMES = {
    1: "Structural Overview",
    2: "Reproducibility Check",
    3: "Data Integrity Review",
    4: "ML Correctness Audit",
    5: "Code Quality Review",
    6: "Deployment Readiness",
}


def run_audit(notebook_path: Path, focus_passes: list[int] | None, api_key: str | None):
    nb = load_notebook(notebook_path)
    cells = get_cells(nb)
    passes_to_run = focus_passes or list(range(1, 7))

    results = {}
    if 1 in passes_to_run:
        results[1] = pass1_structural_overview(cells)
    if 2 in passes_to_run:
        results[2] = pass2_reproducibility(cells, notebook_path.parent)
    if 3 in passes_to_run:
        results[3] = run_semantic_pass(3, cells, api_key)
    if 4 in passes_to_run:
        results[4] = run_semantic_pass(4, cells, api_key)
    if 5 in passes_to_run:
        results[5] = pass5_code_quality(cells)
    if 6 in passes_to_run:
        results[6] = run_semantic_pass(6, cells, api_key)

    return results


def print_report(results: dict):
    for pass_num, data in results.items():
        print(f"\n{'=' * 60}")
        print(f"PASS {pass_num}: {PASS_NAMES[pass_num]}")
        print("=" * 60)
        for key, value in data.items():
            print(f"\n[{key}]")
            print(value if isinstance(value, str) else json.dumps(value, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Run the six-pass Notebook Audit Framework.")
    parser.add_argument("notebook", type=Path, help="Path to .ipynb file")
    parser.add_argument("--focus", type=int, nargs="+", choices=range(1, 7),
                         help="Only run specific pass numbers, e.g. --focus 2 3")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--api-key", default=None, help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    args = parser.parse_args()

    import os
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")

    if not args.notebook.exists():
        print(f"Error: {args.notebook} not found", file=sys.stderr)
        sys.exit(1)

    results = run_audit(args.notebook, args.focus, api_key)

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print_report(results)


if __name__ == "__main__":
    main()