# GRIT — Phase 0.103

**Event-driven acquisition intelligence for Las Vegas / Clark County.**
Not a CRM. Not a contractor portal. A radar that discovers monetizable local
activity earlier and organizes it better than competitors.

Read `MANIFESTO.md` for the mission, `EVENT_MATRIX.md` for the catalogued source
landscape (tiers / access / freshness / monetization / compliance), and
`BOOTSTRAP.xml` for the full project state in one file (the foundational bedrock
for any future session).

---

## What's running at 0.103

- **Multi-source parcel harvest.** Engine samples known owner/address layers,
  verifies real owner+address data is populated, and uses the richest. Runs free
  on the GitHub Actions runner (clean ArcGIS REST).
- **Entity normalization.** Every record is classified into one of
  PERSON / LLC / TRUST / COMMERCIAL / HOA / GOVERNMENT / UNKNOWN.
- **Weighted opportunity scoring.** Entity + contactability + absentee + recent
  sale + value + cluster + event-timeline signals, capped at 100, all signals
  shown for audit. No flat scores, no hidden math.
- **Geographic cluster detection.** Each card carries a real count of neighbor
  leads within 500m, fed into scoring (no fake density).
- **Event contract.** First-class `Event` schema (`grit/events.py`) supporting
  PERMIT / DEED / LICENSE_NEW / VIOLATION / LLC_REGISTRATION / REVIEW_SPIKE /
  SERVICE_REQUEST. Events are joined to cards by parcel APN, forming per-parcel
  timelines that feed the score.
- **Tactical console.** Side-by-side map + sortable spreadsheet list,
  two-way reverse-click linking, entity-colored markers (with HOA/GOV hidden
  by default), CSV export, Source Health Matrix, per-card Assessor lookup.

## Data reality (the honest map)

- Free clean APIs cap at parcel geometry + APN (current) and 2018 owner/address.
- Fresh project-relevant data (permits, deeds, current owner/value/sale) is
  gated behind ViewState portals that block datacenter IPs and that the county
  sells in bulk.
- **The free path is therefore split.** Clean APIs harvest on the cloud
  (GitHub Action). Portal scraping (permits/deeds/Assessor) runs **locally
  from the operator's residential Las Vegas IP** — low volume, real-time, free.

## Operator commands

```bash
python -m grit health     # probe every registered source
python -m grit discover   # walk the ArcGIS catalog and list real fields
python -m grit harvest    # harvest clean APIs -> cards.json + events.json
python -m grit permits    # LOCAL ONLY: capture Accela pages for calibration
python -m grit enrich --sample N   # LOCAL ONLY: capture Assessor samples
python -m grit selftest   # offline verification of transform logic
```

`permits` and `enrich --sample` are **residential-IP** commands — datacenter
runners get 403'd by those portals. Run them from your own machine in Vegas,
push the captured samples, and the precise parsers get written against real
output (capture-then-build, never blind parsing).

## Anti-drift

If a proposed change can't answer **yes** to at least one of the following,
do not build it:

- Does it find money sooner?
- Does it organize money better?
- Does it reduce labor per dollar?
- Does it improve recency / monetizability / repeatability / automation / durability / cost?

See `MANIFESTO.md` for the full mission and `BOOTSTRAP.xml` for the system
contract, including event kinds, next-phase priorities, and the data-reality
findings that shape architecture decisions.
