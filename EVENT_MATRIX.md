# GRIT — EVENT MATRIX

> **Phase 0.103.** The canonical operating encyclopedia of monetizable public
> signals in Clark County and its incorporated cities. This file answers one
> question for every source: *what does it expose, how fresh is it, how do we
> get it without getting blocked or sued, and what is it worth?*
>
> Every endpoint below was **verified live (2026-05)** or is explicitly marked
> `UNVERIFIED` / `NEEDS-VALIDATION`. Per the absolute rules, nothing here is a
> guessed URL dressed up as a confirmed one. If a source is speculative, it says so.

---

## The model this matrix serves

```
EVENT  →  ENTITY  →  MONEY
something happens   who is involved   how it's monetized
```

A source earns a place here only if it emits **time-stamped, geocodable events**
that can be joined to a parcel/APN or an entity (PERSON / LLC / TRUST / CONTRACTOR).
A source that only emits static state (e.g. a flat parcel table with no date) is
context, not signal — useful for enrichment, not for the radar.

---

## How to read a source entry

Each source is scored on the dimensions the 0.103 directive requires:

| Field | Meaning |
|---|---|
| **Tier** | A = clean/sanctioned channel, cloud-safe · B = ViewState/session portal, residential + low-volume · C = lower-freshness / needs-validation |
| **Access** | The *preferred* channel: open-data API › bulk download › public-records request › polite low-volume capture |
| **Freshness** | How current the data is (daily / weekly / quarterly / stale) |
| **Cadence** | How often it's worth re-harvesting |
| **Cloud-OK** | Can the free GitHub runner harvest it, or does it need the operator's residential Las Vegas IP? |
| **Deterministic** | Can it be parsed by a stable, label-anchored parser (yes) or is it fragile/JS-rendered (no)? |
| **Monetization** | What the event is worth and to whom |
| **Durability** | How likely the access method survives schema/portal changes |

**Anti-bot honesty.** Some portals return HTTP 403 to datacenter IPs. GRIT's
answer is **not** proxy rotation or IP evasion — it is (1) prefer the sanctioned
channel that *wants* to be read (open-data hubs, bulk downloads, public-records
requests, documented APIs), and (2) where only a ViewState portal exists, capture
at **human volume from the operator's own residential connection**, throttled and
polite. A harvester that respects rate limits and reads the front door it was
given does not get banned — which is exactly the Source Resilience (Priority 7)
the directive asks for. Staying clean *is* the durability strategy.

---

## TIER A — clean / sanctioned channels (harvest now, cloud-safe)

These are the backbone. They are public by statute, designed to be read
programmatically or bought in bulk, and survive runner harvesting.

### A1 · Clark County GISMO — parcels / geometry / base layers
- **Endpoint:** `https://maps.clarkcountynv.gov/arcgis/rest/services` (REST) and the ArcGIS Hub open-data site `https://hub.arcgis.com/` (org `ccgismo`). Legacy `gisgate.co.clark.nv.us` also live (hostname-mismatched TLS — see config).
- **Tier:** A · **Access:** ArcGIS REST query / Hub download · **Freshness:** parcels current; modern Assessor GIS layer exposes APN + geometry only · **Cadence:** weekly · **Cloud-OK:** yes · **Deterministic:** yes.
- **Events exposed:** none directly — this is the **spatial spine** that every event joins onto (APN ↔ lat/lng).
- **Monetization:** indirect (geocoding + clustering).
- **Durability:** high. **Compliance:** NRS 250 restricts *redistribution* of the raw county parcel geodatabase — fine to query and derive leads, do **not** resell the raw GIS layer.
- **Status in GRIT:** ✅ live since 0.101.

### A2 · Clark County Assessor — current owner / value / sale / characteristics
- **Endpoint:** `https://maps.clarkcountynv.gov/assessor/AssessorParcelDetail/parceldetail.aspx?hdnparcel=<APN>&logo=1`
- **Tier:** A · **Access:** plain per-APN GET · **Freshness:** current · **Cadence:** per-lead, on enrichment · **Cloud-OK:** yes (verified) · **Deterministic:** yes (label-anchored parser).
- **Events exposed:** **DEED** (recorded sale price/date/type) → already emitted as a timeline event.
- **Monetization:** high — current owner + value + recency is the core lead record.
- **Durability:** high. **Status in GRIT:** ✅ live since 0.102. Throttle: `ENRICH_DELAY`, top `CARDS_ENRICH_MAX` leads/run.

