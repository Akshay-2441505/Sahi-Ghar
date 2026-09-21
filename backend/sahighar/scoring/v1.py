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
MIN_SECTIONS_FOR_OVERALL = 2  # one section alone (e.g. "no complaints on record") must not read as a 100/100 record
DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class ProjectFacts:
    registration_end: date | None  # end of the original registration validity
    extended_end: date | None  # new end date, only if an extension certificate exists
    covid_days: int = 0  # days of the extension granted under COVID-19 relief (see covid_days())


def covid_days(history: list[dict] | None, original_end: date | None) -> int:
    """Days of extension the certificate labels "Covid Extension", walking its steps from the original end date.

    Only certificates that list their extensions carry this; without a history (or an original date to measure
    from) nothing is separated out and 0 is returned."""
    if not history or original_end is None:
        return 0
    total, previous = 0, original_end
    for step in history:
        revised = date.fromisoformat(step["revised_end"])
        if revised > previous:
            if "covid" in step["label"].lower():
                total += (revised - previous).days
            previous = revised
    return total


@dataclass(frozen=True)
class ComplaintFacts:
    stage: str  # order_issued | pending | other
    non_execution_applied: bool


@dataclass(frozen=True)
class DeclaredFacts:
    """A completed project the promoter declared in its registration application (its own account, not verified)."""
    original_proposed: date
    actual: date


MIN_DECLARED_PROJECTS = 2


def _months(days: int) -> float:
    return round(days / DAYS_PER_MONTH, 1)


def classify(p: ProjectFacts, today: date) -> tuple[str, float | None]:
    """Return (outcome, months_extended). Outcome: extended | covid_only | not_extended | within_registration | unknown.

    Measured against the ORIGINAL registration end date: an extension never hides in the numbers. Days granted under
    COVID-19 relief are left out of months_extended; an extension that is nothing but COVID-19 relief is "covid_only".
    """
    if p.registration_end is None:
        return "unknown", None
    if p.extended_end is not None and p.extended_end > p.registration_end:
        own_days = (p.extended_end - p.registration_end).days - p.covid_days
        return ("extended", _months(own_days)) if own_days > 0 else ("covid_only", None)
    if p.registration_end < today:
        return "not_extended", None
    return "within_registration", None


def score(projects: list[ProjectFacts], complaints: list[ComplaintFacts], today: date, complaints_known: bool = True,
          declared: list[DeclaredFacts] | None = None, notices: int = 0) -> dict:
    """complaints_known: False when complaints were never collected for this builder. Then the complaint section is
    unavailable ("not_collected"), because an empty list would otherwise read as a clean record.
    notices: how many notices MahaRERA publishes about this builder's projects (kept in abeyance, NCLT). They are shown
    beside the sections, never averaged in, and the overall is withheld while any exist."""
    outcomes = [classify(p, today) for p in projects]
    counts = Counter(outcome for outcome, _ in outcomes)
    evaluated = counts["extended"] + counts["covid_only"] + counts["not_extended"]
    months = [m for outcome, m in outcomes if outcome == "extended"]
    schedule_ok = evaluated >= MIN_EVALUATED_PROJECTS
    schedule = {
        "available": schedule_ok,
        "reason": None if schedule_ok else "insufficient_history",
        "score": round(100 * (counts["not_extended"] + counts["covid_only"]) / evaluated) if schedule_ok else None,
        "extended": counts["extended"],
        "not_extended": counts["not_extended"],
        "covid_only": counts["covid_only"],
        "within_registration": counts["within_registration"],
        "unknown": counts["unknown"],
        "median_months_extended": median(months) if months else None,
    }

    n = len(projects)
    unresolved = sum(c.stage == "pending" or c.non_execution_applied for c in complaints)
    complaints_ok = complaints_known and n > 0
    complaint_summary = {
        "available": complaints_ok,
        "reason": None if complaints_ok else ("not_collected" if not complaints_known else "no_projects"),
        "score": round(100 * max(0.0, 1 - unresolved / n)) if complaints_ok else None,
        "total": len(complaints),
        "pending": sum(c.stage == "pending" for c in complaints),
        "order_issued": sum(c.stage == "order_issued" for c in complaints),
        "order_not_executed": sum(c.non_execution_applied for c in complaints),
        "unresolved": unresolved,
        "project_count": n,
    }

    declared = declared or []
    later_months = [_months((d.actual - d.original_proposed).days) for d in declared if d.actual > d.original_proposed]
    on_or_before = sum(d.actual <= d.original_proposed for d in declared)
    declared_ok = len(declared) >= MIN_DECLARED_PROJECTS
    declared_summary = {
        "available": declared_ok,
        "reason": None if declared_ok else "insufficient_history",
        "score": round(100 * on_or_before / len(declared)) if declared_ok else None,
        "total": len(declared),
        "on_or_before": on_or_before,
        "later": len(later_months),
        "median_months_later": median(later_months) if later_months else None,
    }

    available = [c["score"] for c in (schedule, complaint_summary, declared_summary) if c["available"]]
    return {
        "schedule": schedule,
        "complaints": complaint_summary,
        "declared": declared_summary,
        "progress": {"available": False, "reason": "not_yet_available", "score": None},
        "notices": {"count": notices},
        "overall": round(mean(available)) if len(available) >= MIN_SECTIONS_FOR_OVERALL and not notices else None,
    }
