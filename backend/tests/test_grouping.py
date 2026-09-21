from sahighar.db.models import Promoter
from sahighar.resolve.grouping import resolve_groups


def P(id, name, pan=None, address=None, partners=None):
    return Promoter(id=id, state="MH", rera_promoter_ref=f"P{id}", name=name, pan=pan,
                    registered_address=address, partners_or_directors=partners, source_document_id=1)


def types(group):
    return {(m.promoter_id, m.link_type) for m in group.members}


def test_same_pan_is_filing_confirmed_and_transitive():
    groups = resolve_groups([P(1, "A", pan="ABCDE1234F"), P(2, "B", pan="abcde1234f "), P(3, "C", pan="ZZZZZ9999Z")])
    assert types(groups[0]) == {(1, "filing_confirmed"), (2, "filing_confirmed")}
    assert types(groups[1]) == {(3, "filing_confirmed")}


def test_partner_overlap_plus_same_address_is_possible_only():
    groups = resolve_groups([
        P(1, "Shree Realty LLP", address="12 MG Road, Pune", partners=["Ramesh Shah"]),
        P(2, "Different Name Pvt Ltd", address="12 MG ROAD PUNE", partners=["ramesh  shah"]),
    ])
    assert types(groups[0]) == {(1, "filing_confirmed"), (2, "possible")}
    assert types(groups[1]) == {(2, "filing_confirmed"), (1, "possible")}
    assert groups[0].members[1].evidence["same_address"] is True


def test_partner_overlap_plus_similar_name_is_possible():
    groups = resolve_groups([
        P(1, "Shree Realty LLP", address="A", partners=["Ramesh Shah"]),
        P(2, "Shree Realty Phase 2 LLP", address="B", partners=["Ramesh Shah"]),
    ])
    assert (2, "possible") in types(groups[0])


def test_same_address_plus_similar_name_is_possible_without_any_partner_data():
    groups = resolve_groups([
        P(1, "Shree Realty LLP", address="12 MG Road, Pune"),
        P(2, "Shree Realty Phase 2 LLP", address="12 MG ROAD PUNE"),
        P(3, "Unrelated Builders", address="12 MG Road Pune"),
    ])
    assert (2, "possible") in types(groups[0])
    assert groups[0].members[1].evidence == {"shared_partners": [], "same_address": True, "name_similarity": 100}
    assert all(m.promoter_id != 3 for g in groups[:2] for m in g.members if m.link_type == "possible")


def test_single_weak_signal_creates_no_link():
    only_partner = resolve_groups([P(1, "Alpha", partners=["Ramesh Shah"]), P(2, "Beta", partners=["Ramesh Shah"])])
    assert all(len(g.members) == 1 for g in only_partner)
    only_address = resolve_groups([P(1, "Alpha", address="12 MG Road"), P(2, "Beta", address="12 MG Road")])
    assert all(len(g.members) == 1 for g in only_address)
    only_name = resolve_groups([P(1, "Shree Realty LLP"), P(2, "Shree Realty LLP")])
    assert all(len(g.members) == 1 for g in only_name)
