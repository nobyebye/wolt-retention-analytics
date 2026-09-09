from datetime import date
import pytest
from wolt_analytics.data import Purchase, read_source, reconcile


def p(pid="a", user="u", day=1, line="Restaurant"):
    return Purchase(pid, user, "venue", line, date(2020, 5, day))


def test_bom_and_date_contract(tmp_path):
    path = tmp_path / "first.csv"
    path.write_text(
        "first_purchase_date,user_id,purchase_id,venue_id,product_line\n01.05.20,u,a,v,Restaurant\n",
        encoding="utf-8-sig",
    )
    parsed, raw = read_source(path, True)
    assert parsed[0].purchase_date == date(2020, 5, 1)
    assert raw[0][0] == 2


def test_unknown_user_is_quarantined_without_changing_denominator():
    anchors, events, rejected, stats = reconcile(
        [p()], [p("b", "other")], date(2020, 6, 30)
    )
    assert len(anchors) == len(events) == 1
    assert rejected[0][1] == "unknown_first_purchase_user"
    assert stats["unknown_users"] == 1


def test_pre_first_purchase_is_quarantined():
    _, events, rejected, _ = reconcile([p(day=3)], [p("b", day=2)], date(2020, 6, 30))
    assert len(events) == 1
    assert rejected[0][1] == "purchase_before_first_purchase"


def test_exact_duplicates_are_idempotent():
    _, events, _, stats = reconcile([p()], [p(), p("b"), p("b")], date(2020, 6, 30))
    assert len(events) == 2
    assert stats["exact_duplicates"] == 2


def test_conflicting_purchase_fails():
    with pytest.raises(ValueError, match="Conflicting"):
        reconcile([p()], [p(day=2)], date(2020, 6, 30))


def test_future_data_fails():
    with pytest.raises(ValueError, match="as-of"):
        reconcile([p(day=3)], [], date(2020, 5, 2))


@pytest.mark.parametrize(
    "row",
    ["01.05.20,,a,v,Restaurant", "32.05.20,u,a,v,Restaurant", "01.05.20,u,a,v,Unknown"],
)
def test_invalid_source_fails(tmp_path, row):
    path = tmp_path / "bad.csv"
    path.write_text(
        "purchase_date,user_id,purchase_id,venue_id,product_line\n" + row + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        read_source(path)
