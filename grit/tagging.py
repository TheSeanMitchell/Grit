"""
Universal tagging (Alpha 0.105, roadmap Phase 4).

"Generate tags aggressively. Every event should create as many useful tags as
possible. Store all tags permanently."

Every tag is namespaced (`category:value`) and DERIVED FROM A REAL FIELD already
on the card -- there is no fabricated signal here, only restatements of harvested
data in a queryable vocabulary. A tag is a fact the data already supports, made
filterable. If a field is missing, its tags simply don't fire (honest empty
state), never a guessed tag.

Categories (per the roadmap): permit, ownership, contractor, real-estate,
distress, security, economic-activity, monetization, geographic, temporal.

The output is a flat, de-duplicated, sorted list stored on `card["tags"]`. The
console turns the namespaces into filter facets.
"""
import datetime as dt

# Map a normalized city / known place to a jurisdiction tag value.
_JURIS = {
    "LAS VEGAS": "las-vegas", "NORTH LAS VEGAS": "north-las-vegas",
    "HENDERSON": "henderson", "BOULDER CITY": "boulder-city",
    "MESQUITE": "mesquite", "ENTERPRISE": "enterprise",
    "SPRING VALLEY": "spring-valley", "SUNRISE MANOR": "sunrise-manor",
    "PARADISE": "paradise", "WHITNEY": "whitney", "SUMMERLIN": "summerlin",
    "MOAPA": "moapa", "MOAPA VALLEY": "moapa-valley", "SEARCHLIGHT": "searchlight",
    "LAUGHLIN": "laughlin", "INDIAN SPRINGS": "indian-springs",
    "MOUNT CHARLESTON": "mount-charleston", "BLUE DIAMOND": "blue-diamond",
}

_RESIDENTIAL_USES = ("single family", "sfr", "residential", "condo", "townhouse",
                     "duplex", "apartment", "mobile home")
_COMMERCIAL_USES = ("commercial", "retail", "office", "industrial", "warehouse",
                    "store", "shopping", "hotel", "motel", "restaurant")
_VACANT_USES = ("vacant", "unimproved")


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _months_since(date_val):
    if date_val in (None, "", " "):
        return None
    try:
        if isinstance(date_val, (int, float)) and date_val > 1e10:
            d = dt.datetime.utcfromtimestamp(date_val / 1000)
        else:
            s = str(date_val)[:10]
            d = dt.datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, OverflowError, OSError, TypeError):
        return None
    now = dt.datetime.utcnow()
    return (now.year - d.year) * 12 + (now.month - d.month)


def _days_since(date_val):
    m = _months_since(date_val)
    return None if m is None else m * 30  # coarse; only used for <90d bucketing


