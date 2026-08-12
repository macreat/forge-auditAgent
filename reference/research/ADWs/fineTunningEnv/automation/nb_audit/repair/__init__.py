"""Root-cause analysis, minimal attributed patches, and protocol propagation.

Exposes the three repair stages (spec §15–§17):

- :class:`RootCause` — eight-field root-cause analysis for severity>8 findings.
- :class:`PatchEngine` / :class:`Patch` / :class:`PatchLog` / :class:`PatchRefused` —
  minimal, attributed, diffable line-level patches with safety refusals.
- :class:`PropagationGraph` / :class:`PropagationResult` — downstream re-flagging
  over the IR chain.
"""

from __future__ import annotations

from nb_audit.repair.root_cause import (
    CATEGORY_SECTION,
    IR_CHAIN,
    RootCause,
    RootCauseNotRequired,
    downstream_sections,
    section_for,
)
from nb_audit.repair.patches import (
    Patch,
    PatchEngine,
    PatchLog,
    PatchRefused,
    extract_objective,
    patchable_candidates,
)
from nb_audit.repair.propagation import PropagationGraph, PropagationResult

__all__ = [
    "CATEGORY_SECTION",
    "IR_CHAIN",
    "RootCause",
    "RootCauseNotRequired",
    "downstream_sections",
    "section_for",
    "Patch",
    "PatchEngine",
    "PatchLog",
    "PatchRefused",
    "extract_objective",
    "patchable_candidates",
    "PropagationGraph",
    "PropagationResult",
]
