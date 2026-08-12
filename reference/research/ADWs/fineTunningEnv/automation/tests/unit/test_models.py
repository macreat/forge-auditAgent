"""Tests for nb_audit.models — Finding, signatures, history, manager."""

from __future__ import annotations

from nb_audit.models import (
    Classification,
    Finding,
    FindingManager,
    IssueHistory,
    Location,
    SignatureStore,
    Status,
    clamp_severity,
    compute_signature,
)


def _finding(**overrides) -> Finding:
    base = dict(
        id="F1",
        severity=9,
        classification=Classification.NEW,
        category="leakage",
        location=Location(cell="train_cell", line=3),
        issue="Validation split overlaps train split.",
        root_cause="train_test_split called before feature engineering",
        impact="Inflated validation metrics.",
        correction="Move split before leakage-prone transforms.",
    )
    base.update(overrides)
    return Finding(**base)


# -- severity ---------------------------------------------------------------- #
def test_clamp_severity_bounds():
    assert clamp_severity(0) == 1
    assert clamp_severity(-5) == 1
    assert clamp_severity(5) == 5
    assert clamp_severity(11) == 10
    assert clamp_severity(99) == 10


def test_finding_clamps_severity_in_post_init():
    f = _finding(severity=42)
    assert f.severity == 10
    f2 = _finding(severity=0)
    assert f2.severity == 1


def test_severity_is_never_auto_lowered():
    f = _finding(severity=9)
    assert f.severity == 9  # stays as-is, not lowered
    f.status = Status.RESOLVED
    assert f.severity == 9  # status change never touches severity


# -- enums ------------------------------------------------------------------- #
def test_classification_values():
    assert Classification.NEW.value == "NEW"
    assert Classification.RELATED_TO_OLD_ISSUE.value == "RELATED_TO_OLD_ISSUE"


def test_status_values():
    assert {s.value for s in Status} == {
        "unresolved",
        "patched",
        "resolved",
        "recurring",
        "wont_fix",
    }


# -- signatures -------------------------------------------------------------- #
def test_signature_is_deterministic_and_wording_independent():
    loc = Location(cell="train_cell", line=3)
    a = compute_signature("root||cause", "leakage", loc)
    b = compute_signature("root||cause", "leakage", loc)
    assert a == b
    # wording (issue text) is NOT part of the signature
    c = compute_signature("root||cause", "leakage", Location(cell="train_cell", line=3))
    assert c == a


def test_signature_changes_with_root_cause_or_category_or_location():
    base = compute_signature("r", "leakage", Location(cell="c1"))
    assert compute_signature("r2", "leakage", Location(cell="c1")) != base
    assert compute_signature("r", "leakage2", Location(cell="c1")) != base
    assert compute_signature("r", "leakage", Location(cell="c2")) != base


def test_signature_store_remember_and_lookup():
    store = SignatureStore()
    sig = store.compute("root", "leakage", Location(cell="c1"))
    assert sig not in store
    store.remember(sig, "F1")
    assert sig in store
    assert store.lookup(sig) == "F1"


# -- classification ---------------------------------------------------------- #
def test_first_finding_is_new_second_same_signature_is_related():
    manager = FindingManager()
    first = _finding(id="", issue="validation overlap")
    manager.add(first)
    assert first.classification is Classification.NEW

    second = _finding(
        id="",
        issue="totally different wording",  # wording differs, signature does not
    )
    manager.add(second)
    assert second.classification is Classification.RELATED_TO_OLD_ISSUE


def test_different_root_cause_is_new():
    manager = FindingManager()
    first = _finding(id="")
    manager.add(first)
    assert first.classification is Classification.NEW

    second = _finding(id="", root_cause="a completely different root cause")
    manager.add(second)
    assert second.classification is Classification.NEW


def test_manager_assigns_ids_and_signatures():
    manager = FindingManager()
    f = _finding(id="")
    manager.add(f)
    assert f.id.startswith("F")
    assert f.signature


# -- status ------------------------------------------------------------------ #
def test_upgrade_status():
    manager = FindingManager()
    f = _finding(id="F1")
    manager.add(f)
    assert manager.upgrade_status("F1", Status.PATCHED).status is Status.PATCHED
    assert manager.upgrade_status("F1", "resolved").status is Status.RESOLVED
    assert manager.upgrade_status("missing", "resolved") is None


def test_find_filters():
    manager = FindingManager()
    manager.add(_finding(id="A", category="leakage", severity=9))
    manager.add(_finding(id="B", category="metrics", severity=5))
    manager.add(_finding(id="C", category="leakage", severity=3))
    assert len(manager.find(category="leakage")) == 2
    assert len(manager.find(severity_gt=8)) == 1
    assert manager.find(finding_id="B")[0].id == "B"
    assert len(manager.find(status=Status.UNRESOLVED)) == 3


# -- history ----------------------------------------------------------------- #
def test_history_survives_round_trip():
    manager = FindingManager()
    f = _finding(id="F1")
    manager.add(f)
    f.patch_ids.append("P1")
    manager.upgrade_status("F1", Status.PATCHED)

    raw = manager.history.to_raw()
    reloaded = IssueHistory.from_raw(raw)

    assert len(reloaded) == 1
    restored = reloaded.get("F1")
    assert restored is not None
    assert restored.severity == 9
    assert restored.status is Status.PATCHED
    assert restored.patch_ids == ["P1"]
    assert restored.signature == f.signature


def test_history_preserves_order_and_dedupes():
    manager = FindingManager()
    f = _finding(id="F1")
    manager.add(f)
    manager.add(f)  # re-add same id should not duplicate order entry
    assert [x.id for x in manager.history.all()] == ["F1"]
