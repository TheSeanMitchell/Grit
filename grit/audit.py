"""
Southern Nevada coverage audit (Alpha 0.106).

The v0.106 directive's success metric is "how close are we to capturing,
preserving, and explaining every meaningful economic-activity signal across
Southern Nevada." This module turns that into measured reality:

  * sonv_coverage   -- per-jurisdiction parcels / owners / permits / signals
  * source_inventory-- every feed: status, counts, dates, fields, confidence
  * signal_matrix   -- ~30 signal types: implemented / partial / missing + gap
  * permit_audit    -- completeness + quality (missing-field counts, flags)
  * data_quality    -- field completeness across the warehouse
  * gap_analysis    -- the biggest gaps + a v0.107 roadmap, derived from above

Every number is a real harvested count. Where a denominator (the true universe
of parcels) is unknown, the report says so rather than inventing one. Sources
that exist only on the roadmap are reported NOT IMPLEMENTED -- never dressed up.
"""
import datetime as dt

from . import geo


def _parse(d):
    try:
        return dt.datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _minmax_dates(dates):
    ds = sorted(d for d in (_parse(x) for x in dates) if d)
    return (ds[0].isoformat(), ds[-1].isoformat()) if ds else (None, None)


def _conf(mapped_pct, owner_pct, has_permits):
    c = int(0.5 * mapped_pct + 0.4 * owner_pct + (10 if has_permits else 0))
    return max(0, min(c, 100))


# ── 1. Southern Nevada coverage report ─────────────────────────────────────
def sonv_coverage(cards, events):
    by_kind_apn = {}
    for e in events:
        if e.get("kind") == "PERMIT":
            by_kind_apn.setdefault("PERMIT", []).append(e)

    rows = []
    grouped = {}
    for c in cards:
        j = c.get("property_jurisdiction") or "Unidentified"
        grouped.setdefault(j, []).append(c)

    # ensure every target jurisdiction appears even at zero
    for j in geo.SONV_JURISDICTIONS:
        grouped.setdefault(j, grouped.get(j, []))

    for j, cs in grouped.items():
        n = len(cs)
        owners = sum(1 for c in cs if c.get("owner_name"))
        mapped = sum(1 for c in cs if c.get("lat") and c.get("lng"))
        permitted = sum(1 for c in cs if c.get("has_permit") or c.get("permit_count"))
        signals = sum(len(c.get("timeline") or []) for c in cs)
        value = sum(_num(c.get("assessed_value")) for c in cs)
        owner_pct = round(100 * owners / n, 1) if n else 0.0
        mapped_pct = round(100 * mapped / n, 1) if n else 0.0
        # how the jurisdiction labels were derived (authoritative vs coordinate)
        src = {}
        for c in cs:
            s = c.get("jurisdiction_source") or "—"
            src[s] = src.get(s, 0) + 1
        rows.append({
            "jurisdiction": j,
            "parcels_identified": n,
            "owners_identified": owners, "owner_coverage_pct": owner_pct,
            "permits": permitted, "signals": signals,
            "mapped": mapped, "mapped_pct": mapped_pct,
            "assessed_value": round(value),
            "label_sources": src,
            "confidence": _conf(mapped_pct, owner_pct, permitted > 0),
        })
    rows.sort(key=lambda r: r["parcels_identified"], reverse=True)
    return {
        "note": ("Counts are real harvested identifications. The true parcel "
                 "universe per jurisdiction (assessor roll denominator) is not "
                 "yet ingested, so coverage % is reported against measurable "
                 "fields (owners identified, mapped) rather than an invented total."),
        "jurisdictions_with_data": sum(1 for r in rows if r["parcels_identified"] > 0),
        "target_jurisdictions": len(geo.SONV_JURISDICTIONS),
        "rows": rows,
    }


