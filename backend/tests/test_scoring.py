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
    assert s["overall"] is None  # one section alone (here: no complaints on record) is not a reason to show 100/100


def test_no_projects_means_not_enough_data():
    s = score([], [], TODAY)
    assert s["overall"] is None and s["complaints"]["reason"] == "no_projects"


def test_complaints_not_collected_is_unknown_never_clean():
    projects = [P(date(2022, 1, 1), None), P(date(2022, 1, 1), date(2023, 1, 1))]
    s = score(projects, [], TODAY, complaints_known=False)
    assert s["complaints"]["available"] is False and s["complaints"]["reason"] == "not_collected"
    assert s["complaints"]["score"] is None
    assert s["schedule"]["score"] == 50 and s["overall"] is None  # one known section is shown as itself, not as an overall


def test_overall_needs_at_least_two_sections_with_data():
    from sahighar.scoring.v1 import DeclaredFacts as D
    projects = [P(date(2022, 1, 1), None), P(date(2022, 1, 1), date(2023, 1, 1))]
    declared = [D(date(2015, 3, 10), date(2015, 1, 10)), D(date(2014, 8, 20), date(2014, 8, 20))]
    assert score(projects, [], TODAY, complaints_known=False)["overall"] is None
    assert score(projects, [], TODAY, complaints_known=False, declared=declared)["overall"] == 75


def test_nothing_known_at_all_is_not_enough_data():
    assert score([P(date(2027, 1, 1), None)], [], TODAY, complaints_known=False)["overall"] is None


HISTORY = [{"label": "Extension-1", "revised_end": "2020-12-30"}, {"label": "Covid Extension -2", "revised_end": "2021-03-30"},
           {"label": "Covid Extension -3", "revised_end": "2021-06-30"}, {"label": "Covid Extension -4", "revised_end": "2021-12-30"},
           {"label": "Extension-5", "revised_end": "2027-12-31"}]


def test_covid_relief_days_are_only_the_steps_labelled_covid():
    from sahighar.scoring.v1 import covid_days
    assert covid_days(HISTORY, date(2019, 12, 31)) == 90 + 92 + 183
    assert covid_days(None, date(2019, 12, 31)) == 0 and covid_days([], date(2019, 12, 31)) == 0
    assert covid_days(HISTORY, None) == 0  # no original date, no way to measure the steps


def test_own_extension_months_leave_out_covid_relief():
    facts = P(date(2019, 12, 31), date(2027, 12, 31), covid_days=365)
    assert classify(facts, TODAY) == ("extended", 84.0)  # 96 months in all, 12 of them COVID relief


def test_an_extension_that_is_only_covid_relief_is_its_own_outcome():
    assert classify(P(date(2020, 12, 31), date(2021, 6, 30), covid_days=181), TODAY) == ("covid_only", None)


def test_covid_only_counts_on_the_no_own_extension_side_of_the_schedule_score():
    projects = [P(date(2022, 1, 1), None), P(date(2020, 12, 31), date(2021, 6, 30), covid_days=181),
                P(date(2019, 12, 31), date(2027, 12, 31), covid_days=365)]
    s = score(projects, [], TODAY, complaints_known=False)["schedule"]
    assert (s["not_extended"], s["covid_only"], s["extended"], s["score"]) == (1, 1, 1, 67)
    assert s["median_months_extended"] == 84.0


def test_declared_delivery_counts_on_or_before_the_proposed_date_and_measures_the_rest():
    from sahighar.scoring.v1 import DeclaredFacts as D
    declared = [D(date(2015, 3, 10), date(2015, 1, 10)), D(date(2013, 11, 30), date(2015, 4, 27)), D(date(2014, 8, 20), date(2014, 8, 20)),
                D(date(2014, 12, 31), date(2017, 7, 12))]
    s = score([], [], TODAY, complaints_known=False, declared=declared)["declared"]
    assert (s["available"], s["total"], s["on_or_before"], s["later"], s["score"]) == (True, 4, 2, 2, 50)
    assert s["median_months_later"] == 23.65  # 513 days (16.9 months) and 924 days (30.4 months)


def test_declared_delivery_needs_at_least_two_completed_projects():
    from sahighar.scoring.v1 import DeclaredFacts as D
    one = score([], [], TODAY, complaints_known=False, declared=[D(date(2015, 3, 10), date(2015, 1, 10))])["declared"]
    assert one["available"] is False and one["reason"] == "insufficient_history" and one["score"] is None
    none = score([], [], TODAY, complaints_known=False)["declared"]
    assert none["available"] is False and none["total"] == 0


def test_declared_delivery_feeds_the_overall_only_when_available():
    from sahighar.scoring.v1 import DeclaredFacts as D
    declared = [D(date(2015, 3, 10), date(2015, 1, 10)), D(date(2014, 8, 20), date(2014, 8, 20))]  # 2 of 2 on or before: 100
    projects = [P(date(2022, 1, 1), None), P(date(2022, 1, 1), date(2023, 1, 1))]  # schedule score 50
    s = score(projects, [], TODAY, complaints_known=False, declared=declared)
    assert s["declared"]["score"] == 100 and s["schedule"]["score"] == 50 and s["overall"] == 75
