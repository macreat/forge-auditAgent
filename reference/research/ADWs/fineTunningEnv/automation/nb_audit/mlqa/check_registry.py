"""Runtime ML QA check registry.

Unlike static checks, runtime checks run *after* notebook execution. They take the
notebook IR (:class:`~nb_audit.ir.NotebookModel`) plus the executed kernel
namespace (``ctx``, a dict-like :class:`~typing.Mapping` of variable name →
value) and assert runtime invariants that static analysis cannot see: split
disjointness, tensor shape/dtype/device invariants, metric ranges, checkpoint
existence, and artifact provenance.

Each check is a class declaring a stable ``name``, ``category`` and a default
``severity``, and implementing ``check(model, ctx) -> list[Finding]``. The
registry dispatches by name and runs all checks, returning findings sorted
deterministically so repeated runs over the same namespace are byte-identical.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Iterable, Mapping

from nb_audit.ir import NotebookModel
from nb_audit.models import Classification, Finding, Location


class RuntimeCheck(ABC):
    """Base class for a deterministic, LLM-free runtime ML QA check."""

    name: ClassVar[str] = ""
    category: ClassVar[str] = "mlqa"
    severity: ClassVar[int] = 5

    @abstractmethod
    def check(self, model: NotebookModel, ctx: Mapping) -> list[Finding]:
        """Run this check over the notebook IR and executed namespace."""

    def finding(
        self,
        *,
        location: Location,
        issue: str,
        severity: int | None = None,
        category: str | None = None,
        root_cause: str = "",
        impact: str = "",
        correction: str = "",
    ) -> Finding:
        """Build a :class:`Finding` with this check's default severity/category.

        The returned finding has an empty ``id``; the registry assigns stable
        deterministic ids after sorting. The signature is computed lazily from
        ``root_cause || category || location`` by :class:`Finding`.
        """
        return Finding(
            id="",
            severity=self.severity if severity is None else severity,
            classification=Classification.NEW,
            category=category if category is not None else self.category,
            location=location,
            issue=issue,
            root_cause=root_cause,
            impact=impact,
            correction=correction,
        )


def _sort_key(finding: Finding) -> tuple:
    """Deterministic ordering: cell, line, category, issue."""
    location = finding.location
    return (
        location.cell,
        location.line if location.line is not None else 0,
        finding.category,
        finding.issue,
    )


class RuntimeCheckRegistry:
    """Collects and dispatches runtime checks; runs them deterministically."""

    def __init__(self) -> None:
        self._checks: dict[str, type[RuntimeCheck]] = {}
        self._order: list[str] = []

    # -- registration ------------------------------------------------------ #
    def register(self, check_cls: type[RuntimeCheck]) -> type[RuntimeCheck]:
        """Register a check class. Returns the class for decorator-style use."""
        name = check_cls.name
        if not name:
            raise ValueError("RuntimeCheck subclasses must define a non-empty 'name'")
        self._checks[name] = check_cls
        if name not in self._order:
            self._order.append(name)
        return check_cls

    def get(self, name: str) -> type[RuntimeCheck] | None:
        """Return the registered check class for ``name``, or ``None``."""
        return self._checks.get(name)

    def names(self) -> tuple[str, ...]:
        """Registered check names, in registration order."""
        return tuple(self._order)

    # -- dispatch ---------------------------------------------------------- #
    def dispatch(self, name: str, model: NotebookModel, ctx: Mapping) -> list[Finding]:
        """Instantiate and run the named check over ``model`` and ``ctx``."""
        check_cls = self._checks.get(name)
        if check_cls is None:
            raise KeyError(f"unknown runtime check: {name!r}")
        return check_cls().check(model, ctx)

    def run_all(
        self,
        model: NotebookModel,
        ctx: Mapping,
        names: Iterable[str] | None = None,
    ) -> list[Finding]:
        """Run all (or the requested) checks and return sorted, identified findings.

        Findings are sorted by (cell, line, category, issue) and assigned stable
        ids ``{category}-NN`` so repeated runs are deterministic (REQ-004).
        """
        selected = list(names) if names is not None else list(self._order)
        findings: list[Finding] = []
        for name in selected:
            findings.extend(self.dispatch(name, model, ctx))
        findings.sort(key=_sort_key)
        for index, finding in enumerate(findings, 1):
            if not finding.id:
                finding.id = f"{finding.category or 'mlqa'}-{index:02d}"
        return findings

    # ``run`` is the historical alias used across the pipeline.
    run = run_all
