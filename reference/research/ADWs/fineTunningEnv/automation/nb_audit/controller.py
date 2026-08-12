"""Iteration controller (spec §21) — the audit → patch → execute → QA → re-audit loop.

Implements the §21 loop with the four-gate PASS predicate (§22)::

    PASS = (no unresolved severity>8 findings)
           AND execution == SUCCESS
           AND QA == PASS
           AND no regressions

The whole loop body is injectable — auditor / executor / QA / patcher — so
tests drive iterations deterministically with fake components and NO live LLM.
The semantic LLM auditor is a strictly-degraded ADVISORY signal: it can only
ever ADD findings and returns an empty list on outage, so an LLM outage can
never flip PASS into FAIL.

Finding lifecycle (§8, §20)::

    unresolved → patched → resolved | recurring | wont_fix

- ``patched`` when a correction is applied to an unresolved finding;
- ``resolved`` when a patched signature disappears from the next full re-audit;
- ``recurring`` when a patched signature survives — the controller then REQUIRES
  a materially different correction (a correction string distinct from every
  prior attempt) and records the prior-failure reason, refusing to blindly
  repeat the same patch (§20);
- ``wont_fix`` is user-only: supplied signatures are honoured but never
  auto-assigned. It is a terminal, non-blocking state (the user accepted it).

``MAX_ITERATIONS`` defaults to 10 (config ``audit.max_iterations``) and is
overridable via the constructor, config, or the ``--max-iterations`` CLI flag
(wired in the CLI slice) → config ``audit.max_iterations``. If the loop exhausts
its iterations with unresolved severity>8 findings, the outcome is ``FAILED`` —
never PASS.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from nb_audit.config import AuditConfig
from nb_audit.execute import SUCCESS, ExecutionResult, NotebookExecutor
from nb_audit.ir import NotebookModel
from nb_audit.models import Classification, Finding, SignatureStore, Status
from nb_audit.qa import PASS as QA_PASS
from nb_audit.qa import QAResult, RuntimeQA
from nb_audit.regression import RegressionResult, detect_regressions, signature_set

# Outcome status values (spec §21/§22: "STATUS = FAILED" / "Status: PASS").
PASS = "PASS"
FAILED = "FAILED"

# A finding blocks PASS when its severity exceeds the threshold and its status
# is not terminal-non-blocking (resolved or user-accepted wont_fix) — mirroring
# the design predicate `status not in {resolved, wont_fix}`.
_NON_BLOCKING = (Status.RESOLVED, Status.WONT_FIX)

# Statuses whose signature may transition on the next re-audit.
_TRANSITIONABLE = (Status.PATCHED, Status.RECURRING)


# --------------------------------------------------------------------------- #
# Callable contracts (loop-body injection points)
# --------------------------------------------------------------------------- #
AuditorFn = Callable[[NotebookModel], list[Finding]]
ExecutorFn = Callable[[NotebookModel], ExecutionResult]
QAFn = Callable[[NotebookModel, ExecutionResult], QAResult]
PatcherFn = Callable[
    [list[Finding], NotebookModel, dict[str, list[str]]],
    "PatchOutcome",
]


@dataclass
class PatchOutcome:
    """Result of one patch attempt: a (possibly unchanged) model + corrections.

    ``corrections`` maps ``finding_id -> correction text`` for the findings the
    patcher actually fixed. A finding absent from this map means "no correction
    available" and keeps failing.
    """

    model: NotebookModel
    corrections: dict[str, str] = field(default_factory=dict)

    @property
    def applied_count(self) -> int:
        return len(self.corrections)


@dataclass
class IterationRecord:
    """One loop iteration's audit, execution, QA and patch results."""

    iteration: int
    findings: list[Finding] = field(default_factory=list)
    unresolved_gt8: list[Finding] = field(default_factory=list)
    exec_status: str = ""
    qa_status: str = ""
    regressions: list[Finding] = field(default_factory=list)
    recurring: list[Finding] = field(default_factory=list)
    corrections: dict[str, str] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "findings": [f.to_raw() for f in self.findings],
            "unresolved_gt8": [f.id for f in self.unresolved_gt8],
            "exec_status": self.exec_status,
            "qa_status": self.qa_status,
            "regressions": [f.id for f in self.regressions],
            "recurring": [f.id for f in self.recurring],
            "corrections": dict(self.corrections),
        }


@dataclass
class AuditOutcome:
    """Final result of the iteration loop."""

    status: str
    iterations: list[IterationRecord]
    final_findings: list[Finding]
    max_iterations: int
    reason: str

    @property
    def passed(self) -> bool:
        return self.status == PASS

    def to_raw(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "max_iterations": self.max_iterations,
            "reason": self.reason,
            "iterations": [it.to_raw() for it in self.iterations],
            "final_findings": [f.to_raw() for f in self.final_findings],
        }


