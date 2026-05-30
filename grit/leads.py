"""
Sales-ready lead assembly (Alpha 0.105, roadmap Phase 5).

"Every lead card must include ... a human-readable explanation. Include WHY THIS
MATTERS, written for a brand-new sales representative."

Two jobs:
  1. enrich_lead(card)  -- guarantee the Phase-5 fields exist on the card
     (jurisdiction, property_type, occupancy_status, timeline_summary). Fields
     the data doesn't support stay null; nothing is invented.
  2. why_this_matters(card) -- a plain-English briefing assembled DETERMINISTICALLY
     from the card's real signals. No model call, no fabrication: every sentence
     restates a fact already on the card, in the order a rep should hear it
     (what's happening now -> who owns it -> how big -> what to do).

This is the opposite of black-box scoring: the score's signals[] explain the
NUMBER; this explains the OPPORTUNITY in language a new hire can act on.
"""
import datetime as dt

_TRADE_PHRASE = {
    "roofing": "a roofing job", "hvac": "an HVAC job", "solar": "a solar install",
    "plumbing": "plumbing work", "electrical": "electrical work",
    "pools": "a pool/spa project", "remodeling": "a remodel or addition",
    "fencing": "fencing or block-wall work", "concrete": "concrete/flatwork",
    "landscaping": "landscaping work", "security": "a security/low-voltage job",
    "sign": "signage work", "patio": "a patio project", "pest": "pest work",
}

_JURIS_LABEL = {
    "LAS VEGAS": "Las Vegas", "NORTH LAS VEGAS": "North Las Vegas",
    "HENDERSON": "Henderson", "BOULDER CITY": "Boulder City",
    "ENTERPRISE": "Enterprise", "SPRING VALLEY": "Spring Valley",
    "SUNRISE MANOR": "Sunrise Manor", "PARADISE": "Paradise",
    "WHITNEY": "Whitney", "SUMMERLIN": "Summerlin", "MESQUITE": "Mesquite",
    "MOAPA": "Moapa", "SEARCHLIGHT": "Searchlight", "LAUGHLIN": "Laughlin",
}


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _money(v):
    n = _num(v)
    if n is None:
        return None
    if n >= 1e6:
        return f"${n/1e6:.1f}M"
    if n >= 1e3:
        return f"${n/1e3:.0f}k"
    return f"${n:.0f}"


