"""
Confidence architecture (Alpha 0.107, directive Priority 6).

Every significant field carries provenance: a confidence CLASS, the SOURCE it
came from, and the METHOD used to resolve it. This makes "how much of the
warehouse can we trust, and why" a measured distribution instead of a feeling.

Classes (most to least trustworthy):
  authoritative -- straight from an authoritative system of record (assessor
                   parcel layer, permit feed, source parcel roll, real centroid)
  derived       -- computed deterministically from authoritative data
                   (jurisdiction-by-coordinate, owner-origin parse, urgency)
  inferred      -- a heuristic read that could be wrong (entity type from the
                   owner-name pattern, owner-occupied vs absentee)
  unknown       -- the field is absent (an honest gap, surfaced as unknown)

No value is invented. A field with no data is 'unknown', never back-filled.
"""

# The significant fields whose confidence the warehouse reports on.
KEY_FIELDS = [
    "parcel_apn", "situs_address", "lat", "owner_name", "owner_mailing",
    "property_jurisdiction", "assessed_value", "land_value", "improvement_value",
    "building_sqft", "lot_sqft", "year_built", "bedrooms", "bathrooms",
    "property_use_code", "land_use", "last_sale_date", "last_sale_price",
    "permit_count", "last_permit_date", "trade_tags", "contractors",
    "owner_origin_market", "entity_type", "occupancy_status", "temporal_state",
    "urgency", "primary_date", "score",
]

_ASSESSOR_FIELDS = {"assessed_value", "land_value", "improvement_value",
                    "building_sqft", "lot_sqft", "year_built", "bedrooms",
                    "bathrooms", "property_use_code", "land_use",
                    "last_sale_date", "last_sale_price"}
_PERMIT_FIELDS = {"permit_count", "last_permit_date", "trade_tags",
                  "contractors", "permit_value_total"}
_DERIVED_FIELDS = {"temporal_state", "urgency", "primary_date", "age_days",
                   "score", "cluster_density", "property_type",
                   "owner_origin_market", "owner_city", "owner_state"}
_INFERRED_FIELDS = {"entity_type", "occupancy_status"}

_WEIGHT = {"authoritative": 1.0, "derived": 0.6, "inferred": 0.3, "unknown": 0.0}


def _present(v):
    if v in (None, "", [], {}):
        return False
    s = str(v).strip()
    return s not in ("0", "0.0", "null", "None", "<Null>")


def classify(card, field):
    """Return (confidence_class, source, method) for a field on this card.
    Absent fields are ('unknown', None, None)."""
    if not _present(card.get(field)):
        return "unknown", None, None

    if field in _ASSESSOR_FIELDS:
        ef = card.get("enriched_from")
        if ef == "parcel_layer":
            return "authoritative", "clark_assessor_layer", "batched-layer-query"
        if card.get("vintage") == "current" or card.get("enriched"):
            return "authoritative", "clark_assessor", "parcel-detail"
        return "authoritative", "parcel_roll", "source-roll"

    if field in _PERMIT_FIELDS:
        return "authoritative", "clv_permit", "permit-feed"

    if field == "lat":
        return ("authoritative", "clark_assessor_layer", "apn-centroid") \
            if card.get("geocoded") == "parcel_centroid" \
            else ("authoritative", "source_geometry", "source-coordinate")

    if field in ("parcel_apn", "situs_address", "owner_name", "owner_mailing"):
        if card.get("source") == "clv_permit":
            return "authoritative", "clv_permit", "permit-feed"
        return "authoritative", "parcel_roll", "source-roll"

    if field == "property_jurisdiction":
        src = card.get("jurisdiction_source")
        if src in ("permit-feed", "assessor-city", "situs"):
            return "authoritative", src, "source-field"
        if src == "coordinate":
            return "derived", "parcel_centroid", "coordinate-bbox"
        if src == "county":
            return "derived", "parcel_centroid", "county-envelope"
        return "derived", "resolver", "jurisdiction-resolve"

    if field in _DERIVED_FIELDS:
        m = {"owner_origin_market": "mailing-parse"}.get(field, "computed")
        return "derived", "grit_engine", m

    if field in _INFERRED_FIELDS:
        m = "name-heuristic" if field == "entity_type" else "mailing-compare"
        return "inferred", "grit_engine", m

    return "derived", "grit_engine", "computed"


def annotate(card):
    """Attach card['field_confidence'] (present significant fields) and
    card['confidence'] (class counts + weighted 0-100 score + dominant class).
    Mutates and returns the card."""
    fc, counts = {}, {"authoritative": 0, "derived": 0, "inferred": 0, "unknown": 0}
    for f in KEY_FIELDS:
        cls, src, method = classify(card, f)
        counts[cls] += 1
        if cls != "unknown":
            fc[f] = {"c": cls, "s": src, "m": method}
    known = counts["authoritative"] + counts["derived"] + counts["inferred"]
    score = round(100 * sum(_WEIGHT[k] * counts[k] for k in counts) / len(KEY_FIELDS))
    dominant = max(("authoritative", "derived", "inferred"), key=lambda k: counts[k]) \
        if known else "unknown"
    card["field_confidence"] = fc
    card["confidence"] = {**counts, "known": known, "score": score, "dominant": dominant}
    card["confidence_score"] = score
    return card


def distribution(cards):
    """Warehouse-wide confidence distribution over KEY_FIELDS x cards, plus a
    per-field breakdown so the audit can show which fields are authoritative vs
    unknown. Real classification only -- 'unknown' is a measured gap."""
    totals = {"authoritative": 0, "derived": 0, "inferred": 0, "unknown": 0}
    per_field = {}
    for c in cards:
        for f in KEY_FIELDS:
            cls = (c.get("field_confidence", {}).get(f, {}).get("c")
                   or ("unknown" if not _present(c.get(f)) else classify(c, f)[0]))
            totals[cls] += 1
            d = per_field.setdefault(f, {"authoritative": 0, "derived": 0,
                                         "inferred": 0, "unknown": 0})
            d[cls] += 1
    n = sum(totals.values()) or 1
    pct = {k: round(100 * v / n, 1) for k, v in totals.items()}
    rows = []
    for f, d in per_field.items():
        tot = sum(d.values()) or 1
        known = tot - d["unknown"]
        rows.append({"field": f, **d, "known_pct": round(100 * known / tot, 1)})
    rows.sort(key=lambda r: r["known_pct"], reverse=True)
    avg = round(sum(c.get("confidence", {}).get("score", 0) for c in cards) / (len(cards) or 1), 1)
    return {"totals": totals, "pct": pct, "field_instances": n,
            "avg_card_confidence": avg, "by_field": rows}
