# Developer Task Tracking

## Proposals (to implement)

- 1. **LLM-powered auto-repair for `nb-audit`** — Connect an LLM backend to the repair layer so `nb-audit audit` auto-corrects severity>8 findings instead of only detecting + reporting. Today the default patcher is a no-op, so broken notebooks honestly end `FAILED`. Missing piece: a correction generator that turns a `RootCause` + `NotebookModel` IR + cell source into a minimal line-level patch, wired into `controller.py` (its patcher is already injectable). Building blocks already exist in `reference/research/ADWs/fineTunningEnv/automation/nb_audit/`: `semantic/openai_httpx.py` (`LLM_BASE_URL`/`LLM_MODEL`), `semantic/backend.py`, `semantic/prompts.py`, `repair/patches.py`, `repair/root_cause.py`. `--no-llm` must keep degrading to detect + report (LLM outage never flips PASS/FAIL). AC: `nb-audit audit <broken.ipynb>` auto-patches and re-runs until unresolved>8 == 0 → PASS.

- 2.
