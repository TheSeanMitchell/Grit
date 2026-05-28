# GRIT — PHASE 0.102 CONTINUATION (fresh-session handoff)

Paste this into a new conversation. Read these three files first, in full, and
treat **BOOTSTRAP.xml** as the operational source of truth:

- `MANIFESTO.md`
- `BOOTSTRAP.xml`
- `README.md`

Do not restart architecture discussions. Do not redesign the UI. Do not
fabricate data, enrichment, activity, or leads. Do not generate synthetic demo
records. Do not drift into agent-framework theorizing before acquisition flow
exists.

---

## What is already DONE (do not rebuild)

GRIT is an event-driven acquisition intelligence system for Las Vegas / Clark
County. Shipped and verified through Alpha 0.102:

- Tactical console: side-by-side map + sortable spreadsheet, two-way
  reverse-click linking, CSV export, Source Health Matrix.
- Entity normalization: PERSON / LLC / TRUST / COMMERCIAL / HOA / GOVERNMENT / UNKNOWN.
- Weighted opportunity scoring (entity + contactability + absentee + recent sale
  + value + cluster + event-timeline), HOA/GOV scored 0 and hidden by default.
- Geographic cluster density (real radius calc).
- Event architecture: `grit/events.py` Event contract, `events.json`, APN join,
  per-card timelines that feed scoring.
- **LIVE Assessor enrichment (the 0.102 headline).** `grit/assessor.py` GETs
  `parceldetail.aspx?hdnparcel=<APN>&logo=1` and deterministically parses the
  CURRENT record: owner, mailing, situs address, current assessed/taxable value,
  last sale (price/date/type), land use, year built, beds, baths, roof, pool,
  lot size. The harvest enriches the top `CARDS_ENRICH_MAX` leads each run,
  overwrites stale 2018 fields with today's data, and emits DEED timeline events.
  Verified end-to-end against the real page schema. **The data-freshness problem
  is solved** for owner/value/sale.

## Known truths

- Free clean GIS feeds cap at parcel geometry + APN (current) and 2018
  owner/address (~25% addressed). The 2018 layer is the harvest base; Assessor
  enrichment makes the top leads current.
- The Assessor `parceldetail.aspx` GET worked from a cloud fetch, so enrichment
  may run on the GitHub Action. If the Action's datacenter IP gets blocked, the
  parcel harvest still works and `harvest_meta.enrichment` + health report the
  errors — fall back to running `python -m grit harvest` locally (residential IP).
- Permits/deeds still live behind ViewState portals (Accela ACA, Recorder).
  Permit events are the highest-value remaining signal.

## REMAINING 0.102 PRIORITIES (build next, in order)

1. **Real permit ingestion (Accela ACA).** Highest value. Capture real HTML
   first (`grit/permits.py` scaffold + `python -m grit permits`, run from a
   residential Vegas IP), then write a deterministic parser → normalized PERMIT
   events → joined to parcels → surfaced on map + spreadsheet + timeline + score.
   No blind parsing. Save raw responses for audit.
2. **Property timelines.** Already structured (card `timeline`); evolve into a
   full chronological object: permits, deeds, enrichments, contractor changes,
   notes, operator actions. Timestamped, typed, source-attributed, auditable.
3. **Spreadsheet intelligence.** Multi-column filters, recency filtering,
   event-type filtering, score-breakdown inspection, export subsets, quick-note
   tagging, and operator states (worked / unworked / contacted / follow-up).
   Lightweight intelligence workstation, speed over aesthetics.
4. **Event-driven scoring.** Push further so recent events dominate static owner
   metadata — a roofing permit from 3 days ago should massively outweigh a static
   high-value parcel. (0.102 already adds event-timeline bonuses; deepen them.)
5. **Entity-graph foundations.** Lightweight, inspectable adjacency: same
   contractor repeated, same LLC across parcels, same address across entities.
   Not a graph DB.
6. **Operator efficiency.** Every feature must reduce human labor per dollar.

## First tasks for the new session

1. Confirm the live Assessor enrichment is producing current data in the user's
   latest run (check `cards.json` for `vintage: "current"` and `events.json` for
   DEED events). Tune `CARDS_ENRICH_MAX` / `ENRICH_DELAY` if needed.
2. Begin permit ingestion: have the user run `python -m grit permits` locally and
   upload a captured `docs/data/permit_samples/` file; write the deterministic
   permit-event parser against it.
3. Build operator-state tracking in the spreadsheet.

## Judgment test (every change)

Must answer YES to at least one: finds money sooner? organizes money better?
reduces labor per dollar? improves recency / monetizability / repeatability /
automation / durability / cost? If no — do not build it.
