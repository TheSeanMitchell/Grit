"""
Pipeline: real ArcGIS features -> scored call cards.

Hard rule: every field is either populated from a REAL source attribute or left
null. Nothing is invented. If a field's source attribute is missing, the card
shows it as unknown and any signal that depends on it contributes zero.
"""
import datetime as dt
import json
import os

from . import config, arcgis, sources


# ---- field auto-mapping ---------------------------------------------------
def build_field_map(real_fields):
    """Match a layer's REAL field names to our card fields by substring hint."""
    lowered = {f.lower(): f for f in real_fields}
    mapping = {}
    for card_field, hints in config.FIELD_HINTS.items():
        for hint in hints:
            match = next((orig for low, orig in lowered.items() if hint in low), None)
            if match:
                mapping[card_field] = match
                break
    return mapping


def _attr(props, mapping, key):
    src = mapping.get(key)
    if not src:
        return None
    val = props.get(src)
    if val in ("", " ", None):
        return None
    return val


def _centroid(geom):
    if not geom:
        return None, None
    t = geom.get("type")
    c = geom.get("coordinates")
    try:
        if t == "Point":
            return c[1], c[0]
        if t in ("Polygon", "MultiPolygon"):
            ring = c[0][0] if t == "MultiPolygon" else c[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            return sum(ys) / len(ys), sum(xs) / len(xs)
    except Exception:
        return None, None
    return None, None


def infer_trades(*texts):
    blob = " ".join(str(t).lower() for t in texts if t)
    tags = [trade for trade, kws in config.TRADE_KEYWORDS.items()
            if any(k in blob for k in kws)]
    return tags


# ---- scoring (transparent, deterministic, real-signal only) ---------------
def score_card(card):
    score, signals = 0, []

    sale = card.get("last_sale_date")
    months = _months_since(sale)
    if months is not None and months <= 18:
        score += 30
        signals.append(f"recent sale (~{months} mo ago) -> likely renovation window")

    lu = (card.get("land_use") or "").lower()
    if any(k in lu for k in ("single", "sfr", "residential", "res ")):
        score += 10
        signals.append("residential parcel")

    val = _num(card.get("assessed_value"))
    if val is not None:
        if val >= 750_000:
            score += 20; signals.append("high-value parcel ($750k+)")
        elif val >= 400_000:
            score += 12; signals.append("mid-high value parcel ($400k+)")
        elif val >= 200_000:
            score += 6; signals.append("mid value parcel ($200k+)")

    owner = card.get("owner_mailing")
    situs = card.get("situs_address")
    if owner and situs and _addr_differs(owner, situs):
        score += 10
        signals.append("absentee owner (mailing != situs) -> rental/flip angle")

    if card.get("trade_tags"):
        score += 8
        signals.append("trade signal in record: " + ", ".join(card["trade_tags"]))

    card["score"] = min(score, 100)
    card["signals"] = signals
    card["suggested_action"] = _next_action(card)
    return card


def _next_action(card):
    if card.get("owner_name") and card.get("situs_address"):
        who = card["owner_name"]
        return f"Pull contact for {who}; confirm project intent at {card['situs_address']}."
    if card.get("situs_address"):
        return f"Skip-trace owner for {card['situs_address']}, then reach out."
    return "Enrich record (owner + contact) before outreach."


# ---- card construction ----------------------------------------------------
def feature_to_card(feat, mapping, source_key):
    props = feat.get("properties", {}) or {}
    lat, lng = _centroid(feat.get("geometry"))
    land_use = _attr(props, mapping, "land_use")
    card = {
        "id": f"{source_key}:{_attr(props, mapping, 'parcel_apn') or id(feat)}",
        "source": source_key,
        "harvested_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parcel_apn": _attr(props, mapping, "parcel_apn"),
        "situs_address": _attr(props, mapping, "situs_address"),
        "city": _attr(props, mapping, "city"),
        "zip": _attr(props, mapping, "zip"),
        "owner_name": _attr(props, mapping, "owner_name"),
        "owner_mailing": _attr(props, mapping, "owner_mailing"),
        "land_use": land_use,
        "assessed_value": _attr(props, mapping, "assessed_value"),
        "last_sale_date": _attr(props, mapping, "last_sale_date"),
        "last_sale_price": _attr(props, mapping, "last_sale_price"),
        "lat": lat, "lng": lng,
        "trade_tags": infer_trades(land_use),
        "raw": props,  # full provenance for debugging / enrichment
    }
    return score_card(card)


# ---- orchestration --------------------------------------------------------
def harvest():
    os.makedirs(config.DATA_DIR, exist_ok=True)

    # 1) health probe every registered source (real checks)
    health = [s.probe() for s in sources.REGISTRY]
    _write(config.HEALTH_FILE, {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": health,
    })

    # 2) harvest the live API source. Auto-discover the parcel layer if not pinned.
    cards = []
    harvest_meta = {"status": "no_data", "detail": ""}
    layer_url = config.CLARK_PARCEL_LAYER
    discovered = None

    if not layer_url:
        try:
            best = arcgis.find_parcel_layer()
        except Exception as e:  # noqa: BLE001
            best = None
            harvest_meta["detail"] = f"auto-discovery failed: {type(e).__name__}: {e}"
        if best:
            layer_url = best["url"]
            discovered = best
            _write(f"{config.DATA_DIR}/discovered.json", {
                "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                **best,
            })

    if layer_url:
        fields, info = arcgis.layer_meta(layer_url)
        mapping = build_field_map(fields)
        feats, meta = arcgis.query_layer(layer_url)
        cards = [feature_to_card(f, mapping, "clark_gis") for f in feats]
        cards.sort(key=lambda c: c["score"], reverse=True)
        cards = cards[:config.CARDS_MAX]
        harvest_meta = {"status": "ok", "layer": info.get("name"),
                        "layer_url": layer_url, "auto_discovered": bool(discovered),
                        "field_map": mapping, **meta}
    elif not harvest_meta["detail"]:
        harvest_meta["detail"] = ("No parcel layer found by auto-discovery. "
                                  "You can pin one manually via CLARK_PARCEL_LAYER.")

    _write(config.CARDS_FILE, {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harvest": harvest_meta,
        "count": len(cards),
        "cards": cards,
    })
    return len(cards), harvest_meta


# ---- helpers --------------------------------------------------------------
def _write(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _months_since(date_val):
    if date_val is None:
        return None
    try:
        if isinstance(date_val, (int, float)) and date_val > 1e10:  # epoch ms
            d = dt.datetime.utcfromtimestamp(date_val / 1000)
        else:
            s = str(date_val)[:10]
            d = dt.datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, OverflowError, OSError):
        return None
    now = dt.datetime.utcnow()
    return (now.year - d.year) * 12 + (now.month - d.month)


def _addr_differs(a, b):
    norm = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())[:12]
    return norm(a) and norm(b) and norm(a) != norm(b)
