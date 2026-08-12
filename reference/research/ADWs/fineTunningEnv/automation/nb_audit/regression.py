"""Full-notebook regression audit (spec §19, REQ-009).

After every patch the pipeline must re-audit the WHOLE notebook — never only the
patched cell. This module compares the post-patch finding set against the
previous iteration's set **by signature** (the hash of
``root_cause || category || location``, never by wording) and:

- tags any NEW severity > threshold finding as a ``regression`` (a
  patch-induced failure that must BLOCK PASS via the independent regression
  gate), and
- identifies ``recurring`` signatures (a root cause that survived the patch and
  is still unresolved), which the iteration controller uses to require a
  materially different correction (§20).

It is a pure, deterministic function of two finding lists: no LLM, no execution,
no notebook mutation. The only side effect is setting ``finding.regression =
True`` on the tagged findings, mirroring the in-place id/classification
assignment the registries already perform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from nb_audit.models import Finding, Status


@dataclass
class RegressionResult:
    """Outcome of comparing a post-patch finding set to the prior iteration."""

    previous_signatures: frozenset[str] = field(default_factory=frozenset)
    new_findings: list[Finding] = field(default_factory=list)
    regressions: list[Finding] = field(default_factory=list)
    recurring: list[Finding] = field(default_factory=list)

    @property
    def has_regression(self) -> bool:
        """True when at least one patch-induced severity>threshold finding exists."""
        return bool(self.regressions)

    @property
    def none(self) -> bool:
        """True when there is no regression — the regression gate holds."""
        return not self.regressions


def signature_set(findings: Iterable[Finding]) -> frozenset[str]:
    """Return the set of signatures for ``findings`` (deduplicated)."""
    return frozenset(f.signature for f in findings)


def detect_regressions(
    previous: Iterable[Finding],
    current: Iterable[Finding],
    severity_threshold: int = 8,
) -> RegressionResult:
    """Diff the current finding set against the previous iteration by signature.

    - A signature present now but absent before is a *new* finding. When it is
      severity > ``severity_threshold`` it is tagged ``regression=True`` on the
      finding and recorded as a regression. On the FIRST iteration ``previous``
      is empty, so nothing is tagged — an original issue is not a patch-induced
      regression.
    - A signature present before AND still unresolved now is *recurring*: the
      patch did not eliminate the root cause.
    """
    prev_sigs = signature_set(previous)
    has_prior = bool(prev_sigs)

    result = RegressionResult(previous_signatures=prev_sigs)
    for finding in current:
        if finding.signature in prev_sigs:
            if finding.status == Status.UNRESOLVED:
                result.recurring.append(finding)
        else:
            result.new_findings.append(finding)
            if has_prior and finding.severity > severity_threshold:
                finding.regression = True
                result.regressions.append(finding)
    return result
