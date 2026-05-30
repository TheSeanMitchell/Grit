# GRIT — Alpha 0.110 · Free Data Maximization Audit

*Budget assumption: $0. No AOEXTRACT / AORES / ATTOM / Regrid / paid vendors.*
*Every source below was verified via live research; nothing is speculative.*

---

## 1. Executive Summary

GRIT is a working, single-operator acquisition-intelligence warehouse for Clark
County: ~5,000 leads, **99.9% owner coverage** on held parcels, transparent
scoring, an append-only history, and a confidence-classed audit. As of this
release it pulls four live free feeds — the Clark County parcel layer, City of
Las Vegas permits, CLV **Code Enforcement** (now producing real distress leads —
92 new properties last harvest), and, new in 0.110, **City of Henderson
permits**.

The system is healthy and the architecture (EVENT→ENTITY→MONEY) still holds. The
honest constraint is unchanged and now precisely understood: **breadth** (how many
parcels) is free and self-capped; **depth** (value/sqft/beds) is paid-gated at the
Assessor and therefore off the table this phase. The work that remains is almost
entirely **signal breadth** — more jurisdictions, more event types — which the
free-data universe still has meaningful room to deliver.

The single highest-leverage finding this audit: **Henderson publishes its full
permit feed on a clean Socrata API, carrying contractor *license numbers* and
permit *valuation/sqft*** — richer than the CLV feed. It is now wired (0.110).
That is the model for the remaining work: a small number of clean municipal APIs,
not a long tail of scraping.

---

## 2. Free Data Ceiling Assessment

**What the maximum free system looks like.** With $0, GRIT can realistically reach:

- **Breadth:** address + owner + mailing + land-use for effectively the entire
  ~900k-parcel valley (the free parcel layer carries it). The only real limit is
  rendering — a static site tops out around 10–15k pins before it needs vector
  tiles. So GRIT can *measure* coverage against the whole county while *mapping*
  the active, signal-bearing subset.
- **Permits:** comprehensive for **Las Vegas** and **Henderson** (both clean free
  APIs). North Las Vegas and unincorporated County run on **Accela with no clean
  free API** — reachable only by scraping. Boulder City / Mesquite are tiny and
  portal-poor. So free permit coverage realistically caps at **~2 of the metro's
  ~5 issuing authorities by clean API**, plus optional NLV/County scraping.
- **Distress (the highest-value gap):** code enforcement is **free and live**
  (CLV). Foreclosure / NOD / trustee / lis pendens live at the **Recorder**, which
  has a search interface but **no free bulk API** — realistically unobtainable for
  free at scale. Evictions/probate live in the **Eighth Judicial District** court
  system — limited free access, case-by-case.
- **Business / entity:** CLV + Henderson business licenses are **free**; NV SOS
  (SilverFlume) entity data is **searchable but not cleanly bulk-free**.
- **Contractors:** names come free from permits; Henderson adds **license numbers**
  for free. NSCB license status/discipline is **public but API-less** (scrape).
- **Crime:** **free** (LVMPD ArcGIS Hub) — wireable as an area signal.

**Bottom line:** the free universe gets GRIT to a *strong activity-and-distress
intelligence system across the two API-friendly cities, plus county-wide ownership
breadth* — but **not** parcel-level financial depth, and **not** clean
foreclosure/eviction feeds. Those three (depth, recorder distress, court filings)
are the structural walls of the free tier. Everything else is reachable.

---

## 3. Remaining Free Source Inventory (verified, prioritized)

Ranked by intelligence-gain-per-engineering-hour. All confirmed to exist.

| # | Source | Access | What it adds | Difficulty | Impact |
|---|--------|--------|-------------|-----------|--------|
| 1 | **Henderson DSC Permits** (Socrata `fpc9-568j`) | clean JSON API | 2nd permit jurisdiction; contractor + **license #**; value+sqft | low | **shipped 0.110** |
| 2 | **CLV Business Licenses** (ArcGIS `f6b923ee…`) | clean API | commercial/entity signal | low (needs **address join** — they lack APN) | high |
| 3 | **Henderson Business Licenses** (Socrata `n8gp-u2pj` / ArcGIS) | clean API | commercial/entity in Henderson | low | medium |
| 4 | **LVMPD Crime** (`opendata-lvmpd.hub.arcgis.com`) | clean API | area-risk signal (set item id) | low | medium |
| 5 | **NSCB contractor license** (`nvcontractorsboard.com`) | search portal, **no API** | license status/class/discipline on the 331 contractors | medium (scrape) | high |
| 6 | **CLV Service Requests** (`opendataportal-lasvegas`) | clean API | 311 / property-condition signal | low | medium |
| 7 | **CLV Zoning / Land Development** (ArcGIS ZONING FeatureServer) | clean API | early development-pipeline signal | low–med | medium |
| 8 | **Clark County GIS Hub** (`clarkcountygis-ccgismo`) | clean API | county zoning/land-use/facilities (no permits) | low | low–med |
| 9 | **NLV / County permits** (Accela `aca-prod…/clarkco`) | **no API** | the remaining permit jurisdictions | high (scrape) | high |
| 10 | **Census Building Permits Survey** (federal) | clean API/CSV | the only real permit *denominator* (new-residential/yr) | low | low (context) |
| 11 | **Clark County Recorder** (NOD/trustee/lis pendens) | search only, **no bulk** | the top distress signal | very high | high (blocked) |
| 12 | **Eighth Judicial District courts** (evictions/probate) | limited portal | distress / motivated-seller | very high | medium (blocked) |
| 13 | **NV SOS SilverFlume** (entities/agents) | search, bulk unverified | LLC → officer → portfolio graph | high | medium |

Verified-but-not-recommended: ATTOM/Regrid (paid), Assessor AOEXTRACT/AORES (paid).