### A3 · Nevada Secretary of State — business entities (SilverFlume / ORION)
- **Endpoint:** `https://esos.nv.gov/EntitySearch/OnlineEntitySearch` (search) · **official Bulk Data Download + API** via SilverFlume / the ORION module.
- **Tier:** A · **Access:** **bulk download + documented API** (sanctioned — no scraping) · **Freshness:** current · **Cadence:** daily/weekly delta · **Cloud-OK:** yes · **Deterministic:** yes (structured).
- **Events exposed:** **LLC_REGISTRATION** (new entity), officer/registered-agent changes, status changes (active→expired→revoked). Search supports **officer name** and **registered-agent name** → this is the join that powers the **entity graph**: the same RA or officer across many LLCs reveals an investor/operator cluster.
- **Monetization:** high — new LLC tied to an address = fresh-money / new-operator signal; RA clustering = "who is moving money."
- **Durability:** high (official API). **Status in GRIT:** 🔲 next-build (registry added 0.103; ingestion is the entity-graph milestone).

### A4 · Nevada State Contractors Board — licenses + discipline
- **Endpoint:** `https://app.nvcontractorsboard.com/Clients/NVSCB/Public/ContractorLicenseSearch/ContractorLicenseSearch.aspx` · bulk via **Public Records Request** (free under $10 of effort).
- **Tier:** A (light B for the live search form) · **Access:** web search by license #/company/principal; bulk via records request · **Freshness:** current · **Cadence:** weekly · **Cloud-OK:** mostly (search form is simple) · **Deterministic:** yes.
- **Events exposed:** **LICENSE_NEW**, classification changes, **suspended/expired** status, disciplinary citations. This is the **buyer list** (every licensed contractor by trade) *and* the verification layer (is this permit-puller licensed / in good standing?).
- **Monetization:** high — contractors are a direct buyer of leads; license status gates who you route to.
- **Durability:** high. **Status in GRIT:** registered; ingestion pending.

---

## TIER B — ViewState / session portals (residential, low-volume, capture-then-build)

These hold the freshest *project* signal but sit behind ASP.NET ViewState portals
that 403 datacenter IPs. Doctrine: **capture a real sample from a residential IP
first, calibrate a deterministic parser against it, then ingest at human volume.**
No events published until a verified parser exists (no fabricated activity).

### B1 · Clark County permits — Accela Citizen Access  ★ highest operational value
- **Endpoint:** `https://citizenaccess.clarkcountynv.gov/CitizenAccess/Cap/CapHome.aspx?module=Building&TabName=Building` (also `https://aca-prod.accela.com/clarkco/`)
- **Tier:** B · **Access:** ViewState search by **site address / parcel # / contractor license / record #**; residential capture · **Freshness:** current (daily) · **Cadence:** daily delta · **Cloud-OK:** no (403 from runner) · **Deterministic:** yes once the ViewState handshake is captured.
- **Events exposed:** **PERMIT** — roofing, HVAC, mechanical, plumbing, electrical, solar, pools, remodels, additions, demolition, commercial TI — with puller, address/APN, valuation, issue date. **The single richest "active project" signal in the city.**
- **Bonus:** the same portal exposes **Code Cases** (`module=...` code enforcement) and the **Public Response** complaint feed → see D-series.
- **Monetization:** very high — a fresh permit *is* an active job + a homeowner + a contractor, all geolocated.
- **Durability:** medium (Accela is stable software; the ViewState handshake is the fragile part). **Note:** county is migrating plan review to **ePermitHub** — watch for a cleaner data surface there. **Status in GRIT:** capture scaffold (`grit/permits.py`); parser pending a real sample.

### B2 · City permits — Las Vegas / Henderson / North Las Vegas
- **Endpoints:** each city runs its own Accela/portal, separate from the county. (Henderson + NLV currently 403 the runner — confirmed in the health matrix.)
- **Tier:** B · same access/parsing profile as B1 · **Cloud-OK:** no.
- **Events exposed:** **PERMIT** for incorporated-city parcels (the county portal does *not* cover these — a coverage gap if skipped).
- **Monetization:** high. **Durability:** medium. **Status:** registered; residential capture pending. Build *after* county permits work end-to-end (same parser, new endpoints).

