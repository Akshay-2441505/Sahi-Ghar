import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sahighar.db.models import GroupMembership, Promoter, PromoterGroup, ScoreSnapshot

NAME_SIMILARITY_THRESHOLD = 90


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def _partners(p: Promoter) -> set[str]:
    return {_norm(n) for n in (p.partners_or_directors or [])} - {""}


@dataclass
class Link:
    promoter_id: int
    link_type: str  # filing_confirmed | possible
    evidence: dict


@dataclass
class GroupResult:
    members: list[Link] = field(default_factory=list)


def resolve_groups(promoters: list[Promoter]) -> list[GroupResult]:
    """Rule-based grouping. Pure: takes Promoter objects, returns groups; touches no database.

    filing_confirmed: same PAN (union-find, so links are transitive).
    possible: (overlapping named partner/director AND (same normalised address OR similar name))
              OR (same normalised address AND similar name).
    A single weak signal alone never links anything.
    """
    parent = {p.id: p.id for p in promoters}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_pan: dict[str, list[Promoter]] = {}
    for p in promoters:
        pan = (p.pan or "").strip().upper()
        if pan:
            by_pan.setdefault(pan, []).append(p)
    for same in by_pan.values():
        for other in same[1:]:
            parent[find(other.id)] = find(same[0].id)

    components: dict[int, list[Promoter]] = {}
    for p in promoters:
        components.setdefault(find(p.id), []).append(p)

    groups: dict[int, GroupResult] = {}
    for root, members in components.items():
        pan = (members[0].pan or "").strip().upper()
        evidence = {"basis": "pan", "pan": pan} if len(members) > 1 else {"basis": "single_entity"}
        groups[root] = GroupResult([Link(m.id, "filing_confirmed", dict(evidence)) for m in members])

    # Every `possible` rule needs a shared partner or a shared address, so candidate pairs are
    # built from those two indexes only. ponytail: a very common address (a co-working space) makes
    # O(k^2) pairs; cap or skip oversized buckets if that ever shows up in real data.
    by_partner: dict[str, list[Promoter]] = {}
    by_address: dict[str, list[Promoter]] = {}
    for p in promoters:
        for name in _partners(p):
            by_partner.setdefault(name, []).append(p)
        if _norm(p.registered_address):
            by_address.setdefault(_norm(p.registered_address), []).append(p)
    pairs: set[tuple[int, int]] = set()
    for index in (by_partner, by_address):
        for people in index.values():
            for i, a in enumerate(people):
                for b in people[i + 1:]:
                    if find(a.id) != find(b.id):
                        pairs.add((min(a.id, b.id), max(a.id, b.id)))

    by_id = {p.id: p for p in promoters}
    for a_id, b_id in pairs:
        a, b = by_id[a_id], by_id[b_id]
        shared = sorted(_partners(a) & _partners(b))
        same_address = bool(_norm(a.registered_address)) and _norm(a.registered_address) == _norm(b.registered_address)
        similarity = fuzz.token_set_ratio(_norm(a.name), _norm(b.name))
        similar_name = similarity >= NAME_SIMILARITY_THRESHOLD
        if not ((shared and (same_address or similar_name)) or (same_address and similar_name)):
            continue
        # only a count: partners and directors are personal data, used to match and never shown
        evidence = {"shared_count": len(shared), "same_address": same_address, "name_similarity": round(similarity)}
        for host, guest in ((a, b), (b, a)):
            group = groups[find(host.id)]
            if all(m.promoter_id != guest.id for m in group.members):
                group.members.append(Link(guest.id, "possible", dict(evidence)))

    return sorted(groups.values(), key=lambda g: min(m.promoter_id for m in g.members))


def rebuild_groups(session: Session) -> int:
    # ponytail: full rebuild each run (also drops score snapshots, which reference group ids);
    # keep history / stable group ids only if it is ever needed.
    session.execute(delete(ScoreSnapshot))
    session.execute(delete(GroupMembership))
    session.execute(delete(PromoterGroup))
    groups = resolve_groups(list(session.scalars(select(Promoter))))
    for g in groups:
        row = PromoterGroup()
        session.add(row)
        session.flush()
        for m in g.members:
            session.add(GroupMembership(group_id=row.id, promoter_id=m.promoter_id, link_type=m.link_type, evidence=m.evidence))
    session.commit()
    return len(groups)
