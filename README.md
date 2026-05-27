# GRIT — Harvest Engine (Alpha)

A public-records **opportunity detection engine** for the Las Vegas / Clark County
home-services market. It harvests real parcel / owner / address data, scores where
contract work is forming, and builds **call cards** you follow up on personally.

Not a CRM. The engine pulls real demand signals; you act on them.

## What's real and running

- **Clark County GIS** (`gisgate.co.clark.nv.us/arcgis/rest/services`) — a live,
  free ArcGIS REST API. The harvester queries it for parcels/owners/addresses
  inside the metro bounding box and turns each into a scored call card. Runs on
  the **free GitHub Actions runner**, no paid infrastructure, no API key.

- **Source Health Matrix** — every source is probed on each run (real reachability,
  latency, record counts, and the actual fields discovered). The console shows it
  live so you can debug every connection.

## Sources registered (see `grit/sources.py`)

| Source | Kind | Tier |
|---|---|---|
| Clark County GIS (parcels/owner/address) | ArcGIS REST API | **live — harvests free** |
| Clark County permits (Accela) | ViewState portal | reachable / **manual wave** |
| Nevada State Contractors Board | .aspx portal | reachable / **manual wave** |
| Clark County Assessor / Recorder | .aspx portals | reachable / **manual wave** |
| Las Vegas / Henderson / N. Las Vegas permits | city portals | reachable / **manual wave** |

The "manual wave" sources are public records with no clean API; they need a headless
browser and likely a residential IP (the free runner's datacenter IP gets blocked).
They're probed for health now and harvested in a later pass — per the "free proxy
first" decision.

## First run (3 steps)

```bash
# 1. find the exact parcel/owner layer on the live server (no schema guessing)
python -m grit discover
#    -> paste the best candidate URL into grit/config.py as CLARK_PARCEL_LAYER

# 2. harvest it into real call cards
python -m grit harvest        # writes docs/data/cards.json + health.json

# 3. serve docs/ via GitHub Pages and open index.html
```

After that, the GitHub Action (`.github/workflows/harvest.yml`) re-harvests daily
and commits fresh data automatically.

## Hard rules (enforced in code)

- **No synthetic data.** Every card field is from a real source attribute or null.
  No records are shown until they're harvested. `selftest` uses a clearly-labeled
  fixture that is never written to `docs/data`.
- Stdlib only. Free hosting. Degrades to empty states without crashing.

## Commands

```
python -m grit health     # probe every source -> health.json
python -m grit discover   # enumerate live ArcGIS layers + real fields
python -m grit harvest    # health + harvest live API -> cards.json
python -m grit selftest   # verify transform logic offline (fixture)
```