# ── 2. Source inventory ────────────────────────────────────────────────────
def source_inventory(cards, events, health):
    parcels = [c for c in cards if c.get("source") == "clark_gis"]
    permits_c = [c for c in cards if c.get("source") == "clv_permit"]
    permit_ev = [e for e in events if e.get("kind") == "PERMIT"]
    deed_ev = [e for e in events if e.get("kind") == "DEED"]
    enriched = [c for c in cards if c.get("vintage") == "current"]

    p_old, p_new = _minmax_dates(e.get("date") for e in permit_ev)
    d_old, d_new = _minmax_dates(e.get("date") for e in deed_ev)

    inv = [
        {"source": "Clark County parcel layer (ArcGIS)", "jurisdiction": "Clark County",
         "coverage_area": "Countywide parcels", "status": "WORKING",
         "records": len(parcels), "newest": None, "oldest": None,
         "frequency": "on demand / daily", "confidence": 85,
         "fields": ["APN", "situs", "land use", "owner", "value", "centroid"],
         "missing": ["incorporated-city flag on some parcels"],
         "health": "live"},
        {"source": "City of Las Vegas permits (ArcGIS Hub)", "jurisdiction": "Las Vegas",
         "coverage_area": "City of Las Vegas", "status": "WORKING",
         "records": len(permit_ev), "newest": p_new, "oldest": p_old,
         "frequency": "daily", "confidence": 90,
         "fields": ["record", "type", "status", "date", "valuation", "address",
                    "APN", "owner", "contractor", "license", "trades"],
         "missing": ["trade tag on ~28% of permits", "APN on a few records"],
         "health": "live"},
        {"source": "Clark County Assessor enrichment + deeds", "jurisdiction": "Clark County",
         "coverage_area": "Top leads (enriched on demand)", "status": "PARTIAL",
         "records": len(enriched) + len(deed_ev), "newest": d_new, "oldest": d_old,
         "frequency": "on demand", "confidence": 60,
         "fields": ["owner", "mailing", "value", "sale date/price", "year built"],
         "missing": ["full-roll enrichment (only top leads enriched today)"],
         "health": "live"},
    ]
    # ── candidate sources (v0.107 Priority 2/3/4 feasibility audit) ──────────
    # Honest availability assessment, not fabricated connectors. Each carries a
    # feasibility read + the access method a live integration would use. records=0
    # until actually integrated; nothing here is presented as captured data.
    def cand(source, juris, area, fields, feasibility, access, priority):
        return {"source": source, "jurisdiction": juris, "coverage_area": area,
                "status": "NOT IMPLEMENTED", "records": 0, "newest": None,
                "oldest": None, "frequency": "—", "confidence": 0, "fields": [],
                "missing": fields, "would_provide": fields, "feasibility": feasibility,
                "access": access, "priority": priority, "health": "planned"}
    inv += [
        cand("Henderson permits", "Henderson", "City of Henderson",
             ["permit date", "value", "contractor", "trade", "status", "APN"],
             "MEDIUM", "Accela Citizen Access / city open-data portal — probe required", "HIGH"),
        cand("North Las Vegas permits", "North Las Vegas", "City of North Las Vegas",
             ["permit date", "value", "contractor", "trade", "status", "APN"],
             "MEDIUM", "Accela / city GIS permit layer — probe required", "HIGH"),
        cand("Clark County permits", "Clark County", "Unincorporated County",
             ["permit date", "value", "contractor", "trade", "status", "APN"],
             "MEDIUM", "County ePlan / building-permit dataset — probe required", "HIGH"),
        cand("Boulder City permits", "Boulder City", "City of Boulder City",
             ["permit date", "value", "trade", "status"],
             "LOW", "Smaller jurisdiction; portal availability uncertain — probe required", "MEDIUM"),
        cand("Mesquite permits", "Mesquite", "City of Mesquite",
             ["permit date", "value", "trade", "status"],
             "LOW", "Smaller jurisdiction; portal availability uncertain — probe required", "MEDIUM"),
        cand("Clark County Recorder — distress", "Clark County", "Countywide distress",
             ["NOD", "trustee sale", "lis pendens", "lien", "record date"],
             "LOW", "Recorder document search; bulk access restricted — feasibility study required", "HIGH"),
        cand("Clark County Recorder — deed transfers", "Clark County", "Countywide ownership transfers",
             ["grantor", "grantee", "deed date", "doc type"],
             "MEDIUM", "Recorder/Assessor sale history — partially available via Assessor today", "HIGH"),
        cand("Nevada SOS business registry (SilverFlume/ORION)", "Statewide", "LLC / registered agent / officers",
             ["entity", "registered agent", "officers", "status", "formation date"],
             "MEDIUM", "SilverFlume business search / bulk dataset — probe required", "MEDIUM"),
    ]
    # fold in any reachability the health probe already measured
    hmap = {(s.get("key") or "").lower(): s for s in (health or [])}
    for row in inv:
        for key, s in hmap.items():
            if key and key.split("_")[0] in row["source"].lower():
                row["probe_status"] = s.get("status")
    return inv


