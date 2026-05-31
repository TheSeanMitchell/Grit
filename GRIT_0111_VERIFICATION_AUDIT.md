# GRIT 0.111 — End-to-End Verification Audit

*Verified against the uploaded live repo: version 0.111, warehouse 2026-05-31T02:21:02Z,
8,209 leads. Every figure below is read directly from `docs/data/*.json`, the harvest
metadata, and `docs/index.html`. No estimates. No code changed.*

---

## A. Current Reality Report

The live system is real and substantially more capable than a month ago. The last
harvest ran the 0.111 code end-to-end. What is genuinely working:

- **8,209 leads**, 7,985 mapped, 13 jurisdictions. The map now shows a real second
  cluster (Henderson/Boulder City), not just Las Vegas.
- **Henderson is fully live** — the single biggest advance. 3,992 permits ingested,
  3,937 with APN, **3,208 new leads**, and crucially 2,534 with a contractor and
  **2,028 with a state license number**.
- **Permit-signal classification works** — 1,796 cards carry classified signals,
  surfaced both in the Audit matrix and on lead cards.
- **Code enforcement works** — 1,000 records → **92 new distress leads**.
- **Contractor contactability is real** — 2,500 cards carry license numbers, 1,707
  carry phone numbers (both from Henderson permits).

What is **claimed but not actually working** (the honest core of this audit):

- **Crime: 0 records.** Wired but broken — the item id never resolved.
- **Business-license attach: 3 of 864.** The connector pulls and warehouses them,
  but they essentially do not attach to leads.
- **Henderson business licenses: 0.** Same item-id bug as crime.
- **Per-field confidence provenance**: built in 0.107, then dropped from the shipped
  `cards.json` in the 25 MB file-size fix — so the drawer's per-field provenance is
  now empty (the summary still shows).
- **Contractor license numbers are captured but not shown** in the lead drawer.

---

## B. Installed vs Claimed Matrix

| # | Claim | Classification | Evidence |
|---|-------|----------------|----------|
| 1 | Permit-signal classifier (12 families) | **INSTALLED_AND_VISIBLE** | `cards.permit_signals` populated on 1,796 cards. Counts: public_works 384, fire_life_safety 307, commercial_ti 128, demolition 10, cert_of_occupancy 2, new_construction 687, grading_site 169, telecom 37, roofing 63, pool_spa 165, solar 235, distress(code-enf) 93. Rendered in Audit matrix + drawer "Signals on this property" chips + `signal:` tag facets. |
| 2 | Audit page (matrix, counts, blockers, source health) | **INSTALLED_AND_VISIBLE** | `coverage.json.audit.signal_matrix` = 33 rows, **17 IMPLEMENTED / 4 PARTIAL / 12 MISSING**, every row has a `blocker` field; `index.html` renders the matrix, a blocker-color map, denominators, coverage reality, confidence, source inventory. |
| 2b | Per-signal coverage **%** | **NOT_INSTALLED** | Matrix shows raw counts, not per-signal %. Only breadth/depth % exist (denominators). |
| 3 | Lead drawer: WHO/WHAT/WHEN/WHERE/WHY | **INSTALLED_AND_VISIBLE** | drawer renders owner/entity (WHO), Event timeline (WHAT/WHEN), address+dims (WHERE), why_this_matters (WHY). |
| 3a | Drawer: Signals + Contact channels sections | **INSTALLED_AND_VISIBLE** | both string-matched present in `index.html`; data present (1,796 signal cards; 2,747 mailings; 1,707 phones). |
| 3b | Drawer: Confidence section | **PARTIALLY_INSTALLED** | section + summary render, but per-field provenance list is **empty** — `field_confidence` was dropped from `cards.json` in the file-size fix. |
| 3c | Drawer: Timeline section | **INSTALLED_AND_VISIBLE** | "Event timeline" present; events trimmed to {date,kind,description}. |
| 3d | Drawer: Nearby activity section | **NOT_INSTALLED** | zero matches in `index.html`; never built. |
| 3e | Drawer: Connected entities section | **NOT_INSTALLED** | zero matches in `index.html`; never built. |
| 3f | Drawer: contractor license shown | **INSTALLED_NOT_VISIBLE** | `contractor_license` on 2,500 cards but absent from the drawer's contact block (only name + phone shown). |
| 4 | Henderson permits | **INSTALLED_AND_VISIBLE** | harvest meta: 3,992 ingested, 3,208 leads added; 3,208 cards `source=henderson_permit`; visible as the SE map cluster. |
| 5 | Business-license address-join "fixed" | **PARTIALLY_INSTALLED** | code has `_norm_addr` + address index, but only **3 of 864** attach (`business_license_card_hits: 3`). 413 warehoused as events; attach is functionally broken. |
| 6 | LVMPD crime activated | **NOT_INSTALLED** | harvest meta: `crime.status = "unresolved"`, layer null, **0 records**. |
| 7 | Henderson business licenses | **NOT_INSTALLED** | harvest meta: `henderson_layer: null`. |
| 8 | File-size guard (`checksize`) + slim cards.json | **INSTALLED_AND_VISIBLE** | `cards.json` 17 MB (was 40); command present. |

**Root cause for #6 and #7 (identical bug):** the item ids carry a `_0` layer
suffix — `LVMPD_CRIME_ITEM = "6a371d1a491a4a0794578b031859c768_0"` and Henderson
business `"b86e999491454c4290af161192ad0eba_0"`. `resolve_layer()` sends the id to
the ArcGIS item-metadata API (`/sharing/rest/content/items/{id}`), which expects a
**bare** item id. With `_0` appended the lookup returns nothing → `url` empty →
returns `None` → "unresolved." The two CLV items (no `_0`) resolved correctly.

