"""
Entity graph -- the "money moving as a herd" engine (Phase 0.103 directive).

The core insight: isolated parcels are noise; PORTFOLIOS are signal. The same
operator typically appears as:
  - the same LLC across 5 parcels
  - several differently-named LLCs all mailing to ONE PO box / suite
  - a family trust + a related person sharing a mailing address
  - a person + an LLC the person controls

This module clusters cards into OPERATORS using two join keys:
  (1) normalized owner name (collapse LLC/INC/TRUST suffixes + whitespace)
  (2) normalized mailing address (strip apt/unit + state/zip noise)

Cards sharing EITHER key with another card join the same operator cluster
(union-find). PERSON-type owners are NEVER merged by name alone (avoids the
"JOHN SMITH everywhere" false-positive); they merge only via shared mailing.

Output: operators.json (the ranked operator table) + per-card annotations
(operator_id, portfolio_size, portfolio_value, portfolio_concentration).

Every join is computed from real harvested fields. No fabricated relationships.
"""
import collections
import hashlib
import re
from typing import Dict, List, Optional, Set

# Suffixes / corporate noise stripped during owner normalization. Order matters:
# longest first so " L L C" doesn't get eaten by " L".
_OWNER_NOISE = (
    " L L C", " L.L.C.", " L.L.C", " LLC", " L.P.", " L P", " LP",
    " INCORPORATED", " INC.", " INC",
    " CORPORATION", " CORP.", " CORP",
    " LIMITED", " LTD.", " LTD",
    " TRUSTEE", " TRUSTEES", " AS TRUSTEE", " TRUST",
    " ETAL", " ET AL", " ETUX", " ET UX", " ET VIR",
    " &", " AND ",
)

# Words whose presence signals an entity that should NOT be an operator
# (HOAs / government / churches handled at the entity_type level anyway).
_OPERATOR_EXCLUDE = ("HOA", "GOVERNMENT")


def _norm_owner(name: Optional[str]) -> str:
    """Aggressive owner-name normalization for cluster matching."""
    if not name:
        return ""
    n = " " + str(name).upper() + " "
    n = n.replace(",", " ").replace(".", " ")
    # repeatedly strip corporate suffixes
    changed = True
    while changed:
        changed = False
        for suf in _OWNER_NOISE:
            if n.endswith(suf + " ") or (suf + " ") in n:
                n = n.replace(suf, " ")
                changed = True
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _norm_mailing(mail: Optional[str]) -> str:
    """Mailing-address normalization for cluster matching. Strips unit/apt,
    state, zip, and whitespace noise. Same mailing => same operator network."""
    if not mail:
        return ""
    m = " " + str(mail).upper() + " "
    m = m.replace(",", " ").replace(".", " ")
    # drop apt / unit / suite numbers (keep the building address)
    m = re.sub(r"\b(APT|UNIT|STE|SUITE|#)\s*\S+", " ", m)
    # collapse common street-type abbreviations
    m = re.sub(r"\b(STREET|ST|AVENUE|AVE|BOULEVARD|BLVD|ROAD|RD|DRIVE|DR|"
               r"LANE|LN|COURT|CT|PARKWAY|PKWY|HIGHWAY|HWY|PLACE|PL|WAY)\b",
               lambda x: {"STREET":"ST","AVENUE":"AVE","BOULEVARD":"BLVD",
                          "ROAD":"RD","DRIVE":"DR","LANE":"LN","COURT":"CT",
                          "PARKWAY":"PKWY","HIGHWAY":"HWY","PLACE":"PL"
                          }.get(x.group(0), x.group(0)), m)
    # drop trailing zip (5 or 9 digit) and 2-letter state
    m = re.sub(r"\b[A-Z]{2}\s+\d{5}(-\d{4})?\b", " ", m)
    m = re.sub(r"\b\d{5}(-\d{4})?\b", " ", m)
    m = re.sub(r"\s+", " ", m).strip()
    return m


