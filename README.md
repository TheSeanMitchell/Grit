# GRIT

**Ground-truth Real-estate Intelligence & Targeting — Southern Nevada.**

GRIT is a self-updating warehouse of economic activity across Clark County,
Nevada. It captures public signals (permits, sales, ownership, code enforcement,
business licenses) and chains them into acquisition intelligence:
**EVENT → ENTITY → MONEY.** It runs on zero paid infrastructure.

See `MANIFESTO.md` for the doctrine and `BOOTSTRAP.xml` for a full architecture
map. This README is the practical guide.

---

## How it's built

- **Backend:** Python 3 standard library only — no third-party dependencies.
- **Compute:** a GitHub Action (`.github/workflows/harvest.yml`) runs the harvest
  on a schedule and commits the results.
- **Storage:** flat JSON in `docs/data/` — no database, no server.
- **Console:** a single static HTML page (`docs/index.html`) served by GitHub
  Pages — a Leaflet map plus tabs for Leads, Capital Flow, Contractors,
  Operators, Coverage, and Audit. No build step, no browser storage.

The whole system is a package (`grit/`) plus a static console (`docs/`).

## Running it

```bash
python -m grit selftest   # offline fixture test; never touches docs/data
python -m grit rebuild     # recompute all outputs from existing harvested data
python -m grit harvest     # LIVE harvest (needs network; runs in the Action)
```

`harvest` reaches live county/city/free data sources, so it runs in the GitHub
Action (or any machine with network access). `rebuild` and `selftest` are offline:
use them to verify changes. Coverage numbers only move on a real `harvest`.

To run a harvest manually: **Actions → "GRIT harvest" → Run workflow.**

## What it pulls (all free)

| Signal | Source | Status |
| --- | --- | --- |
| Parcels: geometry + owner + mailing + land-use | Clark County parcel layer | live |
| Building permits (all types) | City of Las Vegas (ArcGIS Hub) | live |
| Code enforcement violations (distress) | City of Las Vegas (ArcGIS Hub) | wired (0.109) |
| Business licenses (commercial/entity) | City of Las Vegas (ArcGIS Hub) | wired (0.109) |
| Crime (area signal) | LVMPD open data | ready — set `LVMPD_CRIME_ITEM` |

Parcel-level **value / square footage / beds / baths** are **not** available from
any free API — Clark County sells them as the paid AOEXTRACT / AORES bulk
extracts. GRIT captures everything free and reports the paid gap honestly rather
than faking it. See the **Coverage** and **Audit** tabs for live denominators,
the confidence distribution, and the Signal Acquisition Matrix.

## Coverage at a glance

Coverage has two ceilings, tracked separately in the console:

- **Breadth** (how many of ~900k parcels) — limited by a deliberate cap, not by
  data. Free to raise; bounded only by what a static site can render.
- **Depth** (value/sqft/beds) — limited by data access; paid-only.

GRIT is signal-driven: it captures every event it can and enriches the parcels
behind them, measuring against the real universe instead of painting every
dormant parcel.

## Configuration

Everything tunable lives in `grit/config.py`: source endpoints and ArcGIS item
ids, the breadth cap (`CARDS_MAX`), per-source caps, and field hints. To wire a
new free ArcGIS Hub dataset, add its item id — the connector resolves the live
layer at harvest time and maps fields by hint, so it degrades gracefully if a
column is renamed.

## Principles

No synthetic data. Append-only history. Transparent scoring (every score ships
its reasons). Four distinct location dimensions. Measured confidence on every
field. Southern Nevada only. If a fact isn't known, the field is empty — never
invented.
