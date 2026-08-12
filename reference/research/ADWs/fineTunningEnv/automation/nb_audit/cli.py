"""CLI for nb-audit (typer app).

Subcommands:

* ``audit``  — run the full audit → patch → execute → QA → re-audit loop (§21)
  and write ``audit.json`` + ``report.md`` to a timestamped run directory.
* ``static`` — run the deterministic, LLM-free static audit and print findings.
* ``execute`` — execute the notebook in a fresh kernel and report the status.
* ``report`` — re-emit ``report.md`` + ``audit.json`` from a persisted run.

Flag → config mapping (resolver precedence ``defaults < yaml < env < cli``):

    --config FILE           → AuditConfig.load(yaml_path=FILE, ...)
    --max-iterations N      → audit.max_iterations
    --severity-threshold N  → audit.severity_threshold
    --no-llm                → disable the semantic LLM backend (static-only)
    --allow-network         → execution.allow_network = true

The semantic LLM backend is attached only when a model/base_url is configured
(via ``NB_AUDIT_LLM_*`` or yaml) AND ``--no-llm`` is absent; otherwise the
pipeline degrades to static-only. Because the semantic signal is strictly
additive (an LLM outage yields no findings), an LLM outage can never flip
PASS/FAIL. ``--allow-network`` defaults to ``false`` and is enforced **by
convention** (see the execute module docstring) — this is not a security sandbox.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional

import typer

from nb_audit.config import AuditConfig
from nb_audit.controller import PASS, AuditController, AuditOutcome
from nb_audit.execute import SUCCESS, NotebookExecutor
from nb_audit.io import NotebookManager
from nb_audit.ir import NotebookModel, NotebookParser
from nb_audit.models import Finding
from nb_audit.report import (
    build_report_documents,
    load_audit_json,
    render_markdown,
    write_report_documents,
)

app = typer.Typer(
    name="nb-audit",
    help="Automated ML notebook audit & repair pipeline.",
    no_args_is_help=True,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _resolve_config(
    config_path: Optional[str] = None,
    *,
    max_iterations: Optional[int] = None,
    severity_threshold: Optional[int] = None,
    allow_network: Optional[bool] = None,
) -> AuditConfig:
    """Resolve config per precedence: defaults < yaml < env < cli flags."""
    cli: dict = {}
    if max_iterations is not None:
        cli.setdefault("audit", {})["max_iterations"] = max_iterations
    if severity_threshold is not None:
        cli.setdefault("audit", {})["severity_threshold"] = severity_threshold
    if allow_network:
        # A boolean flag can only force true; the default is already false.
        cli.setdefault("execution", {})["allow_network"] = True
    return AuditConfig.load(yaml_path=config_path, cli=cli)


def _parse_model(notebook: Path) -> NotebookModel:
    try:
        return NotebookParser().parse_file(str(notebook))
    except Exception as exc:  # NotebookParseError / OSError
        typer.echo(f"Error: cannot parse notebook {notebook}: {exc}", err=True)
        raise typer.Exit(1) from exc


def _build_backend(config: AuditConfig, no_llm: bool):
    """Attach the semantic LLM backend, or ``None`` for static-only."""
    if no_llm:
        return None
    if config.llm.model or config.llm.base_url:
        from nb_audit.semantic.openai_httpx import HttpxOpenAIBackend

        return HttpxOpenAIBackend.from_config(config)
    return None


def _print_findings(findings: list[Finding]) -> None:
    if not findings:
        typer.echo("No findings.")
        return
    for finding in findings:
        location = finding.location
        where = (
            location.cell if location.line is None
            else f"{location.cell}:{location.line}"
        )
        typer.echo(
            f"[{finding.id}] severity={finding.severity} {finding.category} "
            f"@ {where or '-'}: {finding.issue}"
        )
    typer.echo(f"{len(findings)} finding(s).")


def _run_audit_outcome(
    notebook: Path, config: AuditConfig, no_llm: bool
) -> tuple[AuditOutcome, NotebookManager]:
    """Run the controller over ``notebook`` and return (outcome, run manager)."""
    model = _parse_model(notebook)
    manager = NotebookManager(notebook, config=config)
    backend = _build_backend(config, no_llm)
    controller = AuditController(
        config=config, backend=backend, run_dir=manager.run_dir
    )
    outcome = controller.run(model)
    return outcome, manager


def _resolve_run_dir(run: Path) -> Path:
    """Resolve a run argument to an existing run directory.

    Accepts either a run id under ``audit-runs/`` or a path to a run directory
    (spec §23 shows ``nb-audit report audit-runs/<run-id>``).
    """
    candidate = Path(run)
    if candidate.is_dir():
        return candidate.resolve()
    under = Path("audit-runs") / str(run)
    if under.is_dir():
        return under.resolve()
    typer.echo(f"Error: run directory not found: {run}", err=True)
    raise typer.Exit(1)


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #
@app.command()
def audit(
    notebook: Path = typer.Argument(..., help="Path to the .ipynb notebook."),
    config: Optional[Path] = typer.Option(
        None, "--config", help="YAML config file."
    ),
    max_iterations: Optional[int] = typer.Option(
        None, "--max-iterations", help="Cap on audit/patch/execute iterations."
    ),
    severity_threshold: Optional[int] = typer.Option(
        None, "--severity-threshold", help="Severity above which a finding blocks."
    ),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Disable the semantic LLM auditor (static-only)."
    ),
    allow_network: bool = typer.Option(
        False,
        "--allow-network",
        help="Allow the notebook to reach the network (off by convention).",
    ),
) -> None:
    """Run the full audit → patch → execute → QA → re-audit loop."""
    cfg = _resolve_config(
        str(config) if config else None,
        max_iterations=max_iterations,
        severity_threshold=severity_threshold,
        allow_network=allow_network,
    )
    outcome, manager = _run_audit_outcome(notebook, cfg, no_llm)
    docs = build_report_documents(outcome, cfg.audit.severity_threshold)
    json_path, md_path = write_report_documents(docs, manager.run_dir)

    typer.echo(docs.audit_json["summary"])
    typer.echo(f"Run directory: {manager.run_dir}")
    typer.echo(f"Report: {md_path}")
    typer.echo(f"Audit JSON: {json_path}")
    raise typer.Exit(0 if outcome.status == PASS else 1)


@app.command()
def static(
    notebook: Path = typer.Argument(..., help="Path to the .ipynb notebook."),
    config: Optional[Path] = typer.Option(
        None, "--config", help="YAML config file."
    ),
) -> None:
    """Run the deterministic, LLM-free static audit and print findings."""
    _resolve_config(str(config) if config else None)
    model = _parse_model(notebook)

    from nb_audit.static import default_registry

    findings = default_registry().run(model)
    _print_findings(findings)
    raise typer.Exit(0)


@app.command()
def execute(
    notebook: Path = typer.Argument(..., help="Path to the .ipynb notebook."),
    config: Optional[Path] = typer.Option(
        None, "--config", help="YAML config file."
    ),
    allow_network: bool = typer.Option(
        False,
        "--allow-network",
        help="Allow the notebook to reach the network (off by convention).",
    ),
) -> None:
    """Execute the notebook in a fresh kernel and report the status."""
    cfg = _resolve_config(
        str(config) if config else None, allow_network=allow_network
    )
    model = _parse_model(notebook)

    run_dir = Path(tempfile.mkdtemp(prefix="nb-audit-exec-"))
    executor = NotebookExecutor(config=cfg, run_dir=run_dir)
    result = executor.execute_sync(model.to_notebook())

    if result.finding is not None:
        _print_findings([result.finding])
    typer.echo(f"Execution: {result.status}")
    raise typer.Exit(0 if result.status == SUCCESS else 1)


@app.command()
def report(
    run: Path = typer.Argument(
        ..., help="Run id under audit-runs/, or a path to a run directory."
    ),
) -> None:
    """Re-emit report.md + audit.json from a persisted audit run."""
    run_dir = _resolve_run_dir(run)
    try:
        doc = load_audit_json(run_dir)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    markdown = render_markdown(doc)
    md_path = run_dir / "report.md"
    json_path = run_dir / "audit.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    typer.echo(doc.get("summary") or "")
    typer.echo(f"Report: {md_path}")
    typer.echo(f"Audit JSON: {json_path}")
    raise typer.Exit(0)


if __name__ == "__main__":  # pragma: no cover - ``python -m nb_audit.cli``
    app()
