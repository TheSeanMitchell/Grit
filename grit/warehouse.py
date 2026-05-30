"""
Append-only per-record warehouse (Alpha 0.106).

The ledger records one row per harvest (headline counts). This adds the layer
the v0.106 directive asks for: a per-RECORD history so the warehouse can answer
"when did we first see this property / permit, when did we last see it, and has
its state changed." History is a feature -- records are never deleted; a record
that drops out of a later harvest keeps its last_seen and is marked dormant.

Stored at docs/data/warehouse/records.json keyed by stable card id. On the first
run the store initializes (first_seen = last_seen = now); across subsequent
harvests first_seen stays put while last_seen / last_updated advance, so the
divergence -- and the warehouse's growth -- becomes real signal over time.

Nothing here is fabricated. first_seen/last_seen are GRIT's own observation
timestamps, kept distinct from a record's intrinsic event dates (permit issued,
sale closed), which the directive treats as separate facts.
"""
import json
import os
import hashlib
import datetime as dt

from . import config


def _now():
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    return dt.date.today().isoformat()


def _dir():
    d = getattr(config, "WAREHOUSE_DIR", os.path.join(config.DATA_DIR, "warehouse"))
    os.makedirs(d, exist_ok=True)
    return d


def _records_path():
    return os.path.join(_dir(), "records.json")


def load_records():
    try:
        with open(_records_path()) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"generated_at": None, "count": 0, "records": {}}


def _state_hash(card):
    """A small fingerprint of the fields whose change is meaningful, so we can
    tell when a record was genuinely updated vs merely re-observed."""
    parts = [str(card.get(k)) for k in (
        "score", "owner_name", "assessed_value", "permit_count",
        "last_permit_date", "last_sale_date", "occupancy_status",
        "property_jurisdiction")]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def update(cards):
    """Fold the current cards into the per-record store (append-only).

    Returns (store, stats). stats reports growth so the warehouse report can
    show new vs returning vs dormant records."""
    store = load_records()
    recs = store.get("records", {})
    now, today = _now(), _today()
    new_n = changed_n = seen_n = 0
    present = set()

    for c in cards:
        rid = c.get("id")
        if not rid:
            continue
        present.add(rid)
        h = _state_hash(c)
        r = recs.get(rid)
        if r is None:
            recs[rid] = {"first_seen": today, "last_seen": today,
                         "last_updated": today, "observations": 1, "state": h,
                         "kind": c.get("source")}
            new_n += 1
        else:
            r["last_seen"] = today
            r["observations"] = r.get("observations", 1) + 1
            if r.get("state") != h:
                r["state"] = h
                r["last_updated"] = today
                changed_n += 1
            else:
                seen_n += 1

    dormant = [rid for rid in recs if rid not in present]
    store.update({"generated_at": now, "count": len(recs), "records": recs})
    stats = {"tracked": len(recs), "new": new_n, "changed": changed_n,
             "returning": seen_n, "dormant": len(dormant),
             "first_run": store.get("count", 0) == new_n}
    return store, stats


def save(store):
    with open(_records_path(), "w") as f:
        json.dump(store, f, separators=(",", ":"))


def stamp(card, store):
    """Attach the warehouse observation dates to a card for display:
    first_seen, last_seen, last_updated. Mutates and returns the card."""
    r = (store.get("records") or {}).get(card.get("id"))
    if r:
        card["first_seen"] = r.get("first_seen")
        card["last_seen"] = r.get("last_seen")
        card["last_updated"] = r.get("last_updated")
        card["observations"] = r.get("observations")
    return card


def growth_series(ledger_entries):
    """Condense the harvest ledger into a clean growth series for the
    warehouse-growth report (deduped by day, key metrics only)."""
    out, seen = [], set()
    for e in ledger_entries or []:
        day = (e.get("at") or e.get("generated_at") or "")[:10]
        row = {"date": day, "leads": e.get("leads"), "mapped": e.get("mapped"),
               "permit_events": e.get("permit_events"),
               "contractors": e.get("contractors"),
               "imported_capital": e.get("imported_capital")}
        key = (day, row["leads"], row["permit_events"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
