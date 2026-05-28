# GRIT — MANIFESTO

> **Alpha 0.101.** This is the canonical mission. All architecture, scope, and
> roadmap decisions defer to this document.

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

## Where GRIT is going next (post-0.101)

- Permit ingestion (Accela) from a residential IP.
- Deed ingestion (Recorder).
- Property timelines and event histories per parcel.
- Cluster heat detection in the map UI.
- Monetization routing — opportunity → contractor partner → tracked outcome.
