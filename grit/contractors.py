"""
Contractor intelligence (Alpha 0.105, roadmap Phase 8).

Track: contractor frequency, contractor dominance, trade share, geographic
dominance, recent activity. Build a contractor leaderboard.

The signal: a contractor who pulls permits constantly is (a) a buyer for the
operator's services and (b) a tell for where money is moving. This module rolls
the permit-bearing leads up by contractor and computes who is active, in which
trades, in which jurisdictions, and how dominant they are -- all from real
harvested permit fields. No fabricated contractors; a contractor appears only if
a real permit named them.
"""
import collections
import datetime as dt


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _days_since(date_val):
    if not date_val:
        return None
    try:
        d = dt.datetime.strptime(str(date_val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (dt.date.today() - d).days


def _clean_name(n):
    return " ".join(str(n).split()).strip() if n else None


def build_contractor_table(cards, recent_days=90):
    """Roll permit-bearing cards up by contractor. Returns the leaderboard list
    (sorted by composite activity score). Also computes trade share + geographic
    dominance against the global permit population."""
    # global denominators for "dominance" (share of all permits in a trade / city)
    trade_totals = collections.Counter()
    city_totals = collections.Counter()
    for c in cards:
        if not (c.get("has_permit") or c.get("permit_count")):
            continue
        pc = int(c.get("permit_count") or 1)
        for tr in (c.get("trade_tags") or ["untagged"]):
            trade_totals[tr] += pc
        cty = (c.get("city") or c.get("situs_city") or "").strip().upper()
        if cty:
            city_totals[cty] += pc

    agg = {}
    for c in cards:
        contractors = [_clean_name(x) for x in (c.get("contractors") or []) if x]
        if not contractors:
            continue
        pc = int(c.get("permit_count") or 1)
        date = c.get("last_permit_date")
        days = _days_since(date)
        trades = c.get("trade_tags") or []
        city = (c.get("city") or c.get("situs_city") or "").strip().upper()
        pv = _num(c.get("permit_value_total")) or 0.0
        for name in contractors:
            a = agg.get(name)
            if a is None:
                a = {"name": name, "permit_count": 0, "job_sites": 0,
                     "trades": collections.Counter(), "cities": collections.Counter(),
                     "recent_count": 0, "value_total": 0.0,
                     "first_seen": None, "last_seen": None,
                     "sample_addresses": [], "license": None}
                agg[name] = a
            a["permit_count"] += pc
            a["job_sites"] += 1
            a["value_total"] += pv
            for tr in trades:
                a["trades"][tr] += pc
            if city:
                a["cities"][city] += pc
            if days is not None and days <= recent_days:
                a["recent_count"] += 1
            if date:
                if not a["last_seen"] or date > a["last_seen"]:
                    a["last_seen"] = date
                if not a["first_seen"] or date < a["first_seen"]:
                    a["first_seen"] = date
            if c.get("situs_address") and len(a["sample_addresses"]) < 5:
                a["sample_addresses"].append(c["situs_address"])

    out = []
    for name, a in agg.items():
        top_trade, top_trade_n = (a["trades"].most_common(1) or [(None, 0)])[0]
        top_city, top_city_n = (a["cities"].most_common(1) or [(None, 0)])[0]
        trade_share = round(100 * top_trade_n / trade_totals[top_trade], 1) \
            if top_trade and trade_totals[top_trade] else 0.0
        geo_share = round(100 * top_city_n / city_totals[top_city], 1) \
            if top_city and city_totals[top_city] else 0.0
        # composite activity score: recency-weighted volume + trade dominance
        score = a["recent_count"] * 5 + min(a["permit_count"], 60) + int(trade_share / 10) \
            + int(a["value_total"] / 250_000)
        out.append({
            "name": name,
            "permit_count": a["permit_count"],
            "job_sites": a["job_sites"],
            "recent_count": a["recent_count"],
            "value_total": round(a["value_total"], 0),
            "trades": dict(a["trades"]),
            "top_trade": top_trade,
            "trade_share_pct": trade_share,
            "cities": dict(a["cities"]),
            "top_city": (top_city or "").title() or None,
            "geo_dominance_pct": geo_share,
            "first_seen": a["first_seen"],
            "last_seen": a["last_seen"],
            "sample_addresses": a["sample_addresses"],
            "score": score,
        })
    out.sort(key=lambda x: (x["recent_count"], x["permit_count"], x["score"]), reverse=True)
    return out
