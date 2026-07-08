# Templates

## `input-experiment.json`

Structure for defining a prompt experiment to run against multiple models.

| Key | Type | Description |
|---|---|---|
| `timestamp` | string (ISO 8601) | When the experiment was created/initiated. |
| `prompt` | string | The system or user prompt text sent to each model. |
| `models` | array | List of target models to run the prompt against. |
| `models[].name` | string | Model identifier (e.g. `"gpt-4"`, `"ollama"`). |
| `models[].type` | string | Classification of the model: `"API"` for remote endpoints, `"Local"` for self-hosted. |

## `output-experiment.json`

Structure for capturing results after running an experiment.

| Key | Type | Description |
|---|---|---|
| `timestamp` | string (ISO 8601) | When the experiment was completed/recorded. |
| `outputs` | array | Per-model response entries. |
| `outputs[].model` | string | Model identifier matching the input model list. |
| `outputs[].type` | string | Classification: `"API"` or `"Local"`. |
| `outputs[].response` | string | The model's generated text response. |
| `outputs[].delayResponse` | string (ISO 8601) | Timestamp when the response was received (enables latency calculation). |