def tags_for_card(card):
    """Return the full namespaced tag set for one card. Pure function of the
    card's already-harvested fields."""
    t = set()

    # ── entity / ownership ────────────────────────────────────────────────
    et = (card.get("entity_type") or "UNKNOWN").upper()
    t.add(f"entity:{et.lower()}")
    owner_mail = card.get("owner_mailing")
    situs = card.get("situs_address")
    if owner_mail and situs:
        from .pipeline import _addr_differs
        if _addr_differs(owner_mail, situs):
            t.add("ownership:absentee")
        else:
            t.add("ownership:owner-occupied")
    if et in ("LLC", "COMMERCIAL"):
        t.add("ownership:investor")
    if et == "TRUST":
        t.add("ownership:trust-held")
    ps = card.get("portfolio_size") or 1
    if ps >= 2:
        t.add("ownership:portfolio-member")
    if ps >= 5:
        t.add("ownership:portfolio-large")
    if ps >= 15:
        t.add("ownership:portfolio-dominant")

    # ── permit / contractor / economic-activity ──────────────────────────
    if card.get("has_permit") or card.get("permit_count"):
        t.add("permit:active")
        t.add("economic-activity:construction")
        pc = card.get("permit_count") or 0
        if pc >= 2:
            t.add("permit:multiple")
        days = _days_since(card.get("last_permit_date"))
        if days is not None:
            if days <= 30:
                t.add("permit:last-30-days")
            if days <= 90:
                t.add("permit:last-90-days")
        pv = _num(card.get("permit_value_total"))
        if pv and pv >= 100_000:
            t.add("economic-activity:major-capital")
        for ct in (card.get("contractors") or []):
            if ct:
                t.add("contractor:named")
                break
    for trade in (card.get("trade_tags") or []):
        t.add(f"trade:{trade}")
        if trade in ("alarm", "security"):
            t.add("security:system")
    if not card.get("trade_tags"):
        t.add("trade:untagged")

    # ── real-estate / value ───────────────────────────────────────────────
    lu = (card.get("land_use") or "").lower()
    if any(k in lu for k in _RESIDENTIAL_USES):
        t.add("real-estate:residential")
    if any(k in lu for k in _COMMERCIAL_USES):
        t.add("real-estate:commercial")
    if any(k in lu for k in _VACANT_USES):
        t.add("real-estate:vacant-land")
    yb = card.get("year_built")
    try:
        yb = int(str(yb)[:4]) if yb else None
    except (ValueError, TypeError):
        yb = None
    if yb:
        age = dt.datetime.utcnow().year - yb
        if age >= 40:
            t.add("real-estate:aging-structure-40yr")
        elif age >= 20:
            t.add("real-estate:mature-structure-20yr")
        elif age <= 3:
            t.add("real-estate:new-construction")
    if str(card.get("pool")).strip().lower() in ("yes", "y", "true", "1", "pool"):
        t.add("real-estate:has-pool")

    val = _num(card.get("assessed_value"))
    if val is not None:
        if val >= 1_000_000:
            t.add("value:1m-plus")
        elif val >= 750_000:
            t.add("value:750k-1m")
        elif val >= 400_000:
            t.add("value:400k-750k")
        elif val >= 200_000:
            t.add("value:200k-400k")
        else:
            t.add("value:under-200k")

    # ── temporal (sale + freshest signal) ─────────────────────────────────
    ts = card.get("temporal_state")
    if ts:
        t.add(f"temporal:{ts.lower()}")
    sm = _months_since(card.get("last_sale_date"))
    if sm is not None and sm <= 12:
        t.add("real-estate:recent-sale")

    # ── geographic ────────────────────────────────────────────────────────
    city = (card.get("city") or card.get("situs_city") or "").strip().upper()
    juris = _JURIS.get(city)
    if juris:
        t.add(f"geo:{juris}")
    elif city and city not in ("ASSESSOR DESCRIPTION",):
        t.add("geo:other")
    if card.get("lat") and card.get("lng"):
        t.add("geo:mapped")
    else:
        t.add("geo:unmapped")
    cd = card.get("cluster_density") or 0
    if cd >= 10:
        t.add("geo:dense-cluster")
    elif cd >= 4:
        t.add("geo:cluster")

    # ── owner origin / capital flow (mailing geography, NOT property loc) ──
    o_state = card.get("owner_state")
    if o_state:
        if card.get("owner_is_local") or o_state == "NV":
            t.add("origin:local-nv")
        if card.get("owner_out_of_state"):
            t.add("origin:out-of-state")
            from .capital import _STATE_NAME
            slug = _STATE_NAME.get(o_state, o_state).lower().replace(" ", "-")
            t.add(f"origin:{slug}")

    # ── urgency (date-first, v0.106) -- derived from the freshest event age ──
    u = card.get("urgency")
    if u:
        t.add(f"urgency:{u}")
    ad = card.get("age_days")
    if isinstance(ad, int):
        if ad <= 1:
            t.add("urgency:today")
        elif ad <= 7:
            t.add("urgency:this-week")
        elif ad <= 30:
            t.add("urgency:this-month")

    # ── jurisdiction (property jurisdiction, searchable/exportable) ─────────
    pj = card.get("property_jurisdiction")
    if pj:
        t.add("jurisdiction:" + pj.lower().replace(" ", "-"))

    # ── distress (REAL events only -- never inferred) ─────────────────────
    for ev in (card.get("timeline") or []):
        kind = (ev.get("kind") or "").upper()
        desc = (ev.get("description") or "").lower()
        if kind == "VIOLATION":
            t.add("distress:code-violation")
        if kind == "BUSINESS_LICENSE":
            t.add("signal:business-license")
        if kind == "CRIME":
            t.add("signal:crime-area")
        if "notice of default" in desc or "nod" in desc:
            t.add("distress:notice-of-default")
        if "trustee" in desc or "foreclos" in desc:
            t.add("distress:foreclosure-track")
        if "lien" in desc:
            t.add("distress:lien")
    # 0.109 free-saturation flags (set from real source records)
    if card.get("code_enforcement_open"):
        t.add("distress:code-enforcement-open")
        t.add("signal:code-enforcement")
    elif card.get("distress_signal") == "code-enforcement":
        t.add("signal:code-enforcement")
    if card.get("business_license_active"):
        t.add("signal:business-license")
    # 0.111 permit-derived signal families (from real permit records)
    from .signals import DISPLAY as _SIGDISP
    for k in (card.get("permit_signals") or []):
        t.add("signal:" + k.replace("_", "-"))

    # ── monetization readiness (derived heuristics, clearly tags not facts)
    #    each requires a real supporting field; absence => no tag.
    if "real-estate:aging-structure-40yr" in t and "trade:roofing" not in t:
        t.add("monetization:roof-age-candidate")
    if yb and (dt.datetime.utcnow().year - yb) >= 15 and "trade:solar" not in t \
            and "real-estate:residential" in t:
        t.add("monetization:solar-candidate")
    if "ownership:absentee" in t and "ownership:investor" in t:
        t.add("monetization:investor-relationship")
    if val is not None and val >= 750_000:
        t.add("monetization:high-value")
    if "permit:last-90-days" in t:
        t.add("monetization:active-spender")

    return sorted(t)


# Human-readable labels for tag namespaces (used by the console facet UI).
NAMESPACE_LABELS = {
    "trade": "Trade", "entity": "Entity", "ownership": "Ownership",
    "permit": "Permit", "real-estate": "Real Estate", "value": "Value",
    "temporal": "Recency", "geo": "Geography", "distress": "Distress",
    "security": "Security", "economic-activity": "Economic Activity",
    "monetization": "Monetization", "contractor": "Contractor",
    "origin": "Owner Origin", "urgency": "Urgency", "jurisdiction": "Jurisdiction",
}