---

## C. Contactability Audit

Per category — available (on cards) / surfaced (shown in drawer) / hidden / not harvested:

| Channel | Available | Surfaced | Hidden | Not harvested |
|---|---|---|---|---|
| Owner name | 6,098 | yes | — | 2,111 (no owner on those parcels) |
| Owner mailing address | 2,747 | yes | — | 5,462 |
| Contractor name | 2,887 | yes | — | 5,322 |
| **Contractor license #** | **2,500** | **NO** | 2,500 | 5,709 |
| **Contractor phone** | **1,707** | yes | — | 6,502 |
| Business phone | **0** | — | — | all (connector doesn't extract phone) |
| Business email | **0** | — | — | all (connector doesn't extract email) |
| Business activity (proxy) | 3 | yes (for 3) | — | ~861 pulled-but-unattached |

**Real contactability today = owner mailing (2,747) + contractor phone (1,707) +
contractor license (2,500, currently hidden).** Business contact is effectively zero.

**Verified free sources that could raise contactability (no paid skip-tracing):**
- **NSCB** — public license search (NRS 239) returns contractor business address,
  phone, and license status; no API (scrape). Highest contactability lift.
- **Business licenses (CLV + Henderson)** — already pulled (864) but the records'
  own owner/contact fields aren't mapped, and they don't attach. Henderson's feed is
  not even resolving.
- **Permits** — already the best source (phone + license from Henderson); CLV permits
  carry a contractor name but no phone in the current mapping.
- **NV SOS (SilverFlume)** — registered-agent name/address per entity (search, no bulk).

---

## D. Signal Coverage Audit (current reality only)

| Family | Status | Why |
|---|---|---|
| Permits | **GREEN** | CLV + Henderson live; 4,992 PERMIT events. |
| Ownership | **GREEN** | 6,098 owner names (free parcel layer). |
| Contractors | **GREEN** | 921 ranked; Henderson adds 2,500 licenses + 1,707 phones. |
| Code Enforcement | **GREEN** | 93 VIOLATION events, 92 distress leads. |
| Solar (+ Public Works, Fire/Life-Safety, New Construction, Grading, Commercial TI, Demolition, Telecom, Roofing, Pool, CofO) | **GREEN** | classified from real permits; counts in §B. |
| Capital Flow (owner origin) | **GREEN** | 2,093 origin markets, out-of-state capital tracked. |
| Distress (aggregate) | **GREEN (thin)** | only code-enforcement feeds it; foreclosure/NOD blocked. |
| Business Licenses | **PARTIAL → effectively BROKEN** | 864 pulled, **3 attach**; shows green in matrix only because the rule is "≥1." |
| Crime | **BROKEN (wired, 0 records)** | item-id `_0` suffix breaks resolve_layer. |
| Planning / Zoning / Government Projects | **BLOCKED (not built)** | free candidates (CLV Land Development, USASpending) — not implemented. |
| Foreclosures / Trustee Sales / Tax Liens / Mechanics Liens | **BLOCKED** | Clark County Recorder — no free bulk API. |
| Probate / Evictions | **BLOCKED** | Eighth Judicial District — portal only, no bulk. |
| Bankruptcy | **BLOCKED** | federal PACER — paid. |
| Utilities | **BLOCKED** | not public. |

**Matrix honesty note:** the "17 green" headline includes Business Licenses (real
attach = 3) and Certificate of Occupancy (2). The other ~14 greens are solid
(hundreds of records each). The "≥1 record = IMPLEMENTED" rule overstates two signals.

---

## E. Top 10 Highest-ROI Next Actions (recommendations, not a plan)

Ranked by intelligence/contactability gain per engineering hour:

1. **Strip the `_0` suffix from the crime + Henderson-business item ids** (or strip it
   in `resolve_layer`). One-line class of fix; unblocks **two** dead sources at once.
2. **Surface contractor license # in the drawer** — 2,500 records already captured,
   currently invisible. Pure UI, immediate contactability value.
3. **Fix business-license attach** — join by APN where present (CLV business data may
   carry a parcel id) instead of fuzzy address; or accept commercial leads. Today 861
   of 864 are wasted.
4. **Map contractor phone from CLV permits** (Henderson already gives it) — could lift
   phone coverage well beyond the current 1,707.
5. **Tighten the matrix status rule** — require a minimum count (or distinguish
   "captured" vs "attached") so Business Licenses doesn't read green at 3/864.
6. **Wire NSCB contractor enrichment** (free, scrape) — license status + business
   phone/address on the 921 contractors; the biggest verified contactability lift.
7. **Restore a compact per-field confidence** to the drawer (or accept summary-only)
   — the 0.107 provenance feature is currently dark after the file-size cut.
8. **Add per-signal coverage %** to the Audit matrix — the directive's audit spec
   asks for it; today only breadth/depth % exist.
9. **Geocode the 224 unmapped permit leads** — small, makes the map complete.
10. **Re-pull Henderson business licenses via Socrata** (`n8gp-u2pj`) instead of the
    failing ArcGIS item — Henderson already proved its Socrata feed works for permits.

**Drift check:** Henderson + permit-signal classification + code-enforcement leads +
contractor phones/licenses clearly advanced the mission (more leads, more
contactability). Effort that did **not** pay off: the crime wiring (broken), the
business-license connector (3 attaches), and the per-field confidence layer (built,
then hidden by the size fix). Next effort should fix the cheap broken pieces (#1–#3)
before any new source.