def four_gate_pass(
    unresolved_gt8: Iterable[Finding],
    exec_status: str,
    qa_status: str,
    regressions: Iterable[Finding],
) -> bool:
    """The §22 four-gate PASS predicate.

    PASS holds only when ALL four gates hold simultaneously: no unresolved
    severity>threshold findings, execution SUCCESS, QA PASS, and no regressions.
    A failure of ANY single gate → not PASS. Pure and independently testable.
    """
    return (
        not list(unresolved_gt8)
        and exec_status == SUCCESS
        and qa_status == QA_PASS
        and not list(regressions)
    )


class AuditController:
    """Drives the §21 audit/repair loop and evaluates the four-gate PASS.

    Every loop-body dependency is injectable so the controller is deterministic
    and testable without a live LLM or kernel. The default wiring is static-only
    audit (plus the optional semantic ``backend``), a real :class:`NotebookExecutor`,
    :class:`RuntimeQA`, and a no-op patcher (repair strategy generation is the
    semantic LLM's job in the full system; the no-op patcher therefore leaves
    unpatchable findings unresolved, which correctly leads to FAILED).
    """

    DEFAULT_MAX_ITERATIONS = 10

    def __init__(
        self,
        config: AuditConfig | None = None,
        *,
        max_iterations: int | None = None,
        severity_threshold: int | None = None,
        auditor: AuditorFn | None = None,
        executor: ExecutorFn | None = None,
        qa: QAFn | None = None,
        patcher: PatcherFn | None = None,
        backend: Any | None = None,
        run_dir: str | os.PathLike[str] | None = None,
        wont_fix: Iterable[str] | None = None,
    ) -> None:
        self.config = config or AuditConfig()
        self.max_iterations = int(
            max_iterations
            if max_iterations is not None
            else self.config.audit.max_iterations
        )
        self.threshold = int(
            severity_threshold
            if severity_threshold is not None
            else self.config.audit.severity_threshold
        )
        self.backend = backend
        self.run_dir = run_dir

        self.auditor = auditor or self._default_auditor
        self.executor = executor or self._default_executor
        self.qa = qa or self._default_qa
        self.patcher = patcher or self._default_patcher

        # Cross-iteration state (report + recurrence).
        self.signature_store = SignatureStore()
        self.history: list[Finding] = []
        self._id_counter = 0
        self._attempted_corrections: dict[str, list[str]] = {}
        self._failure_reasons: dict[str, str] = {}
        self._wont_fix: set[str] = set(wont_fix or ())

    # -- default loop body -------------------------------------------------- #
    def _default_auditor(self, model: NotebookModel) -> list[Finding]:
        from nb_audit.static import default_registry

        findings = list(default_registry().run(model))
        if self.backend is not None:
            findings.extend(asyncio.run(self.backend.audit(model)))
        return findings

    def _default_executor(self, model: NotebookModel) -> ExecutionResult:
        executor = NotebookExecutor(
            config=self.config,
            run_dir=self.run_dir or Path.cwd(),
        )
        return executor.execute_sync(model.to_notebook())

    def _default_qa(self, model: NotebookModel, exec_result: ExecutionResult) -> QAResult:
        return RuntimeQA(config=self.config).run(model, exec_result)

    def _default_patcher(
        self,
        unresolved: list[Finding],
        model: NotebookModel,
        prior: dict[str, list[str]],
    ) -> PatchOutcome:
        # No deterministic correction generator without the semantic LLM; leave
        # findings unresolved (→ FAILED) rather than fabricate a patch.
        return PatchOutcome(model=model, corrections={})

    # -- user-only override ------------------------------------------------- #
    def mark_wont_fix(self, signature: str) -> None:
        """Mark a signature as user-accepted ``wont_fix`` (never auto-assigned)."""
        self._wont_fix.add(signature)

    # -- helpers ------------------------------------------------------------ #
    def _register(self, finding: Finding) -> Finding:
        """Assign signature/classification/id and accumulate history (flat)."""
        if not finding.signature:
            finding.signature = self.signature_store.compute(
                finding.root_cause, finding.category, finding.location
            )
        if finding.signature in self._wont_fix:
            finding.status = Status.WONT_FIX
        finding.classification = (
            Classification.RELATED_TO_OLD_ISSUE
            if finding.signature in self.signature_store
            else Classification.NEW
        )
        if not finding.id:
            self._id_counter += 1
            finding.id = f"F{self._id_counter:04d}"
        self.signature_store.remember(finding.signature, finding.id)
        self.history.append(finding)
        return finding

    def _blocking(self, findings: Iterable[Finding]) -> list[Finding]:
        """Findings that block PASS: severity>threshold and not terminal."""
        return [
            f
            for f in findings
            if f.severity > self.threshold and f.status not in _NON_BLOCKING
        ]

    def _is_materially_different(self, signature: str, correction: str) -> bool:
        prior = self._attempted_corrections.get(signature, [])
        if not correction:
            return False
        return all(correction != c for c in prior)

    def _prior_failure_reason(
        self, finding: Finding, previous_findings: list[Finding]
    ) -> str:
        attempts = self._attempted_corrections.get(finding.signature, [])
        if attempts:
            return (
                f"previous correction {attempts[-1]!r} did not eliminate "
                f"the root cause"
            )
        prior = next(
            (f for f in previous_findings if f.signature == finding.signature), None
        )
        if prior is not None:
            return f"issue persisted from a prior iteration: {prior.issue}"
        return ""

    def _transition_previous(
        self, previous_findings: list[Finding], current_signatures: frozenset[str]
    ) -> list[Finding]:
        """Move the PREVIOUS iteration's patched findings to their next state.

        A patched/recurring signature absent from the current re-audit is now
        ``resolved``; a signature that survives is ``recurring`` and its
        prior-failure reason is recorded. Returns the newly-recurring findings.
        """
        recurring: list[Finding] = []
        for finding in previous_findings:
            if finding.status not in _TRANSITIONABLE:
                continue
            if finding.signature in current_signatures:
                finding.status = Status.RECURRING
                self._failure_reasons[finding.signature] = self._prior_failure_reason(
                    finding, previous_findings
                )
                recurring.append(finding)
            else:
                finding.status = Status.RESOLVED
        return recurring

    def _apply_patches(
        self,
        blocking: list[Finding],
        model: NotebookModel,
        record: IterationRecord,
    ) -> PatchOutcome:
        prior = {
            sig: list(attempts) for sig, attempts in self._attempted_corrections.items()
        }
        outcome = self.patcher(list(blocking), model, prior)

        for finding in blocking:
            correction = outcome.corrections.get(finding.id)
            if correction is None:
                continue  # no correction available → keeps failing

            if not self._is_materially_different(finding.signature, correction):
                # §20: do NOT blindly repeat the same correction; keep failing.
                continue

            self._attempted_corrections.setdefault(finding.signature, []).append(
                correction
            )
            finding.patch_ids.append(correction)
            finding.status = Status.PATCHED
            record.corrections[finding.id] = correction

        return outcome

    # -- main entry --------------------------------------------------------- #
    def run(self, model: NotebookModel) -> AuditOutcome:
        """Run the §21 loop and return a PASS/FAILED :class:`AuditOutcome`."""
        current = model
        iterations: list[IterationRecord] = []
        previous_findings: list[Finding] = []

        for index in range(1, self.max_iterations + 1):
            # 1. FULL audit (static + optional semantic) — never just the patched cell.
            findings = [self._register(f) for f in self.auditor(current)]

            # 2. Execute + 3. runtime QA (always run, so the gates are evaluable).
            exec_result = self.executor(current)
            qa_result = self.qa(current, exec_result)

            # 4. Fold execution (sev-10) and QA findings into the set.
            if exec_result.finding is not None:
                findings.append(self._register(exec_result.finding))
            findings.extend(self._register(f) for f in qa_result.findings)

            unresolved_gt8 = self._blocking(findings)

            # 5. Regression + recurrence diff vs the previous iteration.
            if previous_findings:
                regression = detect_regressions(
                    previous_findings, findings, self.threshold
                )
            else:
                regression = RegressionResult()

            # 6. Lifecycle transition on the previous iteration's findings.
            self._transition_previous(previous_findings, signature_set(findings))

            record = IterationRecord(
                iteration=index,
                findings=findings,
                unresolved_gt8=unresolved_gt8,
                exec_status=exec_result.status,
                qa_status=qa_result.status,
                regressions=list(regression.regressions),
                recurring=list(regression.recurring),
            )
            iterations.append(record)

            # 7. Four-gate PASS check.
            if four_gate_pass(
                unresolved_gt8,
                exec_result.status,
                qa_result.status,
                regression.regressions,
            ):
                return AuditOutcome(
                    status=PASS,
                    iterations=iterations,
                    final_findings=findings,
                    max_iterations=self.max_iterations,
                    reason="four_gate_pass",
                )

            # 8. Patch the blocking findings and advance to the next iteration.
            outcome = self._apply_patches(unresolved_gt8, current, record)
            previous_findings = findings
            current = outcome.model

        return AuditOutcome(
            status=FAILED,
            iterations=iterations,
            final_findings=iterations[-1].findings if iterations else [],
            max_iterations=self.max_iterations,
            reason="max_iterations_exceeded",
        )
