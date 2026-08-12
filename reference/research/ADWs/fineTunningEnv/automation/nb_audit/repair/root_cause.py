"""Root-cause analysis for severity > 8 findings (spec §15).

Every finding with ``severity > 8`` must undergo root-cause analysis before
patching. The analysis is captured in a :class:`RootCause` dataclass with exactly
eight fields::

    issue, location, severity, classification, root_cause, impact, correction,
    downstream

``RootCause.from_finding(finding)`` builds a fully-populated RCA for any
severity>8 finding and raises :class:`RootCauseNotRequired` otherwise. The
``downstream`` field is derived from the finding's ``category`` using the
ordered IR chain defined here (data → train → val → test → metrics → plots →
artifacts → conclusions → qa), which is also the single source of truth for
protocol propagation (§17, see :mod:`nb_audit.repair.propagation`).

Severity is never auto-lowered here; the RCA simply copies the finding's
severity (already clamped to [1, 10] by :class:`~nb_audit.models.Finding`).
"""

from __future__ import annotations

from dataclasses import dataclass

from nb_audit.models import Classification, Finding, Location

# --------------------------------------------------------------------------- #
# The ordered IR chain (spec §17) — shared with propagation.py
# --------------------------------------------------------------------------- #
IR_CHAIN: tuple[str, ...] = (
    "data",
    "train",
    "val",
    "test",
    "metrics",
    "plots",
    "artifacts",
    "conclusions",
    "qa",
)

# Maps a finding ``category`` to the IR-chain section it belongs to. Categories
# not listed fall back to "data" (most conservative: everything downstream must
# be re-inspected).
CATEGORY_SECTION: dict[str, str] = {
    "data": "data",
    "splits": "data",
    "leakage": "data",
    "reproducibility": "data",
    "execution_order": "data",
    "undefined_name": "data",
    "syntax": "data",
    "ast_analysis": "data",
    "api_misuse": "data",
    "train": "train",
    "tensors": "train",
    "val": "val",
    "validation": "val",
    "test": "test",
    "metrics": "metrics",
    "plots": "plots",
    "artifacts": "artifacts",
    "checkpoints": "artifacts",
    "conclusions": "conclusions",
    "qa": "qa",
    "experimental_validity": "metrics",
}


class RootCauseNotRequired(ValueError):
    """Raised when an RCA is requested for a finding that does not need one."""

    def __init__(self, finding_id: str, severity: int) -> None:
        super().__init__(
            f"root-cause analysis is only required for severity > 8 "
            f"(finding {finding_id!r} has severity {severity})"
        )
        self.finding_id = finding_id
        self.severity = severity


def section_for(category: str) -> str:
    """Return the IR-chain section a finding ``category`` belongs to."""
    if category in CATEGORY_SECTION:
        return CATEGORY_SECTION[category]
    if category in IR_CHAIN:
        return category
    return "data"


def downstream_sections(category: str) -> tuple[str, ...]:
    """Return every IR-chain section downstream of ``category`` (exclusive)."""
    section = section_for(category)
    try:
        index = IR_CHAIN.index(section)
    except ValueError:  # pragma: no cover - section_for always returns a chain member
        index = 0
    return IR_CHAIN[index + 1:]


@dataclass(frozen=True)
class RootCause:
    """Eight-field root-cause analysis for a single severity>8 finding."""

    issue: str
    location: Location
    severity: int
    classification: Classification
    root_cause: str
    impact: str
    correction: str
    downstream: tuple[str, ...]

    @classmethod
    def from_finding(cls, finding: Finding) -> "RootCause":
        """Build a full RCA from a severity>8 finding.

        Raises :class:`RootCauseNotRequired` when ``finding.severity <= 8``.
        """
        if finding.severity <= 8:
            raise RootCauseNotRequired(finding.id, finding.severity)
        return cls(
            issue=finding.issue,
            location=finding.location,
            severity=finding.severity,
            classification=finding.classification,
            root_cause=finding.root_cause,
            impact=finding.impact,
            correction=finding.correction,
            downstream=downstream_sections(finding.category),
        )
