# GRIT — Alpha 0.109 → 0.110

This round is the **Free Data Maximization Audit** (full report:
`GRIT_0110_FREE_DATA_AUDIT.md`) plus the highest-value verified build it
surfaced. No paid sources, no doc rewrites, no placeholders — only a source I
could see returning live data.

## Headline: City of Henderson is now a live permit jurisdiction

The audit's biggest find: **Henderson publishes its full permit feed on a clean
Socrata API** (`opendata.cityofhenderson.com`, dataset `fpc9-568j`) — and it's
*richer than CLV*. Each record carries permit type/status, apply + issue dates,
**parcel number (APN)**, full property address, **coordinates**, owner + mailing,
valuation, square footage, and the contractor's name **with their state license
number**.

New `grit/henderson.py` pulls it via the SODA API and normalizes to GRIT's existing
permit shape, so it reuses the proven `permits_to_cards` / `merge` / `to_events` /
trade-tagging path (I parameterized `permits_to_cards` by source). On your next
harvest, Henderson permits join to parcels by APN, create new permit leads, map by
coordinate, feed the contractor leaderboard **with license numbers**, and carry
valuation + sqft. Fail-safe: a portal hiccup returns zero rows and never aborts the
harvest. Verified against live data and offline via selftest.

This directly serves your emphasis — more permit jurisdictions, deeper contractor
signal — and it's the model for what's next: clean municipal APIs, not scraping.

## What the audit confirmed (the short version)

- **Free permit ceiling ≈ 2 clean-API jurisdictions** (Las Vegas + Henderson now
  captured). North Las Vegas + County are Accela with **no free API** (scrape-only).
- **Code Enforcement is live and working** — 92 new distress leads last harvest.
- **Business Licenses returned ~0** because that dataset keys on **address, not
  APN** — the connector joins on APN. Fixing that (address join) + adding Henderson
  licenses is the top 0.111 item.
- **Contractor licensing (NSCB)** is public but **API-less** (scrape); meanwhile
  Henderson permits now hand us license numbers for free.
- **The three structural walls of the free tier**: parcel-level value/sqft/beds
  (paid Assessor extract), Recorder distress (NOD/trustee — no free bulk), and court
  filings (evictions/probate — portal-limited). Everything else is reachable free.
- At least **6–8 more verified free feeds** remain to wire (crime, service requests,
  zoning/land-development, Henderson/CLV licenses) before the free universe is spent.

## 0.111 (next): the clean-API tier continues

1. Fix the **business-license address-join** + add **Henderson business licenses** →
   Business Licenses goes genuinely green in two cities.
2. Wire **LVMPD crime** as an area signal → Crime goes green.
3. Stretch: **NSCB contractor enrichment** (license status/class/discipline on the
   331 known contractors).

## Verification

`selftest` exit 0 (new asserts cover the Henderson field mapping → permit dict →
cards → events) · `rebuild` exit 0 · console JS syntax-checked, zero browser-storage
APIs · workflow staging fix re-applied. Docs (MANIFESTO/BOOTSTRAP/README) untouched,
per the directive.

## Your move

Run **Actions → GRIT harvest** and Henderson permits populate — new leads across
Henderson, contractor license numbers in the leaderboard, valuation/sqft on permits.
The audit lays out exactly what's free and what isn't; the free universe still has
real room, and the one thing it can't give — parcel-level value depth — remains the
paid Assessor extract whenever you decide it's worth it.
