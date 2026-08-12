"""Core data model: Finding, enums, signatures, history, and the finding manager.

Severity is clamped to [1, 10] and is NEVER auto-lowered. Classification
(NEW vs RELATED_TO_OLD_ISSUE) is decided by signature — the hash of
``root_cause || category || location`` — never by wording.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Classification(str, Enum):
    NEW = "NEW"
    RELATED_TO_OLD_ISSUE = "RELATED_TO_OLD_ISSUE"


class Status(str, Enum):
    UNRESOLVED = "unresolved"
    PATCHED = "patched"
    RESOLVED = "resolved"
    RECURRING = "recurring"
    WONT_FIX = "wont_fix"


# --------------------------------------------------------------------------- #
# Severity
# --------------------------------------------------------------------------- #
MIN_SEVERITY = 1
MAX_SEVERITY = 10


def clamp_severity(value: int) -> int:
    """Clamp ``value`` into [1, 10]. Never lowers a real severity to force PASS."""
    return max(MIN_SEVERITY, min(MAX_SEVERITY, int(value)))


# --------------------------------------------------------------------------- #
# Location
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Location:
    cell: str = ""
    line: int | None = None

    def key(self) -> str:
        """Coarse location key used in signatures (cell, optionally cell:line)."""
        if self.line is not None:
            return f"{self.cell}:{self.line}"
        return self.cell


# --------------------------------------------------------------------------- #
# Signature
# --------------------------------------------------------------------------- #
def _location_key(location: Any) -> str:
    if isinstance(location, Location):
        return location.key()
    return str(location)


def compute_signature(root_cause: str, category: str, location: Any) -> str:
    """Deterministic signature: sha256 of ``root_cause || category || location``."""
    raw = f"{root_cause}||{category}||{_location_key(location)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SignatureStore:
    """Remembers signatures seen so far and maps them to finding ids."""

    def __init__(self) -> None:
        self._known: dict[str, str] = {}

    def compute(self, root_cause: str, category: str, location: Any) -> str:
        return compute_signature(root_cause, category, location)

    def remember(self, signature: str, finding_id: str) -> None:
        self._known[signature] = finding_id

    def lookup(self, signature: str) -> str | None:
        return self._known.get(signature)

    def __contains__(self, signature: str) -> bool:
        return signature in self._known

    def __len__(self) -> int:
        return len(self._known)


# --------------------------------------------------------------------------- #
# Finding
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    id: str
    severity: int
    classification: Classification
    category: str
    location: Location
    issue: str
    root_cause: str = ""
    impact: str = ""
    correction: str = ""
    status: Status = Status.UNRESOLVED
    signature: str = ""
    patch_ids: list[str] = field(default_factory=list)
    regression: bool = False

    def __post_init__(self) -> None:
        self.severity = clamp_severity(self.severity)
        if isinstance(self.classification, str):
            self.classification = Classification(self.classification)
        if isinstance(self.status, str):
            self.status = Status(self.status)
        if isinstance(self.location, dict):
            self.location = Location(
                cell=self.location.get("cell", ""),
                line=self.location.get("line"),
            )
        if not self.signature:
            self.signature = compute_signature(
                self.root_cause, self.category, self.location
            )

    def to_raw(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "classification": self.classification.value,
            "category": self.category,
            "location": {"cell": self.location.cell, "line": self.location.line},
            "issue": self.issue,
            "root_cause": self.root_cause,
            "impact": self.impact,
            "correction": self.correction,
            "status": self.status.value,
            "signature": self.signature,
            "patch_ids": list(self.patch_ids),
            "regression": self.regression,
        }

    @classmethod
    def from_raw(cls, raw: dict) -> "Finding":
        return cls(
            id=raw["id"],
            severity=raw["severity"],
            classification=raw.get("classification", Classification.NEW),
            category=raw.get("category", ""),
            location=raw.get("location", {}),
            issue=raw.get("issue", ""),
            root_cause=raw.get("root_cause", ""),
            impact=raw.get("impact", ""),
            correction=raw.get("correction", ""),
            status=raw.get("status", Status.UNRESOLVED),
            signature=raw.get("signature", ""),
            patch_ids=list(raw.get("patch_ids", [])),
            regression=bool(raw.get("regression", False)),
        )


# --------------------------------------------------------------------------- #
# IssueHistory
# --------------------------------------------------------------------------- #
class IssueHistory:
    """Insertion-ordered registry of findings that survives serialization."""

    def __init__(self) -> None:
        self._findings: dict[str, Finding] = {}
        self._order: list[str] = []

    def add(self, finding: Finding) -> None:
        if finding.id not in self._findings:
            self._order.append(finding.id)
        self._findings[finding.id] = finding

    def get(self, finding_id: str) -> Finding | None:
        return self._findings.get(finding_id)

    def all(self) -> list[Finding]:
        return [self._findings[fid] for fid in self._order]

    def by_signature(self, signature: str) -> list[Finding]:
        return [f for f in self.all() if f.signature == signature]

    def __iter__(self) -> Iterator[Finding]:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self._findings)

    def to_raw(self) -> list[dict]:
        return [f.to_raw() for f in self.all()]

    @classmethod
    def from_raw(cls, raw: Iterable[dict]) -> "IssueHistory":
        history = cls()
        for item in raw:
            history.add(Finding.from_raw(item))
        return history


# --------------------------------------------------------------------------- #
# FindingManager
# --------------------------------------------------------------------------- #
class FindingManager:
    """Adds findings, assigns signatures/classification, and upgrades status."""

    def __init__(
        self,
        signature_store: SignatureStore | None = None,
        history: IssueHistory | None = None,
    ) -> None:
        self.signature_store = signature_store or SignatureStore()
        self.history = history or IssueHistory()
        self._counter = 0

    # -- write path -------------------------------------------------------- #
    def add(self, finding: Finding) -> Finding:
        if not finding.signature:
            finding.signature = self.signature_store.compute(
                finding.root_cause, finding.category, finding.location
            )
        finding.classification = self.classify_new_vs_related(finding)
        if not finding.id:
            finding.id = self._next_id()
        self.signature_store.remember(finding.signature, finding.id)
        self.history.add(finding)
        return finding

    def _next_id(self) -> str:
        self._counter += 1
        return f"F{self._counter:04d}"

    # -- read path --------------------------------------------------------- #
    def find(
        self,
        finding_id: str | None = None,
        category: str | None = None,
        severity_gt: int | None = None,
        status: Status | str | None = None,
        classification: Classification | str | None = None,
    ) -> list[Finding]:
        results = self.history.all()
        if finding_id is not None:
            results = [f for f in results if f.id == finding_id]
        if category is not None:
            results = [f for f in results if f.category == category]
        if severity_gt is not None:
            results = [f for f in results if f.severity > severity_gt]
        if status is not None:
            status = Status(status) if isinstance(status, str) else status
            results = [f for f in results if f.status is status]
        if classification is not None:
            classification = (
                Classification(classification)
                if isinstance(classification, str)
                else classification
            )
            results = [f for f in results if f.classification is classification]
        return results

    def upgrade_status(self, finding_id: str, new_status: Status | str) -> Finding | None:
        finding = self.history.get(finding_id)
        if finding is None:
            return None
        finding.status = Status(new_status) if isinstance(new_status, str) else new_status
        return finding

    def classify_new_vs_related(self, finding: Finding) -> Classification:
        """NEW if the signature is unseen, otherwise RELATED_TO_OLD_ISSUE."""
        signature = finding.signature or self.signature_store.compute(
            finding.root_cause, finding.category, finding.location
        )
        if signature in self.signature_store:
            return Classification.RELATED_TO_OLD_ISSUE
        return Classification.NEW
