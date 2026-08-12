"""Static check registry: the :class:`StaticCheck` ABC and :class:`CheckRegistry`.

Static checks are deterministic and LLM-free. Each check is a class that
declares a stable ``name``, ``category``, and a default ``severity``, and
implements ``check(model) -> list[Finding]``. The registry dispatches checks by
name and runs them over a :class:`~nb_audit.ir.NotebookModel`, returning findings
sorted deterministically (stable across repeated runs of the same notebook).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Iterable

from nb_audit.ir import NotebookModel
from nb_audit.models import Classification, Finding, Location


class StaticCheck(ABC):
    """Base class for a deterministic, LLM-free static audit check."""

    name: ClassVar[str] = ""
    category: ClassVar[str] = "static"
    severity: ClassVar[int] = 5

    @abstractmethod
    def check(self, model: NotebookModel) -> list[Finding]:
        """Run this check over the notebook IR and return its findings."""

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


class CheckRegistry:
    """Collects and dispatches static checks; runs them deterministically."""

    def __init__(self) -> None:
        self._checks: dict[str, type[StaticCheck]] = {}
        self._order: list[str] = []

    # -- registration ------------------------------------------------------ #
    def register(self, check_cls: type[StaticCheck]) -> type[StaticCheck]:
        """Register a check class. Returns the class for decorator-style use."""
        name = check_cls.name
        if not name:
            raise ValueError("StaticCheck subclasses must define a non-empty 'name'")
        self._checks[name] = check_cls
        if name not in self._order:
            self._order.append(name)
        return check_cls

    def get(self, name: str) -> type[StaticCheck] | None:
        """Return the registered check class for ``name``, or ``None``."""
        return self._checks.get(name)

    def names(self) -> tuple[str, ...]:
        """Registered check names, in registration order."""
        return tuple(self._order)

    # -- dispatch ---------------------------------------------------------- #
    def dispatch(self, name: str, model: NotebookModel) -> list[Finding]:
        """Instantiate and run the named check over ``model``."""
        check_cls = self._checks.get(name)
        if check_cls is None:
            raise KeyError(f"unknown static check: {name!r}")
        return check_cls().check(model)

    def run(
        self,
        model: NotebookModel,
        names: Iterable[str] | None = None,
    ) -> list[Finding]:
        """Run all (or the requested) checks and return sorted, identified findings.

        Findings are sorted by (cell, line, category, issue) and assigned stable
        ids ``{category}-NN`` so that two runs over the same notebook produce
        byte-identical finding lists (REQ-003 determinism).
        """
        selected = list(names) if names is not None else list(self._order)
        findings: list[Finding] = []
        for name in selected:
            findings.extend(self.dispatch(name, model))
        findings.sort(key=_sort_key)
        for index, finding in enumerate(findings, 1):
            if not finding.id:
                finding.id = f"{finding.category or 'static'}-{index:02d}"
        return findings

    # ``run_all`` is the historical alias used across the pipeline.
    run_all = run