---

## 4. Coverage by Category (captured / partial / not / free-obtainable / paid-only)

- **Permits** — *partial→good.* CLV + Henderson **captured**; NLV/County **not**
  (Accela, free only via scrape).
- **Code enforcement** — **captured** (CLV, live; distress leads). Henderson/NLV
  code: free-obtainable (probe needed).
- **Crime** — **not captured**, **free-obtainable** (LVMPD, wireable now).
- **Business activity** — **partial** (CLV licenses wired but not joining; Henderson
  free-obtainable). Both free.
- **Ownership** — **captured** (99.9% on held parcels, free layer).
- **Land use** — **captured** (free layer).
- **Recorder events (deeds/NOD/transfers)** — **not captured**; deeds partially via
  Assessor sale history; NOD/trustee **paid-or-blocked** (no free bulk).
- **Court data (evictions/probate/foreclosure filings)** — **not captured**,
  realistically **unobtainable free** at scale (court portals, no bulk).
- **Tax data (value)** — **not captured**, **paid-only** (Assessor extract).
- **Tax liens** — **not captured**; Treasurer/Recorder, no free bulk.
- **Licensing (business + contractor)** — **partial/free** (city licenses free;
  NSCB public but scrape-only).
- **Foreclosure indicators** — **not captured**, **paid-or-blocked**.
- **Eviction indicators** — **not captured**, court-portal-limited.
- **Vacancy indicators** — **not captured**; no clean free source (USPS vacancy is
  restricted; utility shutoffs not public). Code-enforcement "vacant/boarded" cases
  are the closest **free proxy** — already captured.
- **Utility indicators** — **not captured**; not public.
- **Government datasets** — **partial/free** (zoning, land development, facilities,
  capital projects on the city/county hubs).
- **Economic datasets** — **free** (Census BPS, ACS) — context/denominators only.

---

## 5. Recommended 0.110 Build Plan — *(shipped in this release)*

**Wire City of Henderson permits (Socrata DSC feed).** New `grit/henderson.py`
pulls `fpc9-568j` via the SODA API, normalizes to the existing permit shape, and
reuses `permits_to_cards` / `merge_permit_cards` / `to_events` / trade-tagging.
`permits_to_cards` was parameterized by `source_key`. Henderson permits carry APN
(join to parcels), coordinates (map directly), owner + mailing, **contractor +
state license number**, valuation, and square footage. Source inventory + signal
matrix updated; selftest extended; fail-safe (a portal error returns zero rows and
never aborts the harvest). This is the second live permit jurisdiction and deepens
the contractor signal — verified against live data, not a placeholder.

---

## 6. Recommended 0.111 Build Plan — *(next)*

Two changes, both clean APIs, both serving signal breadth:

1. **Fix the business-license join + add Henderson licenses.** CLV business
   licenses returned ~0 last harvest because they key on **address, not APN** —
   the connector currently joins on APN only. Add an **address-normalized join**
   (the `events._norm_addr` helper already exists) so licenses attach to leads, and
   add **Henderson Business Licenses** (Socrata `n8gp-u2pj`). Turns the Business
   Licenses signal genuinely green in two jurisdictions.
2. **Wire LVMPD crime as an area signal.** Resolve the LVMPD ArcGIS item, pull
   incidents, aggregate to a per-area (zip/grid) recent-crime density, and attach a
   neighborhood-context signal to leads. Turns Crime green. (Set `LVMPD_CRIME_ITEM`.)

Stretch: **NSCB contractor enrichment** — for the ~331 known contractors, query the
NSCB public search by name to attach license status / classification / discipline.
Scrape-based (no API), low volume, high signal — gives every contractor a
credibility profile and lets license numbers from Henderson permits resolve to a
status.

---

## 7. Long-Term Roadmap (free-first → eventual full-market)

**Phase A — exhaust the clean free APIs (0.110–0.112).** Henderson permits
(done) → business-license join + Henderson licenses → LVMPD crime → CLV service
requests + zoning/land-development. After this, every SoNV source with a clean
free API is captured. This is the bulk of remaining free value for the least
effort.

**Phase B — the scrape tier (0.113+), only if warranted.** NLV + County permits
via Accela, and NSCB contractor enrichment. Higher maintenance burden; pursue when
clean-API value is exhausted and the lead impact justifies the upkeep.

**Phase C — the structural walls (require money or sustained legal/engineering
effort).** Parcel-level **depth** (Assessor AOEXTRACT/AORES), **Recorder distress**
(NOD/trustee/lis pendens), and **court filings** (evictions/probate). These are the
three things free data cannot give cleanly. When the operator is ready to spend,
**the Assessor extract is the highest-ROI first purchase** — it turns the depth
fields (value/sqft/beds) from ~3% to ~100% across the whole warehouse in one move,
and it is the cheapest of the paid options.

**Architecture note for county-wide scale.** The current static-JSON + per-pin map
is excellent up to ~10–15k leads. Before pushing breadth county-wide, plan for
**slim per-card records** (strip raw/timeline bloat from `cards.json`) and
**clustered or vector-tile rendering**. The append-only warehouse and the
EVENT→ENTITY→MONEY model scale fine; only the map payload needs rework. No
duplication or storage concerns today; the warehouse de-dupes by APN and the
ledger is append-only by design.

---

### Maximizing intelligence-gain-per-hour

The ranking is deliberate: clean municipal APIs first (Henderson permits, the
license join, crime), scraping only when the clean tier is spent, and paid
acquisition reserved for the three things free data structurally cannot provide.
The free universe is not yet exhausted — there are at least 6–8 more verified free
feeds to wire — and 0.110 takes the largest single bite (a whole second permit
city with deeper contractor data).