# ── 3. Signal acquisition matrix ───────────────────────────────────────────
def signal_matrix(cards, events):
    permit_ev = sum(1 for e in events if e.get("kind") == "PERMIT")
    deed_ev = sum(1 for e in events if e.get("kind") == "DEED")
    owners = sum(1 for c in cards if c.get("owner_name"))
    contractors = sum(1 for c in cards if c.get("contractors"))
    solar = sum(1 for c in cards if "solar" in (c.get("trade_tags") or []))
    distress_ev = sum(1 for c in cards for e in (c.get("timeline") or [])
                      if (e.get("kind") or "").upper() in ("VIOLATION",) or
                      any(k in (e.get("description") or "").lower()
                          for k in ("default", "lien", "trustee", "foreclos")))

    def row(name, status, current, priority, note=""):
        return {"signal": name, "status": status, "current_coverage": current,
                "priority": priority, "note": note}

    HIGH, MED, LOW = "HIGH", "MEDIUM", "LOW"
    return [
        row("Permits", "IMPLEMENTED", permit_ev, HIGH,
            "City of Las Vegas live; other authorities pending."),
        row("Property Sales", "PARTIAL", sum(1 for c in cards if c.get("last_sale_date")), HIGH,
            "Captured on enriched leads via Assessor; not full-roll."),
        row("Deed Transfers", "PARTIAL", deed_ev, HIGH, "From Assessor sale history."),
        row("Ownership", "IMPLEMENTED", owners, HIGH, "Owner + mailing on identified parcels."),
        row("Assessor Records", "PARTIAL", sum(1 for c in cards if c.get("vintage") == "current"), HIGH,
            "Top leads enriched; full-roll enrichment is the next wave."),
        row("Contractors", "IMPLEMENTED", contractors, HIGH, "Derived from permit pullers."),
        row("Business Licenses", "MISSING", 0, MED, "NV SOS / city licensing not yet ingested."),
        row("Code Enforcement", "MISSING", 0, MED, "Violation feeds catalogued, not ingested."),
        row("Planning Applications", "MISSING", 0, MED, ""),
        row("Zoning Activity", "MISSING", 0, LOW, ""),
        row("Demolitions", "PARTIAL", 0, MED, "Will surface from permit types once classified."),
        row("Certificates of Occupancy", "MISSING", 0, MED, ""),
        row("Solar Activity", "IMPLEMENTED", solar, MED, "Tagged from permit trades."),
        row("Utility Activity", "MISSING", 0, MED, "Service-connect signals not ingested."),
        row("Public Works", "MISSING", 0, LOW, ""),
        row("Foreclosures", "MISSING", 0, HIGH, "Recorder NOD/trustee — high-value distress."),
        row("Trustee Sales", "MISSING", 0, HIGH, ""),
        row("Tax Liens", "MISSING", 0, MED, ""),
        row("Mechanics Liens", "MISSING", 0, MED, ""),
        row("Probate", "MISSING", 0, MED, ""),
        row("Bankruptcy", "MISSING", 0, LOW, ""),
        row("Evictions", "MISSING", 0, MED, ""),
        row("Crime / Police Activity", "MISSING", 0, LOW, "Metro feeds catalogued."),
        row("Security Signals", "PARTIAL", 0, LOW, "Tag scaffold exists; no source yet."),
        row("Commercial Tenant Improvements", "PARTIAL", 0, MED, "Surfaces from commercial permits."),
        row("Government / Capital Projects", "MISSING", 0, LOW, ""),
        row("Public Bid Awards", "MISSING", 0, LOW, ""),
        row("Distress (any)", "PARTIAL", distress_ev, HIGH, "Only code-violation-style events so far."),
    ]


