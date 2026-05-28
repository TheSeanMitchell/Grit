# GRIT — MANIFESTO

> **Phase 0.103.** This is the canonical mission. All architecture, scope, and
> roadmap decisions defer to this document. See `EVENT_MATRIX.md` for the
> catalogued source landscape.

---

## What GRIT is

GRIT is an **event-driven acquisition intelligence system** for local economic
activity in the Las Vegas / Clark County market.

It is not a CRM. It is not a contractor portal. It is not a dashboard.

It is a continuously improving radar that discovers monetizable real-world
activity earlier and organizes it better than competitors.

## The five things GRIT does

1. **Harvest** public monetizable event signals.
2. **Normalize** the entities behind them (PERSON / LLC / TRUST / HOA / GOVERNMENT / COMMERCIAL).
3. **Score and cluster** opportunities by recency, monetizability, repeatability, automation potential, durability, and operational cost.
4. **Route** opportunities toward monetization systems.
5. **Reduce** human labor required to operate multiple revenue systems simultaneously.

## What GRIT is grounded in

- Real public data.
- Durable acquisition systems.
- Human-in-the-loop execution.
- No synthetic data. No fake activity. No fabricated enrichment.

## Event sources (priority order)

Each event below is a time-stamped, geocoded signal that a parcel/address just
became more monetizable.

1. **Permits** — building, trade, roofing, HVAC, solar, electrical, plumbing.
2. **Deeds** — recorded sales, quitclaims, notices of default.
3. **Contractor licenses** — new issuance, classification, status changes.
4. **Code violations** — nuisance abatement, distressed properties.
5. **LLC registrations** — new business entities tied to addresses.
6. **Review spikes** — surges in complaints or local sentiment.
7. **Local service requests** — public service / 311-style signals.

## Architecture decisions are judged against

- Discovering monetizable activity earlier.
- Organizing it better than competitors.
- Recency / monetizability / repeatability / automation potential / durability / low operational cost.

## What GRIT must not become

- An endlessly redesigned UI.
- A theoretical AI system.
- A fabricator of data or activity.
- An over-engineered agent framework built before real acquisition flow exists.

## The 0.103 shift: signal density

0.102 solved data *freshness* (live Assessor enrichment). The bottleneck is now
*signal density*. GRIT evolves from "parcel → current owner" into a continuous
city activity radar on one chain: **EVENT → ENTITY → MONEY.** Something happens,
GRIT detects it, identifies who is involved, scores monetization probability, and
routes it toward action. The full source landscape lives in `EVENT_MATRIX.md`.

## Shipped through 0.103

- **Live Assessor enrichment (0.102).** Per-APN GET returns CURRENT owner, value,
  last sale, and characteristics — free, deterministic, no fabrication.
- **EVENT_MATRIX.md (0.103).** Every realistic monetizable signal in Clark County
  and its cities, scored on freshness, access, anti-bot reality, monetization, and
  compliance — grounded in verified-live endpoints, not guesses.
- **Source registry rebuilt** around the matrix (sanctioned channels first).

## Where GRIT is going next (the 0.103 build sequence)

1. County permit ingestion (Accela) — capture, calibrate, ingest PERMIT events.
2. Recorder distress ingestion — deeds / NOD / trustee sales / liens by type+date.
3. SilverFlume entity ingestion (bulk/API) — LLC events + officer/agent graph.
4. NSCB license sync — buyer list + permit-puller verification.
5. Recency-weighted event scoring, then the entity graph, then the operator console.

## The stay-clean doctrine

Sanctioned channel first (open data → bulk → API → records request → polite
residential capture); never IP-evasion. Output is acquisition/contractor signal,
never a consumer report. Don't resell raw GIS or recorded documents. Outreach
rules (TCPA/DNC, NRS 645F) gate the *contact*, not the harvest. Staying clean is
the durability strategy.
