"""
Capital-flow intelligence (Alpha 0.105).

Four location dimensions are kept strictly separate -- collapsing them loses
intelligence:

  * property location   -- where the parcel physically sits (plots on the map)
  * permit jurisdiction -- the authority that issued the permit
  * owner mailing geo   -- where the owner receives mail (absentee signal)
  * capital origin      -- the market the ownership capital appears to come from

A Las Vegas parcel owned by a Chicago mailing address STILL plots in Las Vegas.
Chicago is never a map coordinate -- it is an *ownership* fact. This module
turns the owner mailing string into structured origin fields and rolls them up
into a capital-flow view: which out-of-market money is buying into Southern
Nevada, how much, and where it lands.

Everything here is derived from real harvested mailing addresses. No invented
locations: a card with no mailing address simply has no origin.
"""
import re

# Two-letter state -> full name, for nicer origin-market labels.
_STATE_NAME = {
    "NV": "Nevada", "CA": "California", "AZ": "Arizona", "UT": "Utah",
    "TX": "Texas", "IL": "Illinois", "NY": "New York", "FL": "Florida",
    "WA": "Washington", "CO": "Colorado", "OR": "Oregon", "ID": "Idaho",
    "MI": "Michigan", "IN": "Indiana", "OH": "Ohio", "GA": "Georgia",
    "NJ": "New Jersey", "MA": "Massachusetts", "PA": "Pennsylvania",
    "MN": "Minnesota", "MD": "Maryland", "VA": "Virginia", "NC": "North Carolina",
    "TN": "Tennessee", "MO": "Missouri", "WI": "Wisconsin", "HI": "Hawaii",
    "DC": "District of Columbia", "CT": "Connecticut", "NM": "New Mexico",
    "AR": "Arkansas", "KS": "Kansas", "OK": "Oklahoma", "IA": "Iowa",
    "KY": "Kentucky", "LA": "Louisiana", "AL": "Alabama", "SC": "South Carolina",
    "MS": "Mississippi", "NE": "Nebraska", "WV": "West Virginia", "MT": "Montana",
    "RI": "Rhode Island", "ME": "Maine", "NH": "New Hampshire", "SD": "South Dakota",
    "ND": "North Dakota", "WY": "Wyoming", "VT": "Vermont", "DE": "Delaware",
    "AK": "Alaska",
}

# Southern Nevada cities count as LOCAL capital, not imported.
_LOCAL_NV_CITIES = {
    "LAS VEGAS", "NORTH LAS VEGAS", "HENDERSON", "BOULDER CITY", "ENTERPRISE",
    "SPRING VALLEY", "SUNRISE MANOR", "PARADISE", "WHITNEY", "SUMMERLIN",
    "MESQUITE", "MOAPA", "MOAPA VALLEY", "SEARCHLIGHT", "LAUGHLIN", "JEAN",
    "BLUE DIAMOND", "INDIAN SPRINGS", "LOGANDALE", "OVERTON", "PAHRUMP",
    "NELLIS AFB", "THE LAKES",
}

# Pull 'CITY ST 89123' out of a mailing tail. City may be multi-word
# (LOS ANGELES, SALT LAKE CITY); state is two letters; zip is 5 (+4 optional).
_TAIL = re.compile(r"^(.*?)[ ,]+([A-Z]{2})[ ,]+(\d{5})(?:-\d{4})?\s*$")


def _titlecase(city):
    fixups = {"Po Box": "PO Box"}
    t = " ".join(w.capitalize() for w in city.split())
    return fixups.get(t, t)


def parse_owner_origin(mailing):
    """owner_mailing string -> {owner_city, owner_state, owner_zip,
    owner_origin_market, owner_is_local, owner_out_of_state}. Returns {} when
    no usable city/state can be read (never guesses)."""
    if not mailing or not isinstance(mailing, str):
        return {}
    # The mailing is usually 'STREET, CITY ST ZIP'; trust the part after the
    # last comma for the city so a comma-less street token isn't mistaken for it.
    seg = mailing.split(",")[-1].strip()
    m = _TAIL.match(seg)
    if not m:
        # whole-string fallback (some mailings omit the street comma)
        m = _TAIL.match(mailing.strip())
        if not m:
            return {}
    city_raw, state, zc = m.group(1).strip().upper(), m.group(2), m.group(3)
    if not city_raw:
        return {}
    city_disp = _titlecase(city_raw)
    is_local = (state == "NV" and city_raw in _LOCAL_NV_CITIES)
    return {
        "owner_city": city_disp,
        "owner_state": state,
        "owner_zip": zc,
        "owner_origin_market": f"{city_disp}, {state}",
        "owner_is_local": is_local,
        "owner_out_of_state": state != "NV",
    }