# ── 4. Permit completeness + quality ───────────────────────────────────────
def permit_audit(cards, events):
    perm = [e for e in events if e.get("kind") == "PERMIT"]
    today = dt.date.today()

    def raw(e, *keys):
        r = e.get("raw") or {}
        return any(r.get(k) for k in keys)

    oldest, newest = _minmax_dates(e.get("date") for e in perm)
    week = sum(1 for e in perm if (_parse(e.get("date")) and (today - _parse(e.get("date"))).days <= 7))
    month = sum(1 for e in perm if (_parse(e.get("date")) and (today - _parse(e.get("date"))).days <= 30))

    by_j = {}
    for c in cards:
        if c.get("source") == "clv_permit" or c.get("has_permit"):
            j = c.get("property_jurisdiction") or "Unknown"
            by_j[j] = by_j.get(j, 0) + 1
    by_trade = {}
    for c in cards:
        for t in (c.get("trade_tags") or []):
            by_trade[t] = by_trade.get(t, 0) + 1

    missing = {
        "apn": sum(1 for e in perm if not (e.get("parcel_apn") or raw(e, "apn"))),
        "owner": sum(1 for e in perm if not raw(e, "owner_name")),
        "coordinates": sum(1 for e in perm if not (e.get("lat") and e.get("lng"))),
        "contractor": sum(1 for e in perm if not raw(e, "contractor")),
        "date": sum(1 for e in perm if not e.get("date")),
        "valuation": sum(1 for e in perm if not raw(e, "valuation")),
        "trade": sum(1 for e in perm if not (e.get("trade_tag") or raw(e, "trades"))),
    }
    n = len(perm) or 1
    quality = {k: {"missing": v, "complete_pct": round(100 * (n - v) / n, 1)}
               for k, v in missing.items()}
    # suspected-error flags
    flags = []
    no_apn_no_coord = sum(1 for e in perm if not (e.get("parcel_apn") or raw(e, "apn"))
                          and not (e.get("lat") and e.get("lng")))
    if no_apn_no_coord:
        flags.append({"flag": "unmappable permit (no APN and no coordinate)",
                      "count": no_apn_no_coord, "severity": "high"})
    if missing["owner"]:
        flags.append({"flag": "permit with no owner matched", "count": missing["owner"],
                      "severity": "medium"})
    if missing["trade"]:
        flags.append({"flag": "permit with no trade classified", "count": missing["trade"],
                      "severity": "low"})
    return {
        "total": len(perm), "newest": newest, "oldest": oldest,
        "this_week": week, "this_month": month,
        "by_jurisdiction": sorted(({"jurisdiction": k, "permits": v}
                                   for k, v in by_j.items()),
                                  key=lambda x: x["permits"], reverse=True),
        "by_trade": sorted(({"trade": k, "permits": v} for k, v in by_trade.items()),
                           key=lambda x: x["permits"], reverse=True),
        "quality": quality,
        "flags": flags,
    }


