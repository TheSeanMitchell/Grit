"""
Permit-derived signal classification (Alpha 0.111).

Every lead card already carries its permit history (CLV + Henderson). Those
permits encode far more signal than "a permit happened": a barricade permit is
Public Works, a fire-sprinkler permit is life-safety, a tract dwelling is new
construction, a grading permit is pre-construction development. This module reads
the REAL permit descriptions on a card and tags the signal families present.

No new data source -- this is pure classification of records we already hold, so
it is fully verifiable offline and adds zero fabrication risk. Patterns were
derived from the actual harvested permit corpus (counts in the 0.111 audit).
"""
import re

# signal_key -> (display name, [regex patterns matched against permit text])
PERMIT_SIGNALS = {
    "public_works":        ("Public Works",
                            [r"\bpw\b", r"barricade", r"civil improv", r"right.of.way",
                             r"encroach", r"\brow\b", r"public works"]),
    "fire_life_safety":    ("Security Signals",
                            [r"\bfire\b", r"suppress", r"sprinkler", r"alarm",
                             r"hazard", r"haz mat", r"life safety", r"extinguish"]),
    "demolition":          ("Demolitions",
                            [r"demolition", r"\bdemo\b", r"wreck", r"tear.?down", r"raze"]),
    "commercial_ti":       ("Commercial Tenant Improvements",
                            [r"tenant improv", r"\bt\.?i\.?\b", r"build.?out",
                             r"commercial.*(alter|remodel|interior|tenant|build)"]),
    "certificate_of_occupancy": ("Certificates of Occupancy",
                            [r"occupancy", r"\bcofo\b", r"\bc of o\b", r"certificate of occ"]),
    "new_construction":    ("New Construction",
                            [r"\bsfd\b", r"\bsfr\b", r"dwelling", r"\btract\b",
                             r"new (home|residence|construction|dwelling|building)",
                             r"production", r"townhouse", r"single fam"]),
    "grading_site":        ("Grading / Site Work",
                            [r"grading", r"\bgrade\b", r"excavat", r"site work",
                             r"earthwork", r"\brough grade\b"]),
    "telecom_infrastructure": ("Telecom / Infrastructure",
                            [r"cell tower", r"antenna", r"small cell", r"telecom",
                             r"\bwireless\b", r"monopole"]),
    "solar":               ("Solar Activity",
                            [r"photovolt", r"\bpv\b", r"\bsolar\b"]),
    "pool_spa":            ("Pool / Spa",
                            [r"\bpool\b", r"\bspa\b"]),
    "roofing":             ("Roofing", [r"\broof"]),
}

_COMPILED = {k: (name, [re.compile(p) for p in pats]) for k, (name, pats) in PERMIT_SIGNALS.items()}

# signal_key -> display name (for the matrix / UI)
DISPLAY = {k: name for k, (name, _) in PERMIT_SIGNALS.items()}


def _permit_text(card):
    """All permit-ish text on a card: timeline permit descriptions + type + trades."""
    parts = []
    for e in (card.get("timeline") or []):
        if (e.get("kind") or "").upper() == "PERMIT":
            parts.append((e.get("description") or "").lower())
    for t in (card.get("trade_tags") or []):
        parts.append(str(t).lower())
    if card.get("permit_type"):
        parts.append(str(card["permit_type"]).lower())
    return " | ".join(p for p in parts if p)


def classify(card):
    """Set card['permit_signals'] to the list of signal keys present (from REAL
    permit records). Returns that list. Idempotent."""
    text = _permit_text(card)
    found = []
    if text:
        for key, (_, regexes) in _COMPILED.items():
            if any(rx.search(text) for rx in regexes):
                found.append(key)
    card["permit_signals"] = found
    return found


def counts(cards):
    """{signal_key: number of cards carrying it} across the warehouse."""
    out = {k: 0 for k in PERMIT_SIGNALS}
    for c in cards:
        for k in (c.get("permit_signals") or []):
            out[k] = out.get(k, 0) + 1
    return out
