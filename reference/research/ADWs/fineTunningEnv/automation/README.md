# nb-audit

Automated ML notebook audit & repair pipeline. `nb-audit` takes a Jupyter
notebook as input, audits it for experimental-validity problems (data leakage,
split overlap, missing checkpoint restoration, metric misuse, non-reproducible
splits, unsupported conclusions, …), and produces a repeatable QA report. The
original notebook is never modified; every run is preserved under
`audit-runs/<timestamp>/`.

The pipeline is deterministic and LLM-free by default (`static` and `--no-llm`);
the semantic LLM auditor is an optional, strictly-additive signal that can only
*add* findings and never flips PASS/FAIL on outage.

## Installation

```bash
python -m venv venv
venv/bin/pip install -e .
```

This installs the `nb-audit` console script (or run `python -m nb_audit.cli`
as an equivalent entry point).

## Usage

Four subcommands:

```bash
# Full audit → patch → execute → QA → re-audit loop (writes audit.json + report.md).
nb-audit audit notebook.ipynb

# Deterministic, LLM-free static audit (syntax / AST / API misuse).
nb-audit static notebook.ipynb

# Execute the notebook in a fresh kernel and report the status.
nb-audit execute notebook.ipynb

# Re-emit report.md + audit.json from a persisted run.
nb-audit report <run-id>          # run id under audit-runs/
nb-audit report audit-runs/<run-id>
```

### Flags

| Flag | Applies to | Effect |
|------|-----------|--------|
| `--config FILE` | `audit`, `static`, `execute` | Load a YAML config file. |
| `--max-iterations N` | `audit` | Cap on audit/patch/execute iterations (default 10). |
| `--severity-threshold N` | `audit` | Severity above which a finding blocks PASS (default 8). |
| `--no-llm` | `audit` | Disable the semantic LLM auditor (static-only). |
| `--allow-network` | `audit`, `execute` | Allow the notebook to reach the network. |

Example:

```bash
nb-audit audit notebook.ipynb --no-llm --max-iterations 3
```

Exit codes: `audit` exits `0` on PASS and `1` on FAILED (and on a missing input
or missing run directory). `static` exits `0` (findings are informational).

## Configuration

Values resolve with precedence `defaults < config.yaml < env (NB_AUDIT_*) < cli`.
A missing config file resolves to the defaults.

### YAML

```yaml
audit:
  severity_threshold: 8
  max_iterations: 10
  execute_notebook: true
  preserve_original: true

llm:
  model: <configured-model>   # empty → static-only
  base_url: <openai-compatible base URL>
  temperature: 0

execution:
  timeout_seconds: 3600
  allow_network: false
  kernel_name: python3

qa:
  require_clean_execution: true
  require_artifacts: true
  require_reproducibility_checks: true
```

### Environment variables

Every setting is overridable via `NB_AUDIT_*`:

`NB_AUDIT_SEVERITY_THRESHOLD`, `NB_AUDIT_MAX_ITERATIONS`,
`NB_AUDIT_EXECUTE_NOTEBOOK`, `NB_AUDIT_PRESERVE_ORIGINAL`,
`NB_AUDIT_LLM_MODEL`, `NB_AUDIT_LLM_BASE_URL`, `NB_AUDIT_LLM_TEMPERATURE`,
`NB_AUDIT_LLM_MAX_RETRIES`, `NB_AUDIT_EXECUTION_TIMEOUT_SECONDS`,
`NB_AUDIT_EXECUTION_ALLOW_NETWORK`, `NB_AUDIT_EXECUTION_KERNEL_NAME`,
`NB_AUDIT_QA_REQUIRE_CLEAN_EXECUTION`, `NB_AUDIT_QA_REQUIRE_ARTIFACTS`,
`NB_AUDIT_QA_REQUIRE_REPRODUCIBILITY_CHECKS`.

## Sandbox caveat (important)

**There is no real sandbox.** `--allow-network` defaults to `false` and is
enforced **by convention**, through three cooperating mechanisms — the kernel is
launched with `IPY_ALLOW_NETWORK=0`/`NB_AUDIT_ALLOW_NETWORK=0`, its working
directory is a dedicated per-run directory, and a fresh kernel is started per
execution. A malicious notebook can still read the host filesystem or open
sockets under the same UID. Treat `nb-audit` as a data-integrity tool, not a
security boundary; do not run untrusted notebooks expecting isolation.

## Rollback note

Each run is immutable on disk under `audit-runs/<timestamp>/`:
`original.ipynb` (byte-identical copy), `final.ipynb`, `iterations/`,
`audits/`, `artifacts/`, `logs/`, `audit.json`, and `report.md`. Nothing in a
run directory is overwritten across runs — a new run gets a new timestamp — so
rolling back a mistaken patch is a matter of inspecting the previous run's
`iterations/` and re-running from the original. The source notebook is never
touched.

## Development

```bash
# Unit + integration tests (CPU-only, LLM-free).
venv/bin/python -m pytest -q
```

Deliberately broken fixtures live under `tests/fixtures/`; their corrected
counterparts (`*_fixed.ipynb`) back the regression tests that prove a fixed
issue's severity>8 signature is absent.
