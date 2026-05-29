"""
GRIT events — event-driven acquisition intelligence (Alpha 0.101).

Per the mission directive, GRIT is NOT a CRM and NOT a contractor portal --
it's an event-driven acquisition intelligence system. Events are the core
signal: a permit pulled, a deed recorded, a license issued, a violation cited,
an LLC registered. Each event is timestamped, geocoded, and joined to a parcel,
which is how it lights up a lead.

This module defines the event contract. Concrete event SOURCES (permits.py,
deeds.py, etc.) are added one at a time as ingestion is built out -- each one
captures real data only, never fabricated.
"""
import dataclasses as dc
import datetime as dt
import json
import os
from typing import Optional, Dict, Any, List

from . import config

EVENTS_FILE = os.path.join(config.DATA_DIR, "events.json")

# Recognized event kinds (the full Alpha 0.101 priority list)
KINDS = (
    "PERMIT",           # building / trade permit pulled
    "DEED",             # recorded sale / quitclaim
    "LICENSE_NEW",      # new contractor license
    "VIOLATION",        # code enforcement / nuisance
    "LLC_REGISTRATION", # new business entity tied to address
    "REVIEW_SPIKE",     # surge in complaints / reviews
    "SERVICE_REQUEST",  # public service request (311-style)
)


@dc.dataclass
class Event:
    kind: str                         # one of KINDS
    date: str                         # ISO date the event happened
    source: str                       # source key (e.g. 'accela_clark')
    parcel_apn: Optional[str] = None  # join key onto cards
    address: Optional[str] = None
    description: Optional[str] = ""
    trade_tag: Optional[str] = None   # e.g. 'roofing' inferred from permit type
    lat: Optional[float] = None
    lng: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None  # provenance


def _norm_addr(s):
    """Normalize a street address to its leading 'number street' portion for
    joining. Permit addresses carry city/state/zip; assessor situs is often
    street-only -- so we key on the street segment before the city."""
    if not s:
        return ""
    import re as _re
    a = str(s).split(",")[0]                      # drop ', CITY ST ZIP' tail
    a = " " + a.upper() + " "
    a = a.replace(",", " ").replace(".", " ")
    a = _re.sub(r"\b(APT|UNIT|STE|SUITE|#)\s*\S+", " ", a)
    a = _re.sub(r"\b(STREET|AVENUE|BOULEVARD|ROAD|DRIVE|LANE|COURT|PARKWAY|"
                r"HIGHWAY|PLACE|CIRCLE|TERRACE)\b",
                lambda m: {"STREET":"ST","AVENUE":"AVE","BOULEVARD":"BLVD",
                           "ROAD":"RD","DRIVE":"DR","LANE":"LN","COURT":"CT",
                           "PARKWAY":"PKWY","HIGHWAY":"HWY","PLACE":"PL",
                           "CIRCLE":"CIR","TERRACE":"TER"}.get(m.group(0), m.group(0)), a)
    a = _re.sub(r"\b[A-Z]{2}\s+\d{5}(-\d{4})?\b", " ", a)     # ST ZIP
    a = _re.sub(r"\b\d{5}(-\d{4})?\b", " ", a)                # bare ZIP
    # strip a trailing Clark County city if no comma delimited it out
    a = _re.sub(r"\s+(NORTH LAS VEGAS|LAS VEGAS|HENDERSON|BOULDER CITY|MESQUITE|"
                r"ENTERPRISE|SPRING VALLEY|SUNRISE MANOR|PARADISE|WHITNEY|"
                r"SUMMERLIN|NV|NEVADA)\s*$", " ", a)
    return _re.sub(r"\s+", " ", a).strip()


def _norm_apn(apn):
    return "".join(ch for ch in str(apn or "") if ch.isdigit())


def join_to_cards(cards: List[dict], events: List[Event]):
    """Attach events to cards by parcel APN OR normalized situs address. Mutates
    cards in place. Only real harvested events are ever joined; no synthetic
    activity. APNs are matched digit-only (parcel layers use dashes, permit
    PRCLIDs don't), and every event is indexed by BOTH apn and address so a
    format mismatch on one still joins on the other."""
    by_apn, by_addr = {}, {}
    for e in events:
        d = dc.asdict(e)
        ak = _norm_apn(e.parcel_apn)
        if ak:
            by_apn.setdefault(ak, []).append(d)
        adk = _norm_addr(e.address)
        if adk:
            by_addr.setdefault(adk, []).append(d)
    for c in cards:
        hits, seen = [], set()
        for bucket, key in ((by_apn, _norm_apn(c.get("parcel_apn"))),
                            (by_addr, _norm_addr(c.get("situs_address")))):
            if key and key in bucket:
                for d in bucket[key]:
                    sig = (d.get("kind"), d.get("date"), d.get("description"))
                    if sig not in seen:        # don't double-count an event matched by both apn+addr
                        seen.add(sig)
                        hits.append(d)
        if hits:
            c["timeline"] = sorted(hits, key=lambda x: x.get("date", ""), reverse=True)


def write(events: List[Event], path: str = EVENTS_FILE):
    """Persist the events feed for the console. Empty list is valid."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kinds_supported": list(KINDS),
        "count": len(events),
        "events": [dc.asdict(e) for e in events],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)


def load_existing(path: str = EVENTS_FILE) -> List[Event]:
    """Load previously harvested events (so a sparse harvest doesn't lose history)."""
    try:
        with open(path) as f:
            data = json.load(f)
        return [Event(**{k: v for k, v in e.items() if k in Event.__annotations__})
                for e in data.get("events", [])]
    except Exception:
        return []
