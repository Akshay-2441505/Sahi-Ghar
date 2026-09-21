from datetime import date

from sahighar.adapters.base import complaint_stage
from sahighar.scoring.v1 import ComplaintFacts as C
from sahighar.scoring.v1 import ProjectFacts as P
from sahighar.scoring.v1 import classify, score

TODAY = date(2026, 9, 1)


def test_classify_is_measured_against_the_original_end_date():
    assert classify(P(date(2022, 1, 1), date(2023, 1, 1)), TODAY) == ("extended", 12.0)
    assert classify(P(date(2022, 1, 1), None), TODAY) == ("not_extended", None)
    assert classify(P(date(2027, 1, 1), None), TODAY) == ("within_registration", None)


def test_extension_counts_even_if_the_original_date_has_not_passed():
    assert classify(P(date(2027, 1, 1), date(2027, 7, 1)), TODAY)[0] == "extended"


def test_unknown_when_data_missing_or_nonsensical():
    assert classify(P(None, None), TODAY) == ("unknown", None)
    assert classify(P(date(2022, 1, 1), date(2021, 1, 1)), TODAY)[0] == "not_extended"  # "extension" that moves earlier


def test_complaint_stage_maps_known_statuses_and_never_guesses():
    assert complaint_stage("Order Approved") == "order_issued"
    assert complaint_stage("  hearing scheduled ") == "pending"
    assert complaint_stage("Roznama Approved") == "pending"
    assert complaint_stage("Something New") == "other"


def test_score_with_history_and_complaints():
    projects = [P(date(2022, 1, 1), None), P(date(2022, 1, 1), None), P(date(2022, 1, 1), date(2023, 1, 1))]
    complaints = [C("pending", False), C("order_issued", False), C("order_issued", True)]
    s = score(projects, complaints, TODAY)
    assert s["schedule"]["score"] == 67 and s["schedule"]["extended"] == 1 and s["schedule"]["median_months_extended"] == 12.0
    assert s["complaints"]["unresolved"] == 2  # one pending, one order not executed
    assert (s["complaints"]["total"], s["complaints"]["pending"], s["complaints"]["order_issued"],
            s["complaints"]["order_not_executed"]) == (3, 1, 2, 1)
    assert s["complaints"]["score"] == 33  # 100 * (1 - 2/3)
    assert s["progress"]["available"] is False
    assert s["overall"] == 50


def test_pending_and_not_executed_on_one_complaint_count_once():
    s = score([P(date(2022, 1, 1), None)], [C("pending", True)], TODAY)
    assert s["complaints"]["unresolved"] == 1 and s["complaints"]["score"] == 0


def test_insufficient_history_still_scores_complaints():
    projects = [P(date(2022, 1, 1), None), P(date(2027, 1, 1), None)]
    s = score(projects, [], TODAY)
    assert s["schedule"]["available"] is False and s["schedule"]["reason"] == "insufficient_history"
    assert s["complaints"]["score"] == 100
    assert s["overall"] == 100


def test_no_projects_means_not_enough_data():
    s = score([], [], TODAY)
    assert s["overall"] is None and s["complaints"]["reason"] == "no_projects"