def _to_num(v) -> Optional[float]:
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def add(self, k: str):
        if k and k not in self.parent:
            self.parent[k] = k

    def find(self, k: str) -> str:
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def union(self, a: str, b: str):
        if not a or not b:
            return
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_operator_graph(cards: List[dict]) -> List[dict]:
    """Cluster `cards` into operators. Annotates each card with operator_id /
    portfolio_size / portfolio_value (mutates in place) and returns the operator
    table, sorted by composite score (size + value + recency)."""
    from . import temporal  # local import to avoid cycle at module load

    uf = _UnionFind()

    # 1) build node ids per card; collect candidate keys
    card_keys: List[Dict[str, str]] = []
    for c in cards:
        et = c.get("entity_type") or "UNKNOWN"
        if et in _OPERATOR_EXCLUDE:
            card_keys.append({})  # placeholder; excluded from graph
            continue
        owner_norm = _norm_owner(c.get("owner_name"))
        mail_norm  = _norm_mailing(c.get("owner_mailing"))
        # for PERSON, owner name alone is too generic to cluster on (many
        # JOHN SMITHs); only allow PERSON to cluster via shared mailing.
        owner_key = f"O:{owner_norm}" if owner_norm and et != "PERSON" else ""
        mail_key  = f"M:{mail_norm}"  if mail_norm  else ""
        card_keys.append({"owner": owner_key, "mail": mail_key})
        for k in (owner_key, mail_key):
            uf.add(k)
        if owner_key and mail_key:
            uf.union(owner_key, mail_key)

    # 2) each card -> root cluster id (or a singleton id if no joinable key)
    clusters: Dict[str, List[int]] = collections.defaultdict(list)
    for i, keys in enumerate(card_keys):
        if not keys:
            continue
        root = None
        for k in (keys.get("owner"), keys.get("mail")):
            if k:
                root = uf.find(k); break
        if root is None:
            continue
        clusters[root].append(i)

    # 3) materialize the operator table
    operators: List[dict] = []
    for root, idxs in clusters.items():
        members = [cards[i] for i in idxs]
        # canonical name: the most common normalized owner name in the cluster
        names = [m.get("owner_name") for m in members if m.get("owner_name")]
        canonical = collections.Counter(names).most_common(1)
        name = canonical[0][0] if canonical else "(unnamed cluster)"
        # representative mailing (first non-null)
        mailing = next((m.get("owner_mailing") for m in members if m.get("owner_mailing")), None)
        # value + temporal signals
        vals = [v for v in (_to_num(m.get("assessed_value")) for m in members) if v is not None]
        total_value = sum(vals) if vals else 0.0
        states = [temporal.classify(m.get("last_sale_date")) for m in members]
        recent = sum(1 for s in states if s in ("IMMEDIATE", "WARM"))
        cities = sorted({(m.get("city") or "").strip() for m in members if m.get("city")})
        ent_mix = collections.Counter(m.get("entity_type") or "UNKNOWN" for m in members)
        # operator id: stable short hash of the root key
        oid = hashlib.sha1(root.encode("utf-8")).hexdigest()[:10]
        size = len(members)
        # composite operator score: size + value + recency weighting
        score = (
            min(size, 40) * 2                 # parcel count, capped
            + min(int(total_value / 250_000), 30)  # $ per 250k assessed, capped
            + recent * 6                      # recent activity multiplier
        )
        operators.append({
            "id": oid,
            "name": name,
            "canonical_mailing": mailing,
            "entity_mix": dict(ent_mix),
            "parcel_count": size,
            "total_assessed_value": total_value,
            "recent_activity_count": recent,
            "cities": cities,
            "parcel_apns": [m.get("parcel_apn") for m in members if m.get("parcel_apn")],
            "score": score,
            "join_key": root,
        })

    operators.sort(key=lambda o: o["score"], reverse=True)

    # 4) annotate each card with its operator (only if portfolio_size >= 2)
    op_by_root: Dict[str, dict] = {o["join_key"]: o for o in operators}
    for i, keys in enumerate(card_keys):
        c = cards[i]
        if not keys:
            c["operator_id"] = None
            c["portfolio_size"] = 1
            c["portfolio_value"] = _to_num(c.get("assessed_value")) or 0.0
            continue
        root = None
        for k in (keys.get("owner"), keys.get("mail")):
            if k:
                root = uf.find(k); break
        op = op_by_root.get(root)
        if op and op["parcel_count"] >= 2:
            c["operator_id"]     = op["id"]
            c["portfolio_size"]  = op["parcel_count"]
            c["portfolio_value"] = op["total_assessed_value"]
        else:
            c["operator_id"]     = None
            c["portfolio_size"]  = 1
            c["portfolio_value"] = _to_num(c.get("assessed_value")) or 0.0

    return operators