def stamp_owner_origin(card):
    """Attach owner-origin fields to a card from its mailing address. Mutates
    and returns the card. Never touches property location or coordinates."""
    info = parse_owner_origin(card.get("owner_mailing"))
    for k, v in info.items():
        card[k] = v
    return card


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def capital_flow(cards, top=25):
    """Roll owner-origin fields up into a capital-flow view.

    Returns:
      by_market   -- every origin market ranked by property count, with permit
                     count, valuation total, distinct owners, and the Southern
                     Nevada destinations that money lands in
      by_state    -- origin states ranked (NV = local)
      imported    -- the out-of-state subset (the investor-migration signal)
      flows       -- origin_market -> destination_jurisdiction edges
      totals      -- coverage + local-vs-imported split
    """
    markets, states, flows = {}, {}, {}
    owners_by_market = {}
    n_total = len(cards)
    n_with_origin = 0
    imported_props = 0

    for c in cards:
        mk = c.get("owner_origin_market")
        st = c.get("owner_state")
        if not mk or not st:
            continue
        n_with_origin += 1
        out_of_state = bool(c.get("owner_out_of_state"))
        if out_of_state:
            imported_props += 1
        val = _num(c.get("assessed_value")) + _num(c.get("permit_value_total"))
        permitted = 1 if (c.get("has_permit") or c.get("permit_count")) else 0
        dest = c.get("jurisdiction") or "Unknown"

        b = markets.setdefault(mk, {
            "market": mk, "state": st, "out_of_state": out_of_state,
            "properties": 0, "permits": 0, "valuation_total": 0.0,
            "destinations": {}})
        b["properties"] += 1
        b["permits"] += permitted
        b["valuation_total"] += val
        b["destinations"][dest] = b["destinations"].get(dest, 0) + 1
        owners_by_market.setdefault(mk, set()).add(
            (c.get("owner_name") or "").strip().upper() or c.get("id"))

        s = states.setdefault(st, {
            "state": st, "name": _STATE_NAME.get(st, st), "out_of_state": st != "NV",
            "properties": 0, "permits": 0, "valuation_total": 0.0, "markets": set()})
        s["properties"] += 1
        s["permits"] += permitted
        s["valuation_total"] += val
        s["markets"].add(mk)

        ek = (mk, dest)
        f = flows.setdefault(ek, {"origin": mk, "destination": dest,
                                  "origin_state": st, "properties": 0})
        f["properties"] += 1

    market_rows = []
    for mk, b in markets.items():
        b["owners"] = len(owners_by_market.get(mk, ()))
        b["valuation_total"] = round(b["valuation_total"])
        b["destinations"] = sorted(
            ({"jurisdiction": k, "properties": v} for k, v in b["destinations"].items()),
            key=lambda x: x["properties"], reverse=True)
        market_rows.append(b)
    market_rows.sort(key=lambda r: (r["properties"], r["valuation_total"]), reverse=True)

    state_rows = []
    for st, s in states.items():
        s["markets"] = len(s["markets"])
        s["valuation_total"] = round(s["valuation_total"])
        state_rows.append(s)
    state_rows.sort(key=lambda r: r["properties"], reverse=True)

    imported = [r for r in market_rows if r["out_of_state"]]
    flow_rows = sorted(flows.values(), key=lambda r: r["properties"], reverse=True)
    imported_flows = [f for f in flow_rows
                      if next((m["out_of_state"] for m in market_rows
                               if m["market"] == f["origin"]), False)]

    return {
        "by_market": market_rows[:top],
        "by_state": state_rows,
        "imported": imported[:top],
        "imported_flows": imported_flows[:30],
        "totals": {
            "cards": n_total,
            "with_origin": n_with_origin,
            "origin_coverage_pct": round(100 * n_with_origin / n_total, 1) if n_total else 0.0,
            "distinct_markets": len(markets),
            "distinct_states": len(states),
            "out_of_state_markets": len(imported),
            "local_properties": n_with_origin - imported_props,
            "imported_properties": imported_props,
            "imported_pct": round(100 * imported_props / n_with_origin, 1) if n_with_origin else 0.0,
            "imported_valuation": round(sum(r["valuation_total"] for r in imported)),
        },
    }


def ownership_coverage(cards):
    """Coverage of the ownership-intelligence layer for the health matrix:
    mailing city/state, absentee, trust + LLC detection. Percentages over the
    full card set, computed from real fields only."""
    n = len(cards) or 1
    have_mail = sum(1 for c in cards if c.get("owner_mailing"))
    have_city = sum(1 for c in cards if c.get("owner_city"))
    have_state = sum(1 for c in cards if c.get("owner_state"))
    # absentee = mailing present and differs from situs (occupancy_status set)
    occ = [c for c in cards if c.get("occupancy_status")]
    absentee = sum(1 for c in occ if str(c.get("occupancy_status", "")).startswith("Absentee"))
    et = lambda c: (c.get("entity_type") or "").upper()
    llc = sum(1 for c in cards if et(c) in ("LLC", "COMMERCIAL"))
    trust = sum(1 for c in cards if et(c) == "TRUST")
    out_of_state = sum(1 for c in cards if c.get("owner_out_of_state"))
    return {
        "mailing_pct": round(100 * have_mail / n, 1),
        "mailing_city_pct": round(100 * have_city / n, 1),
        "mailing_state_pct": round(100 * have_state / n, 1),
        "absentee": absentee,
        "absentee_pct": round(100 * absentee / (len(occ) or 1), 1),
        "llc": llc, "llc_pct": round(100 * llc / n, 1),
        "trust": trust, "trust_pct": round(100 * trust / n, 1),
        "out_of_state_owners": out_of_state,
        "out_of_state_pct": round(100 * out_of_state / n, 1),
    }
