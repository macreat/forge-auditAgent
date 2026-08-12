"""Runtime ML QA orchestration over the executed kernel namespace.

:class:`RuntimeQA` bridges the executor and the runtime ML QA checks: it takes a
parsed :class:`~nb_audit.ir.NotebookModel` plus the :class:`ExecutionResult`
returned by :class:`~nb_audit.execute.NotebookExecutor` and runs the
:mod:`nb_audit.mlqa` registry's checks against the executed namespace.

The ``require_clean_execution`` gate (config ``qa.require_clean_execution``) is
the pass/fail boundary: if execution did **not** succeed, runtime QA must NOT
report PASS — it reports ``FAILED`` and surfaces the severity-10 ``execution``
finding produced by the executor. This is the only case where QA short-circuits;
the runtime checks themselves are otherwise purely additive (they emit findings
that the iteration controller folds into its ``unresolved > 8`` set).

Note on status semantics: ``QA == PASS`` means "runtime QA ran against a clean
execution" — it does **not** mean "zero findings". A leaky split still yields a
severity-9 finding on a PASS-QA run; the four-gate PASS predicate rejects it via
the independent ``unresolved > 8 == 0`` clause.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nb_audit.config import AuditConfig
from nb_audit.execute import ExecutionResult
from nb_audit.ir import NotebookModel
from nb_audit.mlqa import default_registry
from nb_audit.mlqa.check_registry import RuntimeCheckRegistry
from nb_audit.models import Finding

PASS = "PASS"
FAILED = "FAILED"


@dataclass
class QAResult:
    """Outcome of one runtime QA pass."""

    status: str
    findings: list[Finding] = field(default_factory=list)
    exec_result: ExecutionResult | None = None

    @property
    def passed(self) -> bool:
        return self.status == PASS


class RuntimeQA:
    """Orchestrates the mlqa runtime checks over an executed namespace."""

    def __init__(
        self,
        config: AuditConfig | None = None,
        registry: RuntimeCheckRegistry | None = None,
    ) -> None:
        self.config = config or AuditConfig()
        self.registry = registry or default_registry()

    def run(self, model: NotebookModel, exec_result: ExecutionResult) -> QAResult:
        """Run runtime QA for one executed notebook.

        - ``require_clean_execution`` and a failed execution → ``FAILED`` with
          the executor's severity-10 finding surfaced (no runtime checks run).
        - Otherwise → run every registered check against ``exec_result.namespace``
          and return their findings with status ``PASS``.
        """
        if self.config.qa.require_clean_execution and not exec_result.ok:
            findings = [exec_result.finding] if exec_result.finding is not None else []
            return QAResult(status=FAILED, findings=findings, exec_result=exec_result)

        findings = self.registry.run_all(model, exec_result.namespace)
        return QAResult(status=PASS, findings=findings, exec_result=exec_result)
