# GRIT — Alpha 0.104 → 0.105

**Headline: the map opens up to the whole valley, and owner-origin becomes a first-class intelligence layer — Capital Flow.**

Nothing here invents data. Empty states stay empty; every score still ships its `signals[]`; the only coordinates that ever plot are real property locations.

---

## 1. Why the map only showed part of the city (root cause + fix)

The `.104` map plotted 500 parcels and **none** of the ~900 permit leads. The permit feed carries an APN but no geometry, so every permit card (and all 2,000 permit events) had `lat/lng = null`, and the renderer only plots points that have coordinates. The freshest, highest-value signal was invisible.

Fix: a **geocoding spine** (`grit/geocode.py`) that resolves permit APNs to parcel centroids via the Assessor parcel layer, then stamps coordinates onto permit cards and events. It runs inside the live harvest (it needs to query the county layer). The sandbox here cannot reach county endpoints, so permits are coordless **until you run one harvest** — see §7.

The console no longer hides this: a banner reports exactly how many permit leads are queued for geocoding.

## 2. The jurisdiction bug — fixed **without discarding owner geography**

The City of Las Vegas permit feed's `CITY` field is the **owner's mailing city**, and `.104` mislabeled it as the property's jurisdiction — producing out-of-state "jurisdictions" (Chicago, Indianapolis, LA). That was wrong and is fixed.

Crucially, the fix **does not delete the mailing geography**. Per your correction, GRIT now keeps **four separate location dimensions** and never collapses them:

| Dimension | Field(s) | Used for |
|---|---|---|
| **Property location** | `property_city`, `situs_city` | map pins, clustering, density |
| **Permit jurisdiction** | `permit_jurisdiction` | issuing authority, source completeness |
| **Owner mailing** | `owner_city`, `owner_state`, `owner_zip`, `owner_mailing` | absentee / investor detection |
| **Capital origin** | `owner_origin_market` | investor migration, capital flow |

A Las Vegas parcel owned from Chicago **plots in Las Vegas** — Chicago lives in the owner profile, Capital Flow, and exports, never as a coordinate. (Verified on a NY-owned LV parcel: property pin = Las Vegas, origin market = New York, NY.)

## 3. New intelligence category: **Capital Flow** (`grit/capital.py`)

Parses every owner mailing address into structured origin fields and rolls them up:

- **Top Owner Origin Markets** — properties, permits, valuation, distinct owners, and the Southern Nevada metros each market lands in.
- **Imported Capital** — the out-of-state subset (the investor-migration signal) with origin → metro flows.
- **Origin States** — ranked, local (NV) vs imported.

From the current warehouse (offline rebuild over existing cards): **903/1,412 leads** carry a parsed origin (64%), **76 markets**, **25 states**, **817 local / 86 imported (9.5%)**, **$7.7M imported value tracked**. Notable: New York places only 2 properties but **$2.8M** in value; LA, Chicago, and Scottsdale each place 4.

## 4. Ownership intelligence in the health matrix

New **Ownership** and **Capital Flow** rows in the category matrix, with visible coverage: mailing **64%**, absentee **42.4%**, LLC **24.2%**, trust **18.1%**, out-of-state owners **6.1%**.

## 5. Filterable owner-origin tags

New `origin:` tag namespace — `origin:local-nv`, `origin:out-of-state`, and per-state (`origin:california`, `origin:illinois`, …). Wired into the console's tag facets so you can isolate, e.g., every out-of-state-owned active-permit lead.

## 6. Rebuilt console (`docs/index.html`, v0.105)

Same aesthetic (IBM Plex Mono / Saira Condensed, dark CARTO map), now a tabbed mission console:

- **KPI strip** — leads, permit events, mapped, imported capital, contractors, jurisdictions (click to jump).
- **Map** — opens to the full metro; **out-of-state-owned parcels ringed in orange** (capital visible *at the property*, never as a mailing pin); tag-facet filter grouped by namespace; honest geocode banner.
- **Playback** — timeline scrubber + play/pause + day/week/month/year granularity; cumulative reveal with a trailing-window highlight and a running "$ value moving" readout. Parcel sale events animate now; permit events join after geocoding.
- **Leads** — full sortable list → click any row for the **lead drawer**: the four dimensions side by side, WHY THIS MATTERS, tags grouped by namespace, full event timeline, and the transparent score build.
- **Capital Flow** — the §3 tables; click a market to filter leads to that origin.
- **Contractors** — leaderboard (331 ranked): permits, recency, sites, trade share, declared value, geographic dominance.
- **Operators** — portfolio table; click to filter the map to a portfolio.
- **Coverage** — headline, permit completeness by jurisdiction, lead-warehouse breadth, the category health matrix, and append-only warehouse stats.
- **CSV export** preserves all four dimensions (`property_city`, `property_jurisdiction`, `permit_jurisdiction`, `owner_city`, `owner_state`, `owner_zip`, `owner_origin_market`, …).

Also: the harvest workflow now stages the whole `docs/data` tree, so the **append-only warehouse ledger persists** across runs.

## 7. What lights up NOW vs after one harvest

**Now (offline rebuild over existing data):** every lead tagged + scored with WHY THIS MATTERS; Capital Flow (903 origins, 86 imported, $7.7M); ownership coverage; contractor leaderboard; coverage dashboards; lead drawer; the 500 parcels on the map with out-of-state rings; playback of parcel sales.

**After you run one harvest** (Actions → **GRIT harvest** → Run workflow): the APN→centroid join geocodes the ~900 permit leads → permits appear across the whole valley; permit events join playback; permit origins enrich Capital Flow with real destination spread beyond Las Vegas.

The sandbox can't reach county servers, so I verified the backend with `python -m grit selftest` (exit 0) and `python -m grit rebuild`, not a live pull. No coordinates were fabricated.

## 8. Verification

`selftest` exit 0 (incl. new capital-flow + four-dimension asserts) · `rebuild` → 1,412 cards / 899 operators / 331 contractors · `coverage` + `contractors` CLI render · all JSON valid · console JS syntax-checked, zero browser-storage APIs, all data keys present.

## Untouched (awaiting your sign-off)

Per your instruction, the canonical docs were **not** regenerated: `MANIFESTO.md`, `BOOTSTRAP.xml`, `README.md`, `EVENT_MATRIX.md`, `PHASE_*_HANDOFF.md`. Say the word once you've reviewed `.105` and I'll bring them up to date.
