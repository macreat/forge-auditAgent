# Tasks: Construct Tab — Notebook Construction Framework (Part I)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,300–1,500 (7 new construct modules + utils.py + app.py + settings/paths + requirements + 2 .spec files + README) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 Foundation → PR2 Providers → PR3 Construct core → PR4 UI + docs |
| Delivery strategy | ask-on-risk |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Config + packaging: settings keys, paths.defaultNotebooksDir, nbformat dep, both .spec fixes | PR 1 | `venv/bin/python3 -c "import app.config.settings, app.config.paths"` | GUI: Settings tab shows new fields | Revert settings.py, paths.py, requirements.txt, both .spec |
| 2 | Providers in api/utils.py: ABC + 4 impls + create_provider | PR 2 | Import-smoke + MockTransport probe script | hello_llm.py against running local server | Revert app/api/utils.py |
| 3 | Construct core: models, loaders, scaffold, prompts, writer, export | PR 3 | Import-smoke + probe script (fake provider, in-memory ZIPs) | Scripted demo: .md → scaffold → draft → save | Delete app/construct/ |
| 4 | UI: TAB_SPEC refactor, 7th tab, masked keys + provider dropdown, async _run_construct, README | PR 4 | `venv/bin/python3 -m py_compile app/UI/app.py` | GUI full demo; Audit Scan DB lists notebook | Revert app/UI/app.py + README |

## Phase 1: Foundation & Packaging

- [x] 1.1 requirements.txt: add pinned `nbformat` (R11)
- [x] 1.2 settings.py `_DEFAULTS`: +`llmProvider`, `openaiApiKey`, `anthropicApiKey`, `ollamaModel` (R19)
- [x] 1.3 paths.py: `defaultNotebooksDir()` + `userNotebooksDir()` dev-vs-deploy (R20)
- [x] 1.4 test-prompts-app.spec: `collect_data_files("nbformat")` + hiddenimports `nbformat.validator`, `fastjsonschema`, `jsonschema` — HIGH risk (R11)
- [x] 1.5 test-prompts-installer.spec: same nbformat fix (R11)

## Phase 2: Providers

- [x] 2.1 utils.py: `LLMProvider` ABC — async `draft_section(header, instructions, source_context) -> str`, raises `ProviderError` (R14)
- [x] 2.2 utils.py: implement Local (llama.cpp), OpenAI, Anthropic (`/v1/messages`, `x-api-key`, separate system), Ollama (localhost:11434) via httpx (R14)
- [x] 2.3 utils.py: `create_provider(cfg)` dispatch on `llmProvider`; `ollamaModel` falls back to `"llama3.2"`; keys never in prompts (R14, R19)
- [x] 2.4 Probes: `tools/provider_probe.py` MockTransport asserting URL/headers/body per provider; keys masked, never logged (R19)
- [x] 2.5 settings.py: config JSON written with owner-only `0o600` permissions (RSK-4)
- [x] 2.6 llm-section-drafting spec: `ProviderError` → retry-once semantics + per-request timeout; exact `===MARKDOWN===`/`===CODE===` grammar; external-provider disclosure + default `local` (RSL-1/RLB-3, RDB-8/RLB-2, RSK-3)
- [x] 2.7 proposal.md: list all four providers in scope; mark open questions resolved with spec/design pointers (RDB-1/RLB-8)
- [x] 2.8 design.md: File Changes table reflects base state (config keys, `defaultNotebooksDir()`, nbformat, .spec already present) (RDB-3/RLB-7)

## Phase 3: Construct Core

- [x] 3.1 construct/__init__.py + models.py: `SourceDocument`, `ConstructSession` (R1)
- [x] 3.2 loaders.py: format gate whitelist `.ipynb/.py/.md/.txt` + `load_local()` return-invalid-not-raise (R2, R3)
- [x] 3.3 loaders.py: `load_github()` blob→raw normalize, `httpx.get(timeout=30, follow_redirects=True)`, 404→invalid (R4)
- [x] 3.4 loaders.py: `load_http()` Content-Disposition parse + streamed size cap 10–50 MB (R7)
- [x] 3.5 loaders.py: `load_drive()` 4 URL forms, confirm-token second GET, permission→invalid (R5)
- [x] 3.6 loaders.py: `load_kaggle()` zip-unwrap single text member, ambiguous→invalid (R6)
- [x] 3.7 scaffold.py: 8 canonical headers exact order, env-pin cell, seeds cell (R8, R9, R10)
- [x] 3.8 scaffold.py: nbformat v4 + `nbformat.validate` gate; source context-only (R11, R12)
- [x] 3.9 prompts.py: per-section prompts encoding Phase 2 discipline rules (R13)
- [x] 3.10 writer.py: `parse_section_output` strict `===MARKDOWN===`/`===CODE===` (R16)
- [x] 3.11 writer.py: `draft_sections` sequential + `progress_cb`, retry-once, `ast.parse` per code cell, failed section recorded, run continues (R15, R17, R18)
- [x] 3.12 export.py: `save_notebook` → `defaultNotebooksDir()`, mkdir, `-vN` versioned names, saved path (R20, R21)
- [x] 3.13 export.py: optional flattened `.py` (concatenated code cells) (R22)

## Phase 4: UI Wiring

- [ ] 4.1 app.py: single `TAB_SPEC` list driving `panels[]` + `ft.Tabs`; keep 6 existing tabs working (regression guard)
- [ ] 4.2 app.py settings panel: provider dropdown + masked key fields (`password=True`), save wiring, never logged (R19)
- [ ] 4.3 app.py: Construct panel — source input/type, loader selector, scaffold/draft/export buttons, `.py` opt-in (R23)
- [ ] 4.4 app.py: async `_run_construct` via `page.run_task`, `progress_cb` updates, success/failure surfaced; register 7th tab via `TAB_SPEC` (R15, R23)

## Phase 5: Verification & Docs

- [ ] 5.1 Import-smoke all new modules (config verify command)
- [ ] 5.2 Loader probes: missing file, unsupported ext, `.sh/.pdf/.exe`→invalid (threat matrix), github normalize, drive confirm, kaggle ambiguous, size cap, Content-Disposition (R1–R7)
- [ ] 5.3 Scaffold probe: headers order, cell placement, `nbformat.validate` passes (R8–R12)
- [ ] 5.4 Writer probe: fake provider canned/off-format, retry-once, `ast.parse` reject, failure continues (R15–R18)
- [ ] 5.5 Export probe: versioned names, dir creation, `.py` opt-in (R20–R22)
- [ ] 5.6 Scripted E2E demo: `.md` → scaffold → draft (local) → save → Audit Scan DB lists it; README usage note (R23)

Traceability: R1–R7 source-loading (14 scenarios), R8–R13 scaffold (8), R14–R19 drafting (11), R20–R23 export (8) = 23 req / 41 scenarios. TDD inactive: probes are ad-hoc scripts, no runner. House style: return-invalid-not-raise loaders, `httpx.get(timeout=30, follow_redirects=True)`, pure functions for scaffold/prompts/validation.
