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


def join_to_cards(cards: List[dict], events: List[Event]):
    """Attach events to cards by parcel APN. Mutates cards in place.
    Only real harvested events are ever joined; no synthetic activity."""
    by_apn = {}
    for e in events:
        if e.parcel_apn:
            by_apn.setdefault(e.parcel_apn, []).append(dc.asdict(e))
    for c in cards:
        apn = c.get("parcel_apn")
        if apn and apn in by_apn:
            c["timeline"] = sorted(by_apn[apn], key=lambda x: x.get("date", ""),
                                   reverse=True)


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
