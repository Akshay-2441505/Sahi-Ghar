# Data Sources

Where every piece of data in this product would actually come from.

## Sources identified so far

| Source | Provides | Coverage | Access | Notes |
| --- | --- | --- | --- | --- |
| [MahaRERA project search](https://maharera.maharashtra.gov.in/projects-search-result) | Registered project details, promoter, dates, carpet area, approvals | Maharashtra | Public web search, scrapeable | Primary MVP source |
| [MahaRERA promoter search](https://maharera.maharashtra.gov.in/promoters-search-result) | Promoter/builder registration details | Maharashtra | Public web search |  |
| [MahaRERA promoter-wise complaint list](https://maharera.maharashtra.gov.in/promoter-complaint-report) | Complaints per promoter | Maharashtra | Public web search | Core of the trust score |
| RERA Quarterly Progress Reports (QPR) | Floor-wise completion %, photos, audited financial progress, inventory status | Maharashtra, Karnataka, Telangana (format varies by state) | Published per-project on state RERA sites | Powers the progress-vs-promise tracker |
| MCA (Ministry of Corporate Affairs) company/director data | Directors and registered addresses per company | Pan-India | Public search free; detailed filings carry a small fee | Needed for entity resolution across SPVs |
| [rera-india (GitHub)](https://github.com/mukuldas77-web/rera-india) | An existing open-source attempt at RERA data aggregation | Unknown/partial | Open source | Worth reviewing before building, to avoid duplicate work |
| State "ready reckoner" / circle rate data | Government minimum property valuation per locality | State-published, varies | Public, state revenue department sites | Rough price proxy only — not real market price |
| [Karnataka RERA (K-RERA) project search](https://rera.karnataka.gov.in/) | Registration details, promoter PAN, sanctioned plan, Form-3 CA certificate | Karnataka | Public web search, scrapeable | Comparable richness to MahaRERA |
| [Karnataka RERA promoter complaint report](https://rera.karnataka.gov.in/promoterComplaintReport) | Complaints per promoter, pending/disposed status | Karnataka | Public web search | Direct analogue to MahaRERA's complaint list |
| Karnataka RERA QPR | Quarterly progress reports, with 90-day filing compliance tracking | Karnataka | Published per-project | Powers the progress tracker for Karnataka too |
| [Telangana RERA (TG-RERA) project search](https://rera.telangana.gov.in/) | Project details, approvals, promoter identity and compliance record | Telangana | Public web search, scrapeable | Confirmed comparable to Maharashtra/Karnataka |
| Telangana RERA complaints & litigation history | Formal complaints, litigation history, order/judgment records with status | Telangana | Public web search | Richer than most states — includes order/judgment records, not just a count |
| Telangana RERA QPR | Quarterly progress updates, periodic compliance reports | Telangana | Published per-project | Powers the progress tracker for Telangana too |

## Known gaps

- **No reliable free source for actual sale price.** RERA filings mandate carpet-area disclosure but not price, so budget-based matching in v1 has to be a soft, self-reported filter rather than a verified one — see the PRD's "Out of scope" section.
- **Tamil Nadu and Gujarat RERA portals** have solid project search and registration-status tracking, but public guides don't confirm promoter-level complaint records or QPR visibility the way Maharashtra, Karnataka, and Telangana do — verify directly before adding either, don't assume parity.

## Other tools already attempting this

- [Cubeyards](https://cubeyards.com/rera) pitches free, consumer-facing verification across all 32 states/UTs — but its live database currently shows zero projects and zero realtors, so the vision isn't delivered yet.
- [Revnew](https://revnew.in/rera) redirects straight to Cubeyards — same product, not a separate competitor.
- [Realatic](https://realatic.com/tools/rera-lookup/) is a real-estate CRM company for builders; its RERA lookup is a minor lead-gen utility on their site, not a real consumer-facing competitor.

None of these show complaint-based trust scores, progress-vs-promise tracking, or entity resolution across SPVs — the actual differentiators still stand.
