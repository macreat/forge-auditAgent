# test-prompts-app — Notebook Audit & Cross-LLM Comparison

Cross-platform desktop app for hardware detection, GGUF model download, and
local LLM inference — extended here with a **notebook-auditing use case**:
running the same audit prompt against several LLMs (API-based and local) and
comparing their outputs side by side to see where models agree and where
they diverge.

---

## 1. What the app already does

Built with Python 3.14, Flet, `llama-cpp-python`, and HuggingFace Hub, the
app has four tabs:

| Tab | Purpose |
|---|---|
| **Hardware** | OS, RAM, GPU info, model-size recommendation |
| **Models** | Browse HuggingFace for compatible GGUF models, pick a quantization, download |
| **Server** | Pick a downloaded model, configure host/port/GPU layers/context, start/stop a local OpenAI-compatible inference server |
| **Settings** | Change models directory, save config |

`tools/hello_llm.py` sends a quick chat-completion request to
`http://localhost:8000/v1/chat/completions` to smoke-test a running server.

This gives the app everything it needs to talk to **local** models. Talking
to **API** models (GPT-4, Claude, etc.) uses the same request/response shape
via `app/api/utils.py` (currently a placeholder for provider abstraction).

---

## 2. The new use case: auditing a notebook with multiple LLMs

The idea is to treat each LLM — local or remote — as an interchangeable
**"sensor"**: it receives the same audit prompt plus the same notebook, and
must return strictly structured JSON with no scoring, no severity labels,
and no prose. Because the prompt is fixed and the output schema is fixed,
outputs from different models become directly comparable.

```
                ┌─────────────────────┐
                │  Sensor Prompt       │  (fixed instructions,
                │  + Notebook content  │   forbids scores/severity)
                └──────────┬───────────┘
                           │  same input, sent to every model
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   ┌─────────┐        ┌─────────┐        ┌─────────┐
   │ gpt-4   │        │ ollama  │        │ claude  │   ...any model in
   │ (API)   │        │ (Local) │        │ (API)   │   input-experiment.json
   └────┬────┘        └────┬────┘        └────┬────┘
        │                  │                  │
        ▼                  ▼                  ▼
   SensorOutput       SensorOutput       SensorOutput
   JSON (model A)     JSON (model B)     JSON (model C)
        └──────────────────┼──────────────────┘
                           ▼
              Cross-LLM Comparison / Variability view
```

### 2.1 The sensor prompt contract

The prompt used for this experiment (see example in the project) instructs
the model to act as a **factual evidence-extraction sensor**: it must
extract atomic, verifiable observations from notebook code without scoring,
without severity labels, and without aggregating multiple issues into one
observation. It must return only JSON matching a `SensorOutput` schema, and
must refuse to do a monolithic audit (returning a `chunking-required` flag
instead) if the notebook is too large.

It scans two fixed criteria groups:

- **Criterion 1 — Organized & Clear Structure**: workflow order (1.1),
  top-to-bottom execution order (1.2), code readability (1.3), documentation
  (1.4).
- **Criterion 2 — Reproducibility & Environment Management**: env variables
  (2.1), reliable data handling (2.2), atomic/reusable cells (2.3),
  reproducibility controls / seeds (2.4), caching/fast reruns (2.5).

For every relevant cell and criterion it must emit exactly one
`AtomicObservation`, plus `ComplexFunction` pseudocode entries for
non-trivial functions, plus `CrossReferenceDiscrepancy` entries where the
summary in Steps 1–2 doesn't match what the code actually does.

### 2.2 `SensorOutput` JSON schema

This is the shape every model's response must conform to (derived from the
worked example):