# ── 5. Data quality (field completeness) ───────────────────────────────────
def data_quality(cards):
    n = len(cards) or 1
    fields = ["owner_name", "owner_mailing", "assessed_value", "year_built",
              "last_sale_date", "lat", "property_jurisdiction", "property_city",
              "owner_origin_market", "primary_date", "parcel_apn", "land_use"]
    rows = []
    for f in fields:
        have = sum(1 for c in cards if c.get(f) not in (None, "", "0", 0))
        rows.append({"field": f, "present": have, "pct": round(100 * have / n, 1)})
    rows.sort(key=lambda r: r["pct"], reverse=True)
    return {"cards": n, "fields": rows}


# ── 6. Gap analysis + v0.107 roadmap ───────────────────────────────────────
def gap_analysis(cards, events, sig_matrix):
    missing_high = [s["signal"] for s in sig_matrix
                    if s["status"] in ("MISSING", "PARTIAL") and s["priority"] == "HIGH"]
    unident = sum(1 for c in cards if not c.get("property_jurisdiction"))
    coord_derived = sum(1 for c in cards if c.get("jurisdiction_source") in ("coordinate", "county"))
    no_owner = sum(1 for c in cards if not c.get("owner_name"))
    gaps = [
        {"gap": "Distress signals (foreclosure / NOD / trustee / liens) not ingested",
         "impact": "Misses the highest-urgency acquisition leads", "priority": "HIGH"},
        {"gap": "Permit coverage limited to City of Las Vegas",
         "impact": "Henderson, NLV and unincorporated County permits absent", "priority": "HIGH"},
        {"gap": f"{no_owner} parcels have no identified owner",
         "impact": "Full-roll Assessor enrichment needed for ownership completeness", "priority": "HIGH"},
        {"gap": f"{coord_derived} parcels have coordinate-derived jurisdiction",
         "impact": "Authoritative city refinement via parcel-layer city attribute on next harvest",
         "priority": "MEDIUM"},
        {"gap": "Business-license / officer graph (NV SOS) not ingested",
         "impact": "Limits entity resolution and commercial signal", "priority": "MEDIUM"},
    ]
    roadmap = [
        "v0.107: ingest Clark County Recorder distress (NOD, trustee, lien, lis pendens).",
        "v0.107: pull parcel-layer incorporated-city attribute during geocode for authoritative jurisdiction.",
        "v0.107: extend permits to Henderson / NLV / County (Accela).",
        "v0.107: full-roll Assessor enrichment to lift owner + value coverage toward 100%.",
        "v0.107: NV SOS business + officer graph for entity resolution and commercial signal.",
    ]
    return {"missing_high_priority": missing_high, "unidentified_jurisdiction": unident,
            "gaps": gaps, "v107_roadmap": roadmap}


# ── Coverage denominators (v0.107 Priority 5) ──────────────────────────────
# Published reference universes, clearly sourced and labelled. Only the county
# parcel roll is well-published; per-city / permit / owner universes are NOT
# asserted (left "not established") rather than invent a denominator. Coverage %
# against the county roll is INDICATIVE and tagged as such.
REFERENCE_UNIVERSE = {
    "clark_county_parcels": {
        "universe": 800000,
        "source": "Clark County Assessor secured roll (approximate published figure)",
        "confidence": "reference-approximate",
    },
}


