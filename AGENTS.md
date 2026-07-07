# AGENTS.md — forge-auditAgent

## Repo status

This is an early-stage design/documentation project. There is **no runnable code, no build system, no test suite, and no package manager** yet.

## Key directories

### Design & Reference

- `reference/docs/mds/NotebookBuildAudit.md` — authoritative Construction Framework (3-phase build discipline) and Audit Framework (six-pass notebook review protocol, three-level LLM prompt templates)
- `reference/docs/latex/NotebookBuildAudit.tex` — formal LaTeX spec with diagrams, full prompt templates, and structural trees for both frameworks
- `reference/docs/mds/basis.md` — early design notes summarizing the Construction/Audit Frameworks at a higher level
- `reference/docs/latex/basis.tex` — early LaTeX notes and prompt draft iterations (superseded by NotebookBuildAudit.tex)

### Proposals

- `reference/docs/InitialProposalDev.md` — commercial software development proposal for the Notebook Build Audit & Execution System (FastAPI, Vite+React+TS, Docker, Ollama/OpenAI hybrid LLM, @jupyter-kit)
- `reference/docs/InitialProposalDev.tex` — LaTeX version of the same proposal (compiles to PDF via `latexmk -pdf` then `latexmk -c` for cleanup)
- `reference/docs/InitialProposalDev.pdf` — compiled PDF of the proposal

### Project Management

- `reference/flags/flags.md` — developer task tracking; add/update entries when new work is scoped
- `.agents/skills/sw-development-proposal/SKILL.md` — SKILL.md template blueprint for generating structured software development proposals
- `tools/` — reserved for future tooling; currently empty

## Notable repo quirks

- The root `README.md` is a mostly unfilled template skeleton. The real design content lives under `reference/docs/`.
- `.skills/` and `.tools/` exist in git history but have been reorganized into `.agents/skills/` and `tools/` on the filesystem. Do not recreate the old dot-prefixed dirs.
- There are no CI workflows, no lint/format/typecheck configs, and no dependency manifests.
