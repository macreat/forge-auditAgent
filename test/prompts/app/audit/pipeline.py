"""AuditPipeline — orchestrates sequential execution of all audit passes.

The pipeline runs each pass in order, catches errors per pass (continuing
to the next), and supports optional progress callbacks for UI updates.
"""

from __future__ import annotations

import datetime

from app.audit import (
    pass1_structural,
    pass2_reproducibility,
    pass3_data_integrity,
    pass4_ml_correctness,
    pass5_code_quality,
    pass6_deployment,
)
from app.audit.models import AuditReport, Notebook, PassResult


class AuditPipeline:
    """Orchestrates sequential execution of the six audit passes.

    Attributes:
        passes: List of ``(number, name, module)`` tuples defining the
            audit passes and their execution order. Each module must
            expose a ``run(notebook, focus_areas=None)`` function that
            returns a :class:`PassResult`.
    """

    def __init__(self):
        self.passes = [
            (1, "Structural Overview", pass1_structural),
            (2, "Reproducibility", pass2_reproducibility),
            (3, "Data Integrity", pass3_data_integrity),
            (4, "ML Correctness", pass4_ml_correctness),
            (5, "Code Quality", pass5_code_quality),
            (6, "Deployment Readiness", pass6_deployment),
        ]

    def run(
        self,
        notebook: Notebook,
        focus_areas: list[str] | None = None,
        progress_cb=None,
    ) -> AuditReport:
        """Execute all (or scoped) audit passes sequentially.

        Each pass is called in order. If a pass raises an exception,
        it is caught and a ``PassResult`` with ``status="error"`` is
        used instead. When ``focus_areas`` is non-empty, only passes
        whose name matches an entry are executed.

        Args:
            notebook: The parsed notebook to audit.
            focus_areas: Optional list of pass name substrings to scope
                the audit. Passes whose name (case-insensitive) contains
                any entry are executed; others are skipped. ``None`` or
                an empty list runs all passes.
            progress_cb: Optional callback invoked after each pass
                completes. Receives the :class:`PassResult` as its sole
                argument.

        Returns:
            An :class:`AuditReport` aggregating all pass results.
        """
        results: list[PassResult] = []
        focus_lower = [f.lower() for f in (focus_areas or [])]

        for num, name, pass_mod in self.passes:
            # Skip if focus_areas is non-empty and this pass is out of scope
            if focus_lower and not any(f in name.lower() for f in focus_lower):
                continue

            try:
                result = pass_mod.run(notebook, focus_areas)
            except Exception as exc:
                result = PassResult(
                    pass_name=name,
                    pass_number=num,
                    score=None,
                    status="error",
                    findings=[],
                    deliverable_text=f"Error: {exc}",
                )

            results.append(result)
            if progress_cb:
                progress_cb(result)

        total_possible = len(self.passes)
        total_run = len(results)
        status = "complete" if total_run == total_possible else "partial"

        return AuditReport(
            notebook_name=notebook.filename,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            status=status,
            focus_areas=focus_areas or [],
            passes=results,
        )
