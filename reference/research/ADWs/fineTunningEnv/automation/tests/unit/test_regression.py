"""Tests for nb_audit.regression — signature-diff based regression detection."""

from __future__ import annotations

from nb_audit.models import Classification, Finding, Location, Status
from nb_audit.regression import RegressionResult, detect_regressions, signature_set


def _finding(
    *,
    severity: int = 9,
    category: str = "leakage",
    cell: str = "c1",
    root_cause: str = "partitions are not disjoint",
    status: Status = Status.UNRESOLVED,
) -> Finding:
    return Finding(
        id="",
        severity=severity,
        classification=Classification.NEW,
        category=category,
        location=Location(cell=cell, line=1),
        issue="data leakage",
        root_cause=root_cause,
        status=status,
    )


# -- signature_set ------------------------------------------------------------ #
def test_signature_set_dedupes():
    a = _finding(cell="c1")
    b = _finding(cell="c1")  # same signature
    c = _finding(cell="c2")  # different location → different signature
    sigs = signature_set([a, b, c])
    assert len(sigs) == 2


# -- regressions (patch-induced severity>threshold) ---------------------------- #
def test_new_severity_9_finding_is_tagged_regression():
    prev = [_finding(cell="c1")]
    current = [_finding(cell="c1"), _finding(cell="c2", severity=9)]
    result = detect_regressions(prev, current)

    assert [f.location.cell for f in result.regressions] == ["c2"]
    assert result.new_findings[0].location.cell == "c2"
    assert result.regressions[0].regression is True
    assert result.has_regression
    assert not result.none


def test_new_finding_below_threshold_is_not_regression():
    prev = [_finding(cell="c1")]
    current = [_finding(cell="c1"), _finding(cell="c2", severity=8)]
    result = detect_regressions(prev, current)

    assert result.regressions == []
    assert len(result.new_findings) == 1
    assert result.new_findings[0].regression is False
    assert result.none


def test_first_iteration_never_tags_regression():
    # previous empty → original issues are NOT patch-induced regressions.
    current = [_finding(cell="c1", severity=9)]
    result = detect_regressions([], current)

    assert result.regressions == []
    assert len(result.new_findings) == 1
    assert current[0].regression is False


# -- recurring (signature survived the patch) --------------------------------- #
def test_persisting_unresolved_signature_is_recurring():
    prev = [_finding(cell="c1")]
    current = [_finding(cell="c1")]  # same signature, still unresolved
    result = detect_regressions(prev, current)

    assert len(result.recurring) == 1
    assert result.recurring[0].signature == prev[0].signature
    assert result.regressions == []  # not new → not a regression


def test_resolved_signature_is_not_recurring():
    prev = [_finding(cell="c1")]
    current = [_finding(cell="c1", status=Status.RESOLVED)]
    result = detect_regressions(prev, current)

    assert result.recurring == []


def test_regression_flag_round_trips():
    finding = _finding(cell="c1", severity=9)
    detect_regressions([_finding(cell="c2")], [finding])
    assert finding.regression is True

    restored = Finding.from_raw(finding.to_raw())
    assert restored.regression is True


def test_empty_result_is_safe():
    result = RegressionResult()
    assert result.none
    assert not result.has_regression
    assert result.regressions == []
