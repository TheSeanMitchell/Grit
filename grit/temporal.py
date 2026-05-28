"""
Multi-layer temporal intelligence (Phase 0.103 directive).

Rejects the binary "fresh vs. stale" model. A 1-year-old roof permit is not
worthless -- it suggests solar-readiness, recent capital deployment, and a
spending-prone homeowner. Signals decay in urgency, not in monetizable value.

Five layers, each with its own monetization profile and weight:

    IMMEDIATE   <= 3 mo     active project right now
    WARM        3-12 mo     recent investment behavior; solar/refi candidate
    PERSISTENT  1-3 yr      ongoing ownership pattern; renovation propensity
    HISTORICAL  3-10 yr     trend / forecasting context
    STRUCTURAL  > 10 yr     long-term behavioral baseline

Each layer keeps a base score floor + a multiplier when stacked with other
signals (a STRUCTURAL sale that ALSO sits in a portfolio cluster is still
valuable; an IMMEDIATE sale alone is the strongest pure-recency signal).
"""
import datetime as dt
from typing import Optional


STATES = ("IMMEDIATE", "WARM", "PERSISTENT", "HISTORICAL", "STRUCTURAL")

# (state, max_months_inclusive). order matters.
_BUCKETS = (
    ("IMMEDIATE",  3),
    ("WARM",       12),
    ("PERSISTENT", 36),
    ("HISTORICAL", 120),
    ("STRUCTURAL", None),   # > 10y
)

# Per-state score contribution for a sale-date signal. IMMEDIATE dominates
# but older states still carry weight (the directive's "old != dead" rule).
SALE_WEIGHT = {
    "IMMEDIATE":  25,
    "WARM":       16,
    "PERSISTENT": 10,
    "HISTORICAL": 5,
    "STRUCTURAL": 2,
}

# Per-state weight for permit-style events (when permit ingestion lands).
PERMIT_WEIGHT = {
    "IMMEDIATE":  30,
    "WARM":       18,
    "PERSISTENT": 10,
    "HISTORICAL": 4,
    "STRUCTURAL": 1,
}


def months_since(date_val) -> Optional[int]:
    """Months between `date_val` (ISO date / 'YYYY-MM' / epoch ms) and now.
    Returns None on unparseable input -- never raises, never fabricates."""
    if date_val in (None, "", " "):
        return None
    try:
        if isinstance(date_val, (int, float)) and date_val > 1e10:
            d = dt.datetime.utcfromtimestamp(date_val / 1000)
        else:
            s = str(date_val)[:10]
            if len(s) == 7 and s[4] == "-":
                s += "-01"
            d = dt.datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, OverflowError, OSError, TypeError):
        return None
    now = dt.datetime.utcnow()
    return (now.year - d.year) * 12 + (now.month - d.month)


def classify(date_val) -> Optional[str]:
    """Return the temporal state for `date_val`, or None if unparseable."""
    m = months_since(date_val)
    if m is None or m < 0:
        return None
    for state, cap in _BUCKETS:
        if cap is None or m <= cap:
            return state
    return "STRUCTURAL"  # unreachable, but explicit


def annotate(card: dict) -> dict:
    """Attach temporal_state derived from last_sale_date. Mutates and returns."""
    card["temporal_state"] = classify(card.get("last_sale_date"))
    return card


def score_signal(state: Optional[str], kind: str = "sale") -> int:
    """Score contribution for a single temporal state. Unknown state -> 0."""
    if not state:
        return 0
    table = PERMIT_WEIGHT if kind == "permit" else SALE_WEIGHT
    return table.get(state, 0)