### B3 · Clark County Recorder — deeds / NOD / trustee sales / liens  ★ the distress engine
- **Endpoint:** `https://recorderecomm.clarkcountynv.gov/AcclaimWeb/` (Acclaim record-search system).
- **Tier:** B · **Access:** search by **Document Type + Record Date range** (also Parcel #, Instrument #) — this is the key: you can pull *every document of a given type recorded yesterday* · **Freshness:** current (next-day) · **Cadence:** daily · **Cloud-OK:** no (session portal) · **Deterministic:** yes.
- **Events exposed:** **DEED** (sales, quitclaims, grant/bargain/sale), **Notice of Default & Election to Sell** (NRS 107.080), **Notice of Trustee's Sale**, **Lis Pendens**, **mechanics liens**, **tax liens**, **reconveyances**. NOD → trustee-sale is the canonical distress timeline.
- **Monetization:** very high — leading indicator of ownership change and distress, weeks ahead of the Assessor reflecting it.
- **Durability:** medium-high. **Compliance:** NV AG has an active alert about firms reselling recorded-document copies — GRIT uses these as *signals*, it does **not** resell document copies. **Status:** registered 0.103; capture-then-build.

---

## TIER C — court, distress, and lower-freshness signals (validate before building)

Real and public, but each needs a captured sample to confirm parseability and an
explicit compliance read before it routes anywhere. **Do not build C-tier before
A and B produce validated flow** (phase-gating rule).

### C1 · Eviction filings — Las Vegas Justice Court / other township courts
- **Endpoint:** `https://cvpublicaccess.co.clark.nv.us/eservices/` (Tyler/Odyssey public access); records also by request (`recordsc@clarkcountynv.gov`).
- **Events:** **summary eviction filings** (landlord-tenant) → distress + likely-turnover signal on rentals.
- **Monetization:** medium-high (tired-landlord leads). **Cloud-OK:** no. **Deterministic:** NEEDS-VALIDATION (Odyssey portals vary).
- **⚠ Compliance:** eviction/court data is sensitive. **FCRA**: if GRIT output is ever used for tenant screening it becomes a consumer report — GRIT's use is acquisition signal, not screening; keep that line bright. Do not build features that profile individual tenants.

### C2 · Probate / inherited property — Eighth Judicial District Court
- **Endpoint:** `https://www.clarkcountycourts.us/` case search (online 1990+).
- **Events:** probate case opened → **inherited-property** turnover signal (a classic acquisition lead).
- **Monetization:** medium-high. **Cloud-OK:** no. **Deterministic:** NEEDS-VALIDATION.
- **⚠ Compliance:** death/probate is sensitive; route as property signal, not person-targeting. NV foreclosure/equity-purchase rules (**NRS 645F**) apply to *outreach* to distressed homeowners — flag at the routing layer, not here.

### C3 · Code enforcement / nuisance abatement
- **Source:** Clark County **Public Response** + Accela **Code Cases** (same door as B1); cities run their own.
- **Events:** **VIOLATION** — overgrowth, junk/debris, illegal occupancy, dangerous building → distressed/absentee owner signal, and a repair-work signal.
- **Monetization:** medium-high (distress + forced-work). **Cloud-OK:** no. **Deterministic:** yes (rides the Accela parser).

### C4 · Business licenses / DBA — county + cities
- **Source:** Clark County business-license search; City of NLV business license; county fictitious-firm-name (DBA).
- **Events:** **business license issuance**, **commercial occupancy change**, restaurant openings/closures.
- **Monetization:** medium (commercial TI work, new-business services). **Deterministic:** NEEDS-VALIDATION.

### C5 · Infrastructure / public works
- **Source:** Clark County & city public-works project lists, RTC, NDOT, utility trenching, fiber/telecom permits (often surface as a permit *type* in B1/B2).
- **Events:** road work, utility expansion, warehouse/logistics buildout, school expansion → **neighborhood-change** and **commercial-cluster** signal.
- **Monetization:** medium (timing + cluster context). **Most of this is reachable as permit metadata — harvest via B1/B2 rather than new sources.**

### C6 · Public sentiment — review / complaint spikes  ⚠ lowest-confidence
- **Source:** local-business reviews, neighborhood forums, complaint surges.
- **Events:** **REVIEW_SPIKE**, complaint surge, contractor-reputation swing.
- **Monetization:** low-medium and **noisy**. **Cloud-OK:** varies. **Deterministic:** no (unstructured, ToS-restricted, easy to over-fit noise).
- **Verdict:** **DEFER.** Most platforms forbid scraping in ToS and the signal-to-noise is poor. Revisit only if a sanctioned API (e.g. an official complaints feed) appears. Do not build social scrapers to chase this — it fails both the durability test and the stay-clean doctrine.

---

## Required-category coverage map (directive checklist)

| Directive category | Primary source(s) | Tier | Status |
|---|---|---|---|
| Permits (roofing/HVAC/solar/etc.) | Accela county + cities (B1/B2) | B | scaffold |
| Deeds / quitclaims | Recorder (B3), Assessor (A2) | A/B | partial (DEED live via A2) |
| Trustee sales / NOD / foreclosure | Recorder (B3) | B | registered |
| Tax / mechanics liens | Recorder (B3) | B | registered |
| Probate / inherited | District Court (C2) | C | validate |
| Absentee / cash / investor concentration | Assessor (A2) + entity graph (A3) | A | partial |
| New / suspended / expired licenses | NSCB (A4) | A | registered |
| High-volume permit pullers | derived from B1 + A4 join | — | after permits |
| Code enforcement / nuisance | Accela code cases / Public Response (C3) | C | registered |
| Vacant / utility shutoff | utilities (NEEDS-VALIDATION) | C | defer |
| Eviction filings | Justice Court (C1) | C | validate |
| LLC / DBA / business license | SilverFlume (A3) + county/city (C4) | A/C | registered |
| Commercial occupancy / openings | business license (C4) + commercial permits (B1) | B/C | validate |
| Review / complaint spikes | C6 | C | **defer** |
| Road / utility / fiber / public works | permit metadata (C5 via B1/B2) | B | after permits |
| High-value sales / flips / refi | Assessor (A2) + Recorder (B3) | A/B | partial |
| Institutional / REIT buying | entity graph (A3) + Recorder (B3) | A/B | after entity graph |

---

## Monetization mapping (EVENT → who pays)

- **Permit (trade)** → the trade contractor (roofer/HVAC/solar) buys a geolocated active-job lead; verify puller via NSCB.
- **Recent sale / new owner** → renovation, services, and "just bought, needs work" outreach.
- **NOD / trustee sale / probate / eviction** → acquisition/wholesale lead (⚠ NRS 645F outreach rules; treat humanely).
- **New LLC + recorded purchase cluster** → investor identified early → partner, compete, or sell them leads.
- **Code violation** → forced-repair work + distressed-owner acquisition angle.
- **Contractor license cluster** → buyer segmentation and territory mapping.

---

## The stay-clean doctrine (this is a competitive asset, not a tax)

1. **Sanctioned channel first.** Open-data hub › bulk download › documented API › public-records request › polite residential capture. Never IP-evasion or proxy rotation.
2. **Human volume.** Throttle every portal (`ENRICH_DELAY`-style spacing); a day's permits is dozens, not thousands.
3. **Signal, not resale.** GRIT derives leads; it does not resell raw GIS (NRS 250) or recorded-document copies (NV AG alert).
4. **Bright FCRA line.** Output is acquisition/contractor signal. It is **not** a consumer report and must never be used for tenant/credit/employment screening.
5. **Outreach rules live at routing, not harvest.** TCPA/DNC for calls/texts; NRS 645F for distressed-homeowner contact. The matrix only *finds* — compliance gates the *contact*.
6. **Degrade gracefully.** A dead portal lowers a source's health score; it never produces fabricated events.

---

## Recommended build sequence (feeds the 0.103 roadmap)

1. **County permits ingestion (B1)** — capture → calibrate parser → ingest. Highest value, unlocks contractor + valuation + recency events.
2. **Recorder distress ingestion (B3)** — NOD / trustee sale / deed by document-type+date. Leading-indicator engine.
3. **SilverFlume entity ingestion (A3)** — bulk/API → LLC events + officer/RA graph. Powers repeat-entity detection.
4. **NSCB license sync (A4)** — buyer list + permit-puller verification + license-status events.
5. **Recency-weighted event scoring** — events.py already carries dates; weight by age so fresh permits/NODs dominate.
6. **Entity graph** — cluster across permits + deeds + LLCs + licenses (the A3/A4/B1/B3 join).
7. **City permits (B2)**, then validate **C-tier** (code, eviction, probate) one at a time, each with a captured sample and a compliance read.

> Anything proposed that is not on this path must pass the judgement test in
> `MANIFESTO.md`: does it find money sooner, organize it better, reduce labor per
> dollar, or improve recency/density/monetization quality? If not — do not build it.
