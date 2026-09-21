"""Trust score v1: a scored checklist, not ML. All tunable numbers live here.

Every sub-score is shown with its inputs; the overall number is never shown alone.
Wording is neutral: an extension is not necessarily the promoter's fault, and a project past
its end date without an extension may simply have been completed, so neither is called "late".
"""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from statistics import mean, median

MIN_EVALUATED_PROJECTS = 2  # fewer evaluated projects -> "insufficient history"
DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class ProjectFacts:
    registration_end: date | None  # end of the original registration validity
    extended_end: date | None  # new end date, only if an extension certificate exists


@dataclass(frozen=True)
class ComplaintFacts:
    stage: str  # order_issued | pending | other
    non_execution_applied: bool


def _months(days: int) -> float:
    return round(days / DAYS_PER_MONTH, 1)


def classify(p: ProjectFacts, today: date) -> tuple[str, float | None]:
    """Return (outcome, months_extended). Outcome: extended | not_extended | within_registration | unknown.

    Measured against the ORIGINAL registration end date: an extension never hides in the numbers.
    """
    if p.registration_end is None:
        return "unknown", None
    if p.extended_end is not None and p.extended_end > p.registration_end:
        return "extended", _months((p.extended_end - p.registration_end).days)
    if p.registration_end < today:
        return "not_extended", None
    return "within_registration", None


def score(projects: list[ProjectFacts], complaints: list[ComplaintFacts], today: date) -> dict:
    outcomes = [classify(p, today) for p in projects]
    counts = Counter(outcome for outcome, _ in outcomes)
    evaluated = counts["extended"] + counts["not_extended"]
    months = [m for outcome, m in outcomes if outcome == "extended"]
    schedule_ok = evaluated >= MIN_EVALUATED_PROJECTS
    schedule = {
        "available": schedule_ok,
        "reason": None if schedule_ok else "insufficient_history",
        "score": round(100 * counts["not_extended"] / evaluated) if schedule_ok else None,
        "extended": counts["extended"],
        "not_extended": counts["not_extended"],
        "within_registration": counts["within_registration"],
        "unknown": counts["unknown"],
        "median_months_extended": median(months) if months else None,
    }

    n = len(projects)
    unresolved = sum(c.stage == "pending" or c.non_execution_applied for c in complaints)
    complaint_summary = {
        "available": n > 0,
        "reason": None if n > 0 else "no_projects",
        "score": round(100 * max(0.0, 1 - unresolved / n)) if n > 0 else None,
        "total": len(complaints),
        "pending": sum(c.stage == "pending" for c in complaints),
        "order_issued": sum(c.stage == "order_issued" for c in complaints),
        "order_not_executed": sum(c.non_execution_applied for c in complaints),
        "unresolved": unresolved,
        "project_count": n,
    }

    available = [c["score"] for c in (schedule, complaint_summary) if c["available"]]
    return {
        "schedule": schedule,
        "complaints": complaint_summary,
        "progress": {"available": False, "reason": "not_yet_available", "score": None},
        "overall": round(mean(available)) if available else None,
    }
