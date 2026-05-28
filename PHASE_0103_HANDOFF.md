# GRIT — PHASE 0.103 HANDOFF (fresh-session)

Read first, in full, and treat as the source of truth:

1. `MANIFESTO.md` — mission
2. `BOOTSTRAP.xml` — system contract + current state (version 0.103)
3. `EVENT_MATRIX.md` — the source encyclopedia (what to build, in what order)
4. `README.md` — operator quickstart

Do not restart architecture. Do not redesign the UI. Do not fabricate data,
events, or leads. Do not build social-sentiment scrapers (deferred — see C6).
Follow the stay-clean doctrine: sanctioned channel first, never IP-evasion.

---

## Verified state at 0.103 (do not rebuild)

- Tactical console (map + sortable spreadsheet + Source Health Matrix + CSV).
- Entity normalization (PERSON / LLC / TRUST / COMMERCIAL / HOA / GOVERNMENT).
- Weighted, transparent scoring + real geographic clustering.
- Event contract (`grit/events.py`); APN-joined per-parcel timelines.
- **LIVE Assessor enrichment** (`grit/assessor.py`) — current owner/value/sale.
- **EVENT_MATRIX.md** — full source landscape, grounded in verified-live endpoints.
- **Source registry rebuilt** (`grit/sources.py`) around the matrix: corrected
  Accela + Recorder search URLs, added SilverFlume (bulk/API) and court eServices.

## The single next task

**County permit ingestion (Accela, EVENT_MATRIX B1)** — the highest-value signal.

Capture-then-build, never blind parsing:
1. From a residential Las Vegas IP, run `python -m grit permits` to capture the
   real ACA Building search page (ViewState + field names).
2. Upload one captured sample. The deterministic permit-event extractor gets
   written *against that real output* — PERMIT events with puller, address/APN,
   valuation, issue date, trade tag.
3. No events are published until the parser is verified (no fabricated activity).

After permits flow end-to-end: Recorder distress (B3) → SilverFlume entities (A3)
→ NSCB sync (A4) → recency-weighted event scoring → entity graph. Full ordered
sequence is at the bottom of `EVENT_MATRIX.md`.

## Judgement test (gates every new feature)

Find money sooner? Organize it better? Reduce labor per dollar? Improve recency,
density, or monetization quality? If none — do not build it.
