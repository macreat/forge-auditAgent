"""Tests for nb_audit.repair.root_cause — RootCause dataclass + from_finding."""

from __future__ import annotations

import dataclasses

import pytest

from nb_audit.models import Classification, Finding, Location
from nb_audit.repair.root_cause import (
    CATEGORY_SECTION,
    IR_CHAIN,
    RootCause,
    RootCauseNotRequired,
    downstream_sections,
    section_for,
)


def _finding(**overrides) -> Finding:
    base = dict(
        id="F1",
        severity=9,
        classification=Classification.NEW,
        category="splits",
        location=Location(cell="c1", line=3),
        issue="Validation split overlaps train split.",
        root_cause="Split performed before leakage-prone preprocessing",
        impact="Inflated validation metrics.",
        correction="Move the split before preprocessing.",
    )
    base.update(overrides)
    return Finding(**base)


# -- structure ---------------------------------------------------------------- #
def test_root_cause_has_exactly_8_fields():
    names = [f.name for f in dataclasses.fields(RootCause)]
    assert names == [
        "issue",
        "location",
        "severity",
        "classification",
        "root_cause",
        "impact",
        "correction",
        "downstream",
    ]


def test_from_finding_populates_all_8_fields():
    f = _finding()
    rc = RootCause.from_finding(f)
    assert rc.issue == f.issue
    assert rc.location == f.location
    assert rc.severity == 9
    assert rc.classification is Classification.NEW
    assert rc.root_cause == f.root_cause
    assert rc.impact == f.impact
    assert rc.correction == f.correction
    assert isinstance(rc.downstream, tuple)


def test_from_finding_derives_downstream_from_category():
    rc = RootCause.from_finding(_finding(category="splits"))
    assert "metrics" in rc.downstream
    assert "plots" in rc.downstream
    assert "conclusions" in rc.downstream


def test_from_finding_refuses_severity_below_9():
    with pytest.raises(RootCauseNotRequired):
        RootCause.from_finding(_finding(severity=8))
    with pytest.raises(RootCauseNotRequired):
        RootCause.from_finding(_finding(severity=5))
    # severity is never auto-lowered into patchable range
    with pytest.raises(RootCauseNotRequired):
        RootCause.from_finding(_finding(severity=8))


def test_rca_never_lowers_severity():
    rc = RootCause.from_finding(_finding(severity=10))
    assert rc.severity == 10


# -- chain / mapping ---------------------------------------------------------- #
def test_chain_order_matches_spec():
    assert IR_CHAIN == (
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


def test_section_mapping():
    assert section_for("leakage") == "data"
    assert section_for("splits") == "data"
    assert section_for("tensors") == "train"
    assert section_for("metrics") == "metrics"
    assert section_for("checkpoints") == "artifacts"
    assert section_for("unknown-category") == "data"  # conservative fallback


def test_downstream_sections_are_exclusive_and_ordered():
    assert downstream_sections("metrics") == (
        "plots",
        "artifacts",
        "conclusions",
        "qa",
    )
    assert downstream_sections("qa") == ()
    assert downstream_sections("data") == IR_CHAIN[1:]


def test_categories_are_registered_in_category_section():
    assert CATEGORY_SECTION["splits"] == "data"
    assert CATEGORY_SECTION["leakage"] == "data"
