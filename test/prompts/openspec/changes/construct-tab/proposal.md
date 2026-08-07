# Proposal: Construct Tab — Notebook Construction Framework (Part I)

## Intent

Implement Construction Framework Part I (`reference/docs/mds/NotebookBuildAudit.md` lines 16-75) as a new "Construct" tab: load a source document (local/cloud) → generic notebook skeleton → LLM-draft sections → save/export. Value: consistent, reviewable team templates plus a closed construct → audit loop (constructed notebooks appear in the Audit tab's Scan DB).

## Scope

### In Scope

- 7th "Construct" tab in `app/UI/app.py` (keep `panels[]`/`tabs[]` in sync; async via `page.run_task`)
- Loaders: GitHub raw, local file, Drive (public), Kaggle (public), generic HTTP; `.ipynb`/`.py`/`.md`/`.txt` only
- Generic skeleton: 8 canonical markdown headers + environment-pin + reproducibility/seeds cells; source passed to LLM as context, never mapped into structure
- LLM drafting via provider strategy in `app/api/utils.py` with all four providers (**Local** llama.cpp, **OpenAI**, **Anthropic**, **Ollama**), one section at a time; validated via `nbformat.validate` + `ast.parse`; external providers require an explicit source-transmission disclosure
- Export to `test/prompts/notebooks/` (Audit Scan DB dir); new config keys (`llmProvider`, API keys, `ollamaModel`), masked in UI

### Out of Scope

Domain parsing; source-structure mapping; OAuth/private files; PDF ingestion; Phase 3 validation loop; docs toctree updates.

## Capabilities

> No existing specs — all New.

### New Capabilities

- `construct-source-loading`: local + cloud loaders, invalid-object returns (audit/loader.py pattern), format gating
- `notebook-scaffold`: nbformat-based skeleton — 8 headers, env-pin, seeds cells
- `llm-section-drafting`: provider strategy, prompts, per-section drafting, validation gates
- `construct-export`: save validated `.ipynb` to `NOTEBOOKS_DIR`

### Modified Capabilities

None.

## Approach

New package `test/prompts/app/construct/` (`models.py`, `loaders.py`, `scaffold.py`, `prompts.py`, `writer.py`, `export.py`), mirroring `app/audit/`: dataclasses, loaders return `valid=False` + errors (not exceptions), `httpx.get(timeout=30, follow_redirects=True)`, pipeline with `progress_cb`. Skeleton via `nbformat` (add to `requirements.txt`; PyInstaller-safe). Providers in `app/api/utils.py` per explore #68/#69; cloud quirks (Drive confirm token, Kaggle zip unwrap) in `loaders.py`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `test/prompts/app/construct/` | New | Full package |
| `test/prompts/app/api/utils.py` | Modified | LLM provider strategy |
| `test/prompts/app/UI/app.py` | Modified | 7th tab; panels/tabs sync |
| `test/prompts/app/config/settings.py` | Modified | Provider/key config keys |
| `test/prompts/requirements.txt` | Modified | Add `nbformat` |
| `test/prompts/notebooks/` | Modified | Audit Scan DB target |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cloud loader breakage (Drive token, Kaggle zip, redirects) | Med | Follow #69; invalid-object errors |
| LLM emits invalid code | Med | Validation gates; one retry per section |
| API keys in plaintext config | Med | Local-first, gitignored, masked in UI |
| Tab regression (panels/tabs sync) | Low | Single source-of-truth list |

## Rollback Plan

Revert `app.py` tab arrays to 6 tabs; delete `app/construct/`; revert `settings.py` schema and `requirements.txt`. Additive — no data migration.

## Dependencies

- `nbformat` (PyInstaller-safe; CI installs via `pip install -r requirements.txt`)
- External API keys optional — Local provider works offline
## Success Criteria

- [ ] All four demo sources (GitHub, local, Drive, Kaggle) load and scaffold end-to-end
- [ ] Every skeleton has the 8 canonical headers + env-pin + seeds cells
- [ ] Drafted notebooks pass `nbformat.validate`; all code cells pass `ast.parse`
- [ ] Constructed notebooks appear in Audit tab Scan DB; Local + ≥1 external provider produce sections

## Open Questions

Both open questions are **resolved**:

- ~~OllamaProvider in v1 (dep present) or defer?~~ → **Resolved: Ollama in v1**, as one of the four providers in the provider strategy — see `specs/llm-section-drafting/spec.md` ("Provider strategy") and `design.md` D4.
- ~~Drafting loop: per-section (recommended, matches Phase 2 discipline) vs single-shot — confirm in specs~~ → **Resolved: per-section sequential loop**, matching Phase 2 Divide-and-Conquer discipline — see `specs/llm-section-drafting/spec.md` ("Per-section sequential drafting") and `design.md` D7.