def _ago(date_val):
    """Human 'N days/weeks/months ago' from an ISO date. None if unparseable."""
    if not date_val:
        return None
    try:
        d = dt.datetime.strptime(str(date_val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    days = (dt.date.today() - d).days
    if days < 0:
        return None
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    if days < 730:
        return f"{days // 30} months ago"
    return f"{days // 365} years ago"


def jurisdiction(card):
    # City permit feeds carry the issuing authority as the jurisdiction. The CLV
    # feed's only city column is the OWNER's mailing city, so a property whose
    # owner mails from Chicago must not be labeled "Chicago" — every City of Las
    # Vegas permit is, by definition, for a property in the Las Vegas jurisdiction.
    if card.get("source") == "clv_permit":
        return "Las Vegas"
    city = (card.get("city") or card.get("situs_city") or "").strip().upper()
    return _JURIS_LABEL.get(city, city.title() if city and city != "ASSESSOR DESCRIPTION" else None)


def property_type(card):
    lu = (card.get("land_use") or "").lower()
    if any(k in lu for k in ("single family", "sfr")):
        return "Single-family residence"
    if "condo" in lu or "townhouse" in lu:
        return "Condo / townhouse"
    if any(k in lu for k in ("commercial", "retail", "office", "industrial", "warehouse")):
        return "Commercial property"
    if any(k in lu for k in ("vacant", "unimproved")):
        return "Vacant land"
    if "residential" in lu:
        return "Residential"
    return card.get("land_use") or None


def occupancy_status(card):
    mail, situs = card.get("owner_mailing"), card.get("situs_address")
    if mail and situs:
        from .pipeline import _addr_differs
        return "Absentee owner (mailing differs from property)" if _addr_differs(mail, situs) \
            else "Owner-occupied (mails to the property)"
    return None


def timeline_summary(card):
    tl = card.get("timeline") or []
    if not tl:
        return None
    kinds = {}
    for e in tl:
        kinds[e.get("kind", "?")] = kinds.get(e.get("kind", "?"), 0) + 1
    newest = max((e.get("date") for e in tl if e.get("date")), default=None)
    parts = ", ".join(f"{v} {k.lower()}" + ("s" if v > 1 else "") for k, v in kinds.items())
    return f"{parts}" + (f"; most recent {newest}" if newest else "")


def _parse(date_val):
    try:
        return dt.datetime.strptime(str(date_val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def stamp_dates(card):
    """Date-first display fields (v0.106 Rule 2). Surfaces the freshest
    meaningful EVENT date, its kind, age in days, a human 'ago', and an urgency
    tier -- so a card never makes you hunt for time. Event dates are the
    record's own facts and stay distinct from warehouse first/last-seen."""
    cand = []
    if card.get("last_permit_date"):
        cand.append(("permit", card["last_permit_date"]))
    if card.get("last_sale_date"):
        cand.append(("sale", card["last_sale_date"]))
    for e in (card.get("timeline") or []):
        if e.get("date"):
            cand.append(((e.get("kind") or "event").lower(), e["date"]))
    best = None
    for kind, dv in cand:
        d = _parse(dv)
        if d and (best is None or d > best[0]):
            best = (d, kind, dv)
    if best:
        age = (dt.date.today() - best[0]).days
        card["primary_date"] = str(best[2])[:10]
        card["primary_date_kind"] = best[1]
        card["primary_ago"] = _ago(best[2])
        card["age_days"] = age if age >= 0 else None
        card["urgency"] = ("hot" if age <= 7 else "warm" if age <= 30
                           else "recent" if age <= 90 else "aging" if age <= 365 else "stale")
    if not card.get("harvested_at"):
        card["harvested_at"] = card.get("last_seen")
    return card


def why_this_matters(card):
    """A 2-4 sentence briefing for a brand-new rep. Deterministic; real signals
    only, ordered: active work -> owner -> scale/value -> the play."""
    s = []

    # 1) what's happening right now (permits are the strongest 'act now' flag)
    if card.get("has_permit") or card.get("permit_count"):
        trades = card.get("trade_tags") or []
        phrase = _TRADE_PHRASE.get(trades[0]) if trades else None
        phrase = phrase or "a building permit"
        ago = _ago(card.get("last_permit_date"))
        ct = (card.get("contractors") or [None])[0]
        pc = card.get("permit_count") or 1
        line = f"This property has {phrase}"
        if ago:
            # "a building permit" reads as 'pulled'; trade jobs read as 'permitted'
            verb = "pulled" if "permit" in phrase else "permitted"
            line += f" {verb} {ago}"
        if ct:
            line += f" by {ct}"
        line += " — active work is happening here"
        if pc >= 2:
            line += f", and it's pulled {pc} permits"
        line += "."
        s.append(line)
        pv = _money(card.get("permit_value_total"))
        if pv and _num(card.get("permit_value_total")):
            s.append(f"Declared job value so far is {pv}.")

    # 2) who owns it
    et = (card.get("entity_type") or "").upper()
    owner = card.get("owner_name")
    occ = occupancy_status(card)
    absentee = occ and occ.startswith("Absentee")
    if owner:
        if et in ("LLC", "COMMERCIAL"):
            s.append(f"It's owned by {owner}, a business entity"
                     + (" mailing out of a different address — an investor profile that reinvests in property."
                        if absentee else "."))
        elif et == "TRUST":
            s.append(f"Title is held in a trust ({owner})"
                     + (" with off-site mailing." if absentee else "."))
        else:
            s.append(f"The owner of record is {owner}"
                     + (" and mails elsewhere, so they're likely a landlord or absentee owner."
                        if absentee else "."))

    # 2b) where the capital comes from (out-of-state = investor-migration signal)
    if card.get("owner_out_of_state") and card.get("owner_origin_market"):
        s.append(f"The owner mails from {card['owner_origin_market']} — out-of-state "
                 f"capital buying into the valley, so expect a manager or remote decision-maker.")

    # 3) scale / portfolio / value
    ps = card.get("portfolio_size") or 1
    if ps >= 2:
        s.append(f"This owner controls {ps} parcels in the metro — worth working as a "
                 f"relationship, not a one-off.")
    val = _money(card.get("assessed_value"))
    if val and card.get("vintage") == "current":
        s.append(f"Current assessed value is {val}.")
    elif val:
        s.append(f"Assessed value is {val}.")
    cd = card.get("cluster_density") or 0
    if cd >= 4:
        s.append(f"There are {cd} comparable leads within 500m — good route density for a day of door-knocks.")

    # 4) the play
    act = card.get("suggested_action")
    if act:
        s.append(act if act.endswith(".") else act + ".")

    if not s:
        s.append("Limited data on this parcel so far — enrich the owner and contact "
                 "before any outreach.")
    return " ".join(s)


def enrich_lead(card):
    """Attach the Phase-5 lead-card fields + the WHY THIS MATTERS briefing,
    and the four SEPARATE location dimensions (property / permit-jurisdiction /
    owner-mailing / capital-origin). Mutates and returns the card."""
    from . import capital, geo
    # CLV permit cards stored the owner's mailing city as situs_city (feed
    # quirk). The site sits in the issuing jurisdiction, so correct the
    # PROPERTY city -- but the owner mailing geography is preserved untouched
    # in owner_mailing and surfaced below as its own dimension.
    if card.get("source") == "clv_permit":
        card["situs_city"] = "LAS VEGAS"
        card["city"] = "LAS VEGAS"
    # permit jurisdiction = issuing authority. CLV is currently the only live
    # permit feed, so any card carrying permit events was permitted by the City.
    if card.get("has_permit") or card.get("permit_count"):
        card["permit_jurisdiction"] = "City of Las Vegas"
    # property jurisdiction resolved from the most authoritative field, with the
    # method recorded (jurisdiction_source); coordinate-derived labels are flagged.
    geo.stamp(card)
    # explicit dimension fields (kept distinct on purpose; never collapsed)
    card["property_city"] = card.get("situs_city") or card.get("city")
    if (not card.get("property_city") or card.get("property_city") == "ASSESSOR DESCRIPTION") \
            and card.get("property_jurisdiction"):
        card["property_city"] = card["property_jurisdiction"]
    capital.stamp_owner_origin(card)        # owner_city/state/zip + origin market
    card["property_type"] = property_type(card)
    card["occupancy_status"] = occupancy_status(card)
    stamp_dates(card)                       # date-first display fields
    card["timeline_summary"] = timeline_summary(card)
    card["why"] = why_this_matters(card)
    return card