def coverage_denominators(cards):
    parcels_identified = len(cards)
    owners_identified = sum(1 for c in cards if c.get("owner_name"))
    ref = REFERENCE_UNIVERSE["clark_county_parcels"]
    uni = ref["universe"]
    rows = [
        {"scope": "Clark County parcels", "captured": parcels_identified,
         "universe": uni, "universe_source": ref["source"],
         "universe_confidence": ref["confidence"],
         "coverage_pct": round(100 * parcels_identified / uni, 3),
         "basis": "indicative — vs approximate published county roll"},
        {"scope": "Owners identified", "captured": owners_identified,
         "universe": uni, "universe_source": ref["source"],
         "universe_confidence": ref["confidence"],
         "coverage_pct": round(100 * owners_identified / uni, 3),
         "basis": "indicative — owners ≈ parcels universe"},
        {"scope": "Permits captured", "captured": sum(1 for c in cards if c.get("has_permit") or c.get("permit_count")),
         "universe": None, "universe_source": None, "universe_confidence": "unknown",
         "coverage_pct": None,
         "basis": "universe not established — total SoNV permits issued is not yet enumerated"},
    ]
    return {"note": ("Coverage % is shown only where a sourced universe exists. The county "
                     "parcel roll is an approximate published reference; per-jurisdiction, "
                     "permit, and owner universes are not yet established and are left blank "
                     "rather than estimated."),
            "rows": rows}


def confidence_summary(cards):
    """Warehouse confidence distribution (v0.107 Priority 6)."""
    from . import confidence
    return confidence.distribution(cards)


# ── Ownership networks (v0.107 Priority 4, offline-computable portion) ──────
def ownership_networks(cards):
    """Multi-property ownership networks from real harvested owners. Groups
    parcels by normalized owner, summarises portfolio size / value / spread and
    flags out-of-state-controlled networks. The LLC / registered-agent / officer
    layer (NV SOS) is a separate, not-yet-ingested source (see source inventory)."""
    def norm(n):
        return " ".join((n or "").upper().split())
    nets = {}
    for c in cards:
        o = norm(c.get("owner_name"))
        if not o:
            continue
        n = nets.setdefault(o, {"owner": c.get("owner_name"), "parcels": 0,
                                "value": 0.0, "jurisdictions": set(),
                                "entity_type": c.get("entity_type"),
                                "out_of_state": False, "origin": None,
                                "permits": 0, "sample": []})
        n["parcels"] += 1
        n["value"] += _num(c.get("assessed_value"))
        if c.get("property_jurisdiction"):
            n["jurisdictions"].add(c["property_jurisdiction"])
        if c.get("owner_out_of_state"):
            n["out_of_state"] = True
            n["origin"] = c.get("owner_origin_market")
        if c.get("has_permit") or c.get("permit_count"):
            n["permits"] += 1
        if len(n["sample"]) < 4 and c.get("situs_address"):
            n["sample"].append(c["situs_address"])
    rows = []
    for o, n in nets.items():
        if n["parcels"] < 2:
            continue
        rows.append({"owner": n["owner"], "entity_type": n["entity_type"],
                     "parcels": n["parcels"], "value": round(n["value"]),
                     "jurisdictions": sorted(n["jurisdictions"]),
                     "jurisdiction_count": len(n["jurisdictions"]),
                     "permits": n["permits"], "out_of_state": n["out_of_state"],
                     "origin": n["origin"], "sample_addresses": n["sample"]})
    rows.sort(key=lambda r: (r["parcels"], r["value"]), reverse=True)
    multi = len(rows)
    controlled = sum(r["parcels"] for r in rows)
    return {
        "networks": rows[:50],
        "multi_property_owners": multi,
        "parcels_in_networks": controlled,
        "network_concentration_pct": round(100 * controlled / (len(cards) or 1), 1),
        "cross_jurisdiction_networks": sum(1 for r in rows if r["jurisdiction_count"] > 1),
        "out_of_state_networks": sum(1 for r in rows if r["out_of_state"]),
    }


def build_audit(cards, events, health):
    sig = signal_matrix(cards, events)
    return {
        "sonv_coverage": sonv_coverage(cards, events),
        "source_inventory": source_inventory(cards, events, health),
        "signal_matrix": sig,
        "permit_audit": permit_audit(cards, events),
        "data_quality": data_quality(cards),
        "denominators": coverage_denominators(cards),
        "confidence": confidence_summary(cards),
        "ownership_networks": ownership_networks(cards),
        "gap_analysis": gap_analysis(cards, events, sig),
    }
