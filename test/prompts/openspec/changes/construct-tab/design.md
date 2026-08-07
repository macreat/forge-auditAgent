# Design: Construct Tab — Notebook Construction Framework (Part I)

## Technical Approach

New `app/construct/` package mirroring `app/audit/`: models with return-invalid-not-raise semantics, public-file loaders, an nbformat scaffold, a per-section LLM drafting loop with validation gates. Providers live in `app/api/utils.py` behind an `LLMProvider` ABC selected by the `llmProvider` config key. A 7th Construct panel is driven by a single tab-spec list; exports land in `defaultNotebooksDir()` (dev: `test/prompts/notebooks/`), closing the construct → audit loop. Satisfies all four delta specs.

## Architecture Decisions

| # | Decision | Options | Choice & rationale |
|---|----------|---------|--------------------|
| D1 | Module layout | Single module | Package `app/construct/` (models/loaders/scaffold/prompts/writer/export) — mirrors `app/audit/`, pure logic testable |
| D2 | Loader errors | Raise exceptions | `valid=False` + `validation_errors` (audit/loader.py pattern); spec REQUIRES the contract |
| D3 | Provider interface | Sync httpx; per-provider functions | `async draft_section()` on `LLMProvider` ABC — LLM calls take seconds, must not block the Flet loop |
| D4 | Provider set | Local+OpenAI only | All four (local/openai/anthropic/ollama) — spec REQUIRES four; `ollama` already a dep |
| D5 | Scaffold tool | Hand-written JSON dict | `nbformat` v4 builders — spec REQUIRES `nbformat.validate` gate; pure-Python, PyInstaller-safe |
| D6 | Section format | Free-form; JSON envelope | Fenced `===MARKDOWN===`/`===CODE===` — unambiguously parseable; off-format fails validation → retry |
| D7 | Drafting | Single-shot notebook | Per-section sequential with `progress_cb` — Phase 2 Divide-and-Conquer; retry scoped to one section |
| D8 | Filenames | Timestamp; overwrite | `-v2`/`-v3` suffix on collision — spec-required, deterministic |
| D9 | Key storage | Keychain; env vars | gitignored `~/.test-prompts/config.json`, masked UI, never logged — spec-required |

## Data Flow

```
Construct UI ──load──▶ loaders.py ──▶ SourceDocument
     │                                   │
     ├──scaffold──▶ scaffold.py ──▶ nb (8 headers + env-pin + seeds) [nbformat.validate]
     │                                   │
     ├──draft─────▶ writer.py ──▶ provider.draft_section() per section
     │                    │ (progress_cb → UI; retry once; ast.parse + validate gates)
     │                    └──▶ drafted notebook
     └──save──────▶ export.py ──▶ defaultNotebooksDir()/name[-vN].ipynb
                                     │
                          Audit Scan DB (same dir) ──▶ Audit ──▶ Export PDF
```

## File Changes

Rows marked **"No change (base)"** were listed as changes in the original design but already landed in PR1 (commits `5e40ad4`, `b07a3aa`); they are kept here for reference only. Genuinely new work: `app/construct/`, `app/api/utils.py`, `app/UI/app.py`, plus the PR2 settings permissions hardening.

| File | Action | Description |
|------|--------|-------------|
| `app/construct/{__init__,models,loaders,scaffold,prompts,writer,export}.py` | Create | Package: models, 5 loaders, 8-header scaffold, prompts, drafting loop, export |
| `app/api/utils.py` | Modify | `LLMProvider` ABC + 4 providers + `create_provider(cfg)` |
| `app/config/settings.py` | Modify (PR2: RSK-4 only) | `_DEFAULTS` provider keys already present in base (PR1); PR2 hardens `save()` to owner-only `0o600` permissions (finding RSK-4) |
| `app/config/paths.py` | No change (base) | `defaultNotebooksDir()` already present (PR1, commit `5e40ad4`) |
| `app/UI/app.py` | Modify | Tab-spec single source of truth; 7th Construct panel; async `_run_construct` |
| `requirements.txt` | No change (base) | `nbformat==5.11.0` already pinned (PR1, commit `b07a3aa`) |
| `test-prompts-app.spec` | No change (base) | nbformat `collect_data_files` + hiddenimports already applied (PR1, commit `b07a3aa`) |

## Interfaces / Contracts

```python
@dataclass
class SourceDocument:                 # construct/models.py
    filename: str; source: str; content: str      # local|github|drive|kaggle|http
    valid: bool = True; validation_errors: list[str] = field(default_factory=list)

@dataclass
class ConstructSession:
    source: SourceDocument | None = None
    scaffold: NotebookNode | None = None          # nbformat v4
    drafted: NotebookNode | None = None
    saved_path: str | None = None
    errors: list[str] = field(default_factory=list)

class LLMProvider(ABC):                           # api/utils.py
    @abstractmethod
    async def draft_section(self, header: str, instructions: str,
                            source_context: str) -> str: ...   # raises ProviderError
def create_provider(cfg: dict) -> LLMProvider     # dispatch on cfg["llmProvider"]

# Per-section output: ===MARKDOWN===\n...\n===CODE===\n... (≥1 MARKDOWN, CODE optional)
async def draft_sections(scaffold, source: SourceDocument, provider: LLMProvider,
                         progress_cb=None) -> ConstructSession   # construct/writer.py
```

## Testing Strategy

| Layer | What to test | Approach |
|-------|-------------|----------|
| Unit | Loaders: Drive confirm regex + 2nd request, Kaggle ZIP unwrap/ambiguous, size cap, Content-Disposition, format gate | Pure functions with `httpx.MockTransport`, in-memory ZIPs |
| Unit | Scaffold: 8 headers exact order, env-pin + seeds cells; Writer: strict-format parse, retry-once, `ast.parse` gate, failed section continues | Cell inspection; fake provider with canned/off-format responses |
| Unit | Providers: URL/headers/body for openai/anthropic/ollama | `httpx.MockTransport` asserting request shape |
| Integration | Export: versioned filename; Audit Scan DB lists saved notebook | Temp dir; reuse `_scan_notebooks_db` |
| E2E | Demo: `.md` → scaffold → draft → save → audit → PDF | Manual scripted run (no runner) |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|----------|---------------|-----------------|-------------------|
| Documentation-like/executable paths | Applicable — loaders classify remote content by extension | Whitelist `.ipynb/.py/.md/.txt`; content is inert source text, never executed | Unit: `.sh`/`.pdf`/`.exe` source → `valid=False` |
| Git / VCS / PR boundaries | N/A — no git, VCS, or PR automation in this change | — | — |

## Migration / Rollout

No migration. Additive: new package, new config keys, new tab. Rollback: delete `app/construct/`, revert `app.py` tab list, `settings._DEFAULTS`, `requirements.txt`, `.spec`.

## Open Questions

- [x] ~~`ollamaModel` default when unset: fall back to `"llama3.2"` in `create_provider`, or require user to set it?~~ — **Resolved in PR2**: `create_provider` falls back to `"llama3.2"` (task 2.3; see `app/api/utils.py`).
- [ ] Pre-existing `resultsColumn` shadow in `app.py` (~line 600) — leave untouched? (PR4)
