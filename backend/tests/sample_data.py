# Two fixture documents shared by the service, API and demo-seed code.
# P1+P2 share a PAN (filing_confirmed); P3 shares partner + address with P1 (possible); P4 is unrelated.

DOC_1 = {
    "promoters": [
        {"ref": "P1", "name": "Shree Realty LLP", "pan": "AAAPA0001A", "registered_address": "12 MG Road, Pune",
         "partners_or_directors": ["Ramesh Shah"]},
        {"ref": "P2", "name": "Shree Homes LLP", "pan": "AAAPA0001A"},
    ],
    "projects": [
        {"reg_no": "MH-1", "promoter_ref": "P1", "name": "Shree Heights", "city": "Pune",
         "registration_end": "2022-01-01"},
        {"reg_no": "MH-2", "promoter_ref": "P2", "name": "Shree Gardens",
         "registration_end": "2022-01-01", "extended_end": "2023-01-01"},
    ],
    "complaints": [
        {"ref": "C1", "promoter_ref": "P1", "status": "Hearing Scheduled", "project_reg_no": "MH-1",
         "filed_year": 2024, "filed_month": 3},
        {"ref": "C2", "promoter_ref": "P2", "status": "Order Approved", "project_reg_no": "MH-2",
         "filed_year": 2023, "filed_month": 11, "order_url": "https://example.test/order/C2.pdf"},
    ],
}
DOC_2 = {
    "promoters": [
        {"ref": "P3", "name": "Shree Realty Phase 2 LLP", "pan": "BBBPB0002B", "registered_address": "12 MG ROAD PUNE",
         "partners_or_directors": ["ramesh shah"]},
        {"ref": "P4", "name": "Zenith Constructions", "pan": "CCCPC0003C"},
    ],
    "projects": [
        {"reg_no": "MH-3", "promoter_ref": "P3", "name": "Shree Towers", "registration_end": "2027-01-01"},
        {"reg_no": "MH-4", "promoter_ref": "P4", "name": "Zenith One", "registration_end": "2027-06-01"},
    ],
}
