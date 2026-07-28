## LLM-as-a-Judge as the Evaluation Paradigm

The proposed notebook auditing framework follows the emerging **LLM-as-a-Judge (LAJ)** paradigm, in which a powerful language model evaluates the outputs of another model (or of itself under controlled prompting) instead of relying solely on human reviewers. This approach is particularly suitable for notebook audits because many evaluation criteria—such as code clarity, logical coherence, documentation quality, or methodological soundness—cannot be measured using deterministic metrics alone.

Unlike traditional automatic evaluation metrics (e.g., BLEU or ROUGE), which require reference outputs and perform poorly on open-ended reasoning tasks, an LLM judge can evaluate responses using qualitative criteria similar to those employed by expert reviewers. Recent work has shown that sufficiently capable language models achieve agreement with human evaluators comparable to inter-human agreement when judging open-ended responses.

### Motivation

Notebook auditing combines objective and subjective evaluation tasks.

**Objective tasks** include:

- dependency validation,
- execution reproducibility,
- train/test split verification,
- artifact existence,
- environment completeness.

These can often be evaluated deterministically through programmatic checks.

Conversely, **subjective tasks** include:

- quality of documentation,
- conceptual coherence,
- methodological soundness,
- explanation quality,
- maintainability,
- deployment readiness.

These require semantic reasoning and therefore benefit from an LLM acting as an evaluator.

The proposed framework intentionally separates these two categories rather than attempting to solve both with a single mechanism.

---

## Deterministic Evaluation vs. LLM Judging

The audit framework adopts a layered evaluation strategy.

### Layer 1 — Deterministic Verification

Whenever correctness can be established objectively, deterministic evaluation is preferred.

Examples include:

- successful notebook execution,
- dependency resolution,
- version pinning,
- artifact generation,
- file existence,
- reproducibility checks.

These evaluations are binary and reproducible.

### Layer 2 — LLM-as-a-Judge

Only after deterministic checks have been completed does the framework invoke an LLM judge to assess properties requiring semantic interpretation.

Examples include:

- structural organization,
- readability,
- methodological consistency,
- code explanation quality,
- deployment recommendations.

This mirrors the evaluation philosophy adopted by recent agent benchmarks, where objective verification forms the first layer of validation while model-based evaluation is reserved for inherently subjective tasks.

---

## Prompt Engineering as Judge Design

An LLM judge is only as reliable as its evaluation protocol.

Following the G-Eval methodology, the prompts presented in this work do not ask the model to provide a single holistic score. Instead, each prompt decomposes notebook evaluation into explicit review criteria.

Rather than asking

> "Is this notebook good?"

the evaluator is instructed to inspect predefined dimensions such as:

- reproducibility,
- data integrity,
- methodological correctness,
- implementation quality,
- deployment readiness.

The resulting structured reports resemble formal peer-review checklists instead of free-form opinions, improving consistency across repeated evaluations.

This principle directly motivates the progressive prompt hierarchy introduced in Section **Prompt Crafting**, where increasingly constrained prompts guide the model from coarse inspection toward structured multi-pass auditing.

---

## Known Limitations

Although LLM judges exhibit strong agreement with human evaluators, they remain susceptible to systematic biases.

Commonly reported biases include:

- **Position bias** — preference for the first candidate presented.
- **Verbosity bias** — longer responses often receive higher scores despite similar quality.
- **Self-enhancement bias** — models tend to rate their own generations more favorably than those produced by competing models.
- **Reasoning limitations** — evaluation quality decreases when the judge must solve difficult mathematical or logical problems before assessing correctness.

These limitations motivate the design choices adopted throughout the audit framework:

- decomposition into multiple audit passes,
- explicit evaluation criteria,
- preference for deterministic verification whenever possible,
- avoidance of single holistic quality scores.

Rather than treating the LLM as an oracle, the framework views it as a structured reviewer operating within clearly defined evaluation boundaries.

---

## Position within This Work

The notebook auditing framework proposed in this document should therefore be interpreted as a specialized instance of the LLM-as-a-Judge paradigm.

Its primary contribution is not a new evaluation model, but a structured auditing protocol that combines:

1. deterministic verification wherever objective correctness exists;
2. prompt-engineered LLM judging for semantic evaluation;
3. incremental multi-pass analysis that progressively refines the assessment while reducing cognitive overload for both the evaluator and the reader.

This hybrid strategy combines the reproducibility of automated software testing with the flexibility of modern language-model evaluation, providing a practical methodology for AI-assisted review of computational notebooks.