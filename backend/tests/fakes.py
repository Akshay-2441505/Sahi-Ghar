import json
from datetime import date

from sahighar.adapters.base import ComplaintRec, ParsedRecords, ProjectRec, PromoterRec, RawDoc, complaint_stage
from sahighar.util import utcnow


def _d(value):
    return date.fromisoformat(value) if value else None


class FakeAdapter:
    """Test double. Each payload is a JSON document {promoters, projects, complaints} keyed by url."""

    state = "MH"
    origin = "fake"

    def __init__(self, payloads: dict[str, dict]):
        self.payloads = payloads

    def discover(self):
        for url, payload in self.payloads.items():
            yield RawDoc(self.origin, "project", url, utcnow(), "application/json", json.dumps(payload).encode())

    def parse(self, doc: RawDoc) -> ParsedRecords:
        d = json.loads(doc.data)
        return ParsedRecords(
            promoters=[PromoterRec(**x) for x in d.get("promoters", [])],
            projects=[
                ProjectRec(**{**x, "registration_end": _d(x.get("registration_end")), "extended_end": _d(x.get("extended_end"))})
                for x in d.get("projects", [])
            ],
            complaints=[ComplaintRec(**{**x, "stage": complaint_stage(x["status"])}) for x in d.get("complaints", [])],
        )