| Key | Type | Description |
|---|---|---|
| `overall_purpose` | string | 2–3 sentence summary of the notebook's goal |
| `pipeline_summary` | string | 3–5 sentence summary of block dependencies |
| `observations` | array | One entry per (criterion, cell) pair |
| `observations[].criterion_id` | string | e.g. `"1.4"`, `"2.1"` |
| `observations[].cell_id` | string | Stable cell id (native or `C000`, `C001`, ...) |
| `observations[].applicability` | string | `IN_SCOPE` or `NOT-APPLICABLE` |
| `observations[].observation` | string | Factual statement, no judgement words |
| `observations[].code_snippet` | string | Exact snippet supporting the claim |
| `observations[].line_range` | string | e.g. `"C005:10-15"` |
| `complex_functions` | array | Non-trivial functions translated to pseudocode |
| `complex_functions[].cell_id` | string | Cell containing the function |
| `complex_functions[].function_name` | string | Fully qualified function/method name |
| `complex_functions[].pseudocode` | string | Plain-English description of the logic |
| `cross_reference_discrepancies` | array | Mismatches between Steps 1–2 and the code |

Because every model returns this same shape, an audit run against N models
produces N structurally identical JSON files that can be diffed
field-by-field.

---

## 3. Extending `input-experiment.json` / `output-experiment.json`

The existing templates already describe *what to run* and *what came back*
per model. For the notebook-audit use case they're extended slightly:

**`input-experiment.json`** — `prompt` becomes the full sensor prompt above,
and a `notebookPath` (or inline `notebookCells`) field is added alongside
`models`:

```json
{
  "timestamp": "2026-07-10T20:00:00Z",
  "prompt": "You are a factual evidence-extraction sensor for a Jupyter Notebook audit. ...",
  "notebookPath": "notebooks/multi_scale_lstm.ipynb",
  "models": [
    { "name": "gpt-4", "type": "API" },
    { "name": "claude-sonnet-5", "type": "API" },
    { "name": "ollama-llama3", "quantization": "q4_0", "type": "Local" }
  ]
}
```

**`output-experiment.json`** — each entry's `response` is now expected to be
a parsed `SensorOutput` object instead of free text, and (per the docs
table) `delayResponse` records when that response arrived so latency can be
computed against `timestamp`:

```json
{
  "timestamp": "2026-07-10T20:00:00Z",
  "outputs": [
    {
      "model": "gpt-4",
      "type": "API",
      "response": { "overall_purpose": "...", "observations": ["..."] },
      "delayResponse": "2026-07-10T20:00:04Z"
    },
    {
      "model": "ollama-llama3",
      "type": "Local",
      "response": { "overall_purpose": "...", "observations": ["..."] },
      "delayResponse": "2026-07-10T20:00:11Z"
    }
  ]
}
```

---

## 4. New feature: Cross-LLM Comparison view

This is the piece that turns N separate JSON files into an actual audit
tool: a **Compare** tab (or a view within Server/Models) that pivots the
`observations` arrays from every model into one table, keyed by
`criterion_id` + `cell_id`, with **one column per LLM**.

### 4.1 Comparison table shape

| criterion_id | cell_id | gpt-4 | claude-sonnet-5 | ollama-llama3 | variability |
|---|---|---|---|---|---|
| 2.4 | C008 | "seeds set for random, numpy, torch before split/init" | "seeds set for random, numpy, torch before split/init" | *(absent — not reported)* | **partial** (2/3 models reported it) |
| 2.1 | C005 | "DATA_URL and RNG_SEED hardcoded" | "RNG_SEED hardcoded; DATA_URL not flagged" | "config values hardcoded" | **divergent** (differing scope) |
| 1.1 | — | applicability: NOT-APPLICABLE | applicability: IN_SCOPE | applicability: IN_SCOPE | **disagreement on applicability** |

A blank cell means that model didn't emit an observation for that
`criterion_id` × `cell_id` pair at all — itself a meaningful signal, since
the prompt requires exactly one observation per relevant cell per
criterion.

### 4.2 Proposed `comparison-experiment.json` output

To make this table reproducible and storable (not just a UI computation),
a new artifact sits alongside the existing input/output JSON files:

```json
{
  "timestamp": "2026-07-10T20:05:00Z",
  "notebookPath": "notebooks/multi_scale_lstm.ipynb",
  "models": ["gpt-4", "claude-sonnet-5", "ollama-llama3"],
  "comparisonRows": [
    {
      "criterion_id": "2.4",
      "cell_id": "C008",
      "byModel": {
        "gpt-4": { "applicability": "IN_SCOPE", "observation": "..." },
        "claude-sonnet-5": { "applicability": "IN_SCOPE", "observation": "..." },
        "ollama-llama3": null
      },
      "variabilityScore": 0.33,
      "variabilityType": "partial-coverage"
    },
    {
      "criterion_id": "1.1",
      "cell_id": null,
      "byModel": {
        "gpt-4": { "applicability": "NOT-APPLICABLE", "observation": null },
        "claude-sonnet-5": { "applicability": "IN_SCOPE", "observation": "..." },
        "ollama-llama3": { "applicability": "IN_SCOPE", "observation": "..." }
      },
      "variabilityScore": 0.67,
      "variabilityType": "applicability-disagreement"
    }
  ],
  "crossReferenceDiscrepancyDiff": {
    "onlyIn": {
      "gpt-4": [],
      "claude-sonnet-5": ["pipeline_summary claims caching is present; C024 shows none"],
      "ollama-llama3": []
    }
  }
}
```

`variabilityScore` is a simple stand-in metric — e.g. the fraction of models
that *disagree* with the majority (on coverage, on `applicability`, or on
observation text similarity below a threshold). `variabilityType` labels
*why* the row is flagged:

- **`missing-in-one`** — one or more models skipped a cell/criterion the
  others covered.
- **`applicability-disagreement`** — models disagree on `IN_SCOPE` vs
  `NOT-APPLICABLE`.
- **`text-divergence`** — all models reported something, but the factual
  content differs materially (e.g. different snippet, different scope of
  what's flagged).
- **`consistent`** — all models agree, both in coverage and content.

### 4.3 How this shows up in the app

- **Server tab** already lets you pick a model and run it; this would be
  extended so a single "Run Audit" action fires the same prompt+notebook at
  every model listed in `input-experiment.json` (sequentially for local
  models sharing one server slot, in parallel for API models).
- A new **Compare** tab renders `comparisonRows` as the table in §4.1, with
  rows sortable/filterable by `variabilityType`, and disagreement rows
  highlighted so a reviewer can jump straight to the places where models
  don't agree — which is usually where a closer manual look is most
  valuable.
- `variabilityScore` aggregated across all rows gives a single "how much do
  these models agree overall" number per notebook, useful for deciding
  whether one model's audit alone is trustworthy enough to skip
  cross-checking.

---

## 5. Updated project structure (relevant additions only)

```
test/prompts/
├── app/
│   ├── api/
│   │   ├── local.py         # existing: hardware, HF browser, GGUF download, AsyncLlamaServer
│   │   ├── utils.py         # provider abstraction — now used to dispatch the
│   │   │                    #   same sensor prompt to both API and Local models
│   │   └── compare.py       # NEW — builds comparisonRows / variability metrics
│   │                        #   from a set of SensorOutput JSON files
│   └── UI/
│       └── app.py           # Hardware / Models / Server / Settings / Compare tabs
├── templates/
│   ├── input-experiment.json    # extended with notebookPath + full sensor prompt
│   ├── output-experiment.json   # response is now a parsed SensorOutput object
│   └── comparison-experiment.json  # NEW — per-criterion/cell diff across models
```

---

## 6. Summary

- The app's existing hardware-detection + local-server + HF-download
  pipeline stays the same.
- The notebook-audit use case adds a fixed, judgement-free "sensor prompt"
  that any model — local or API — answers in a common `SensorOutput` JSON
  shape.
- `input-experiment.json` / `output-experiment.json` gain a notebook
  reference and a structured (not free-text) response.
- A new `comparison-experiment.json` + **Compare** tab pivot per-model
  outputs into one table, one column per LLM, so it's immediately visible
  where models agree, where one model missed something, and where models
  actively disagree on the facts.