# LLM Section Drafting Specification

## Purpose

Draft each scaffolded section's content through an LLM provider strategy, one section at a time, with strict output-format enforcement and validation gates (`nbformat.validate` + `ast.parse` per code cell) before acceptance.

## Requirements

### Requirement: Provider strategy

The drafting pipeline MUST use a provider strategy with four implementations exposing a common interface (e.g., `draft_section(...) -> str`): **LocalProvider** (in-process llama.cpp OpenAI-compatible endpoint via `httpx`), **OpenAIProvider** (OpenAI-compatible API via `httpx`), **AnthropicProvider** (`/v1/messages` with `x-api-key` header and separate system field), and **OllamaProvider** (`localhost:11434` OpenAI-compatible; `ollama` already a dependency). The active provider MUST be selected by the `llmProvider` config key, whose default value MUST be `local`.

Every provider MUST enforce a per-request timeout (default 60 seconds) and MUST raise a typed `ProviderError` on transport, HTTP, or parse failures. Error messages MUST NOT contain API keys, full request bodies, or full response bodies. A `ProviderError` counts as a validation failure for the retry-once rule (see "Retry on validation failure").

#### Scenario: Local provider drafts offline

- GIVEN `llmProvider=local` and the in-process server running
- WHEN the pipeline drafts a section
- THEN the section text is produced from the local llama.cpp endpoint

#### Scenario: Anthropic provider uses messages API

- GIVEN `llmProvider=anthropic` and a configured key
- WHEN the pipeline drafts a section
- THEN the request hits `/v1/messages` with the `x-api-key` header
- AND the system prompt is sent in the separate system field

#### Scenario: Provider failure raises typed error

- GIVEN a provider that is unreachable or returns an HTTP error
- WHEN the pipeline calls `draft_section`
- THEN a typed `ProviderError` is raised
- AND the error message does not contain API keys or full request/response bodies

#### Scenario: Default provider is local

- GIVEN a fresh configuration with no `llmProvider` value
- WHEN the provider is created
- THEN the active provider is the local provider

### Requirement: Per-section sequential drafting

The pipeline MUST draft sections sequentially, one section at a time (Divide and Conquer, Phase 2 discipline), in canonical order. It MUST accept a progress callback invoked after each section completes.

#### Scenario: Sections drafted one at a time

- GIVEN a scaffolded notebook with 8 sections
- WHEN drafting runs
- THEN sections are drafted in canonical order, one at a time, with the progress callback invoked after each

#### Scenario: Section failure does not abort the run

- GIVEN a section that fails twice for any reason (validation failure or `ProviderError`)
- WHEN drafting continues
- THEN the failed section is recorded as a draft error and the next section is drafted

### Requirement: Strict output format

Each provider MUST return output in the strict per-section format defined below, which the pipeline parses into cells unambiguously. Non-conforming output MUST be treated as a validation failure for retry purposes.

Grammar (line-based):

- A section consists of one or more blocks, each introduced by a marker line.
- Markers: `===MARKDOWN===` (markdown cell) and `===CODE===` (code cell), each alone on its own line.
- Every section output MUST contain at least one `===MARKDOWN===` block. `===CODE===` blocks are optional.
- Blocks are repeatable in any order; each MARKDOWN block becomes one markdown cell and each CODE block becomes one code cell, preserving output order.
- The line after a marker begins that block's content; the block ends at the next marker line (or at end of output).
- Content lines are taken verbatim. To include a literal line equal to a marker inside content, escape it by prefixing `\` (e.g., `\===CODE===`); the parser removes exactly one leading backslash from the escaped line.

#### Scenario: Parsable output accepted

- GIVEN provider output in the strict format
- WHEN the pipeline parses it
- THEN the markdown and code cells are extracted without ambiguity

#### Scenario: Off-format output fails validation

- GIVEN provider output that does not match the strict format
- WHEN the pipeline validates it
- THEN the section fails validation and the retry rule applies

#### Scenario: Missing MARKDOWN block fails validation

- GIVEN provider output containing only CODE blocks
- WHEN the pipeline validates it
- THEN the section fails validation and the retry rule applies

#### Scenario: Escaped marker line kept verbatim

- GIVEN a content line equal to a marker escaped as `\===CODE===`
- WHEN the pipeline parses the block
- THEN the line is kept as literal content `===CODE===` inside the cell

### Requirement: Retry on validation failure

Each section MUST be retried at most once when its draft fails for any reason: a validation failure (strict-format, `ast.parse`, or `nbformat.validate` gate) or a `ProviderError` raised by the provider. A `ProviderError` therefore counts as a validation failure for the retry-once rule. A section that fails twice for any reason MUST be recorded as a draft error and MUST NOT block the remaining sections.

#### Scenario: One retry per section

- GIVEN a section whose first draft fails validation
- WHEN the pipeline retries it once
- THEN the retry's output is validated
- AND if the retry passes, the section is accepted

#### Scenario: ProviderError retried once

- GIVEN a section whose first draft raises `ProviderError`
- WHEN the pipeline applies the retry-once rule
- THEN the section is retried once
- AND if the retry succeeds, the section is accepted

### Requirement: External provider disclosure

Before the first draft request to an external provider (OpenAI, Anthropic, or Ollama — any provider other than `local`), the UI MUST show a disclosure stating that the source document content will be transmitted to that provider's service, and MUST obtain explicit user confirmation before proceeding. The default `llmProvider` MUST be `local`, so no disclosure is required until the user explicitly opts into an external provider.

#### Scenario: Disclosure before external draft

- GIVEN `llmProvider=openai|anthropic|ollama` and a source document loaded
- WHEN the user starts drafting
- THEN the UI shows a disclosure that source content will be transmitted to the external service
- AND drafting starts only after the user confirms explicitly

#### Scenario: No disclosure for local

- GIVEN `llmProvider=local` (the default)
- WHEN the user starts drafting
- THEN no external disclosure is shown
- AND drafting proceeds against the in-process local server

### Requirement: Post-validation gates

The pipeline MUST validate drafted output before acceptance: the assembled notebook MUST pass `nbformat.validate`, and every code cell MUST pass `ast.parse`.

#### Scenario: Notebook and cells validated

- GIVEN a fully drafted notebook
- WHEN the pipeline runs the validation gates
- THEN `nbformat.validate` passes on the notebook
- AND every code cell parses via `ast.parse`

#### Scenario: Invalid code cell rejected

- GIVEN a draft containing syntactically invalid code
- WHEN `ast.parse` runs on that cell
- THEN the cell fails parsing and the section is flagged for retry

### Requirement: Key handling

API keys MUST be stored in the gitignored user config JSON (`~/.test-prompts/config.json`, new keys `openaiApiKey`, `anthropicApiKey`, `ollamaModel`), MUST be masked in the UI, and MUST NOT be logged or embedded in prompts sent to providers. Keychain storage is deferred to a future change.

#### Scenario: Keys masked and never logged

- GIVEN configured API keys
- WHEN the UI renders the settings
- THEN keys appear masked (e.g., `****`-suffixed)
- AND no log output contains the full key value

#### Scenario: Local provider works without keys

- GIVEN no API keys configured
- WHEN `llmProvider=local`
- THEN drafting works offline without key configuration
