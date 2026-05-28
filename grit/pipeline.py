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
    """Match a layer's REAL field names to our card fields by substring hint,
    rejecting fields blocked by FIELD_NEGATIVE (e.g. parcel-number != address)."""
    lowered = {f.lower(): f for f in real_fields}
    negatives = getattr(config, "FIELD_NEGATIVE", {})
    mapping = {}
    for card_field, hints in config.FIELD_HINTS.items():
        blocked = negatives.get(card_field, [])
        for hint in hints:
            match = next((orig for low, orig in lowered.items()
                          if hint in low and not any(b in low for b in blocked)), None)
            if match:
                mapping[card_field] = match
                break
    return mapping


def populated_richness(features, mapping):
    """How much real lead data a sample actually contains (not just schema)."""
    n = len(features) or 1
    owner = addr = val = 0
    for f in features:
        p = f.get("properties", {}) or {}
        if mapping.get("owner_name") and p.get(mapping["owner_name"]) not in (None, "", " "):
            owner += 1
        if mapping.get("situs_address") and p.get(mapping["situs_address"]) not in (None, "", " "):
            addr += 1
        if mapping.get("assessed_value") and p.get(mapping["assessed_value"]) not in (None, "", " "):
            val += 1
    return {
        "sample": len(features),
        "owner_pct": round(owner / n, 2),
        "address_pct": round(addr / n, 2),
        "value_pct": round(val / n, 2),
        "score": round((owner + addr) / n + 0.3 * (val / n), 3),
    }


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
def classify_owner(name):
    """Normalize an owner name into one of: PERSON / LLC / TRUST / HOA /
    GOVERNMENT / COMMERCIAL / UNKNOWN. Order matters -- HOA wins over TRUST,
    LLC wins over TRUST (e.g. 'ABC PROPERTIES LLC TRUSTEE'), etc."""
    if not name:
        return "UNKNOWN"
    n = " " + str(name).upper().replace(",", " ") + " "
    tokens = config.ENTITY_TOKENS
    for et in ("HOA", "GOVERNMENT", "LLC"):
        if any(t in n for t in tokens.get(et, [])):
            return et
    if "TRUST" in n:
        return "TRUST"
    if any(t in n for t in tokens.get("COMMERCIAL", [])):
        return "COMMERCIAL"
    return "PERSON"


# ---- scoring (transparent, deterministic, real-signal only) ---------------
def score_card(card):
    """Weighted multi-factor scoring. Entity type sets the floor; contactability,
    recency, value and cluster density build on top. HOAs and government score 0
    (not leads via this channel). Everything is shown in `signals` for audit."""
    entity = card.get("entity_type") or classify_owner(card.get("owner_name"))
    card["entity_type"] = entity
    base = config.ENTITY_BASE_SCORE.get(entity, 8)
    score, signals = base, [f"entity: {entity} (+{base})"]

    if entity in ("HOA", "GOVERNMENT"):
        card["score"] = 0
        card["signals"] = signals + ["filtered: not an individual-homeowner lead"]
        card["suggested_action"] = "skip (HOA / government -- not a contractor lead)"
        return card

    if card.get("situs_address"):
        score += 10; signals.append("has situs address (+10)")
    if card.get("owner_mailing"):
        score += 5;  signals.append("has owner mailing (+5)")

    owner = card.get("owner_mailing"); situs = card.get("situs_address")
    if owner and situs and _addr_differs(owner, situs):
        score += 10
        signals.append("absentee owner -- mailing ≠ situs (+10)")

    months = _months_since(card.get("last_sale_date"))
    if months is not None and months <= 18:
        bonus = 25 if months <= 6 else 18 if months <= 12 else 12
        score += bonus
        signals.append(f"recent sale (~{months} mo, +{bonus})")

    val = _num(card.get("assessed_value"))
    if val is not None:
        if val >= 750_000: score += 20; signals.append("high-value parcel $750k+ (+20)")
        elif val >= 400_000: score += 12; signals.append("mid-high value $400k+ (+12)")
        elif val >= 200_000: score += 6;  signals.append("mid value $200k+ (+6)")

    if card.get("trade_tags"):
        score += 8
        signals.append("trade signal in record (+8): " + ", ".join(card["trade_tags"]))

    cd = card.get("cluster_density") or 0
    if cd:
        bonus = min(cd, config.CLUSTER_MAX_BONUS)
        score += bonus
        signals.append(f"cluster: {cd} neighbors within {config.CLUSTER_RADIUS_M}m (+{bonus})")

    # event-driven (timeline) bonus -- fires once event sources are live
    recent_events = [e for e in (card.get("timeline") or [])
                     if _months_since(e.get("date")) is not None
                     and _months_since(e.get("date")) <= 3]
    if recent_events:
        bonus = min(30 * len(recent_events), 40)
        score += bonus
        signals.append(f"{len(recent_events)} event(s) in last 90d (+{bonus})")

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
    owner = _attr(props, mapping, "owner_name")
    card = {
        "id": f"{source_key}:{_attr(props, mapping, 'parcel_apn') or id(feat)}",
        "source": source_key,
        "harvested_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parcel_apn": _attr(props, mapping, "parcel_apn"),
        "situs_address": _attr(props, mapping, "situs_address"),
        "city": _attr(props, mapping, "city"),
        "zip": _attr(props, mapping, "zip"),
        "owner_name": owner,
        "owner_mailing": _attr(props, mapping, "owner_mailing"),
        "land_use": land_use,
        "assessed_value": _attr(props, mapping, "assessed_value"),
        "last_sale_date": _attr(props, mapping, "last_sale_date"),
        "last_sale_price": _attr(props, mapping, "last_sale_price"),
        "lat": lat, "lng": lng,
        "entity_type": classify_owner(owner),
        "trade_tags": infer_trades(land_use),
        "timeline": [],            # event-driven: filled by event ingestion
        "cluster_density": 0,      # filled in post-pass
        "raw": props,
    }
    return score_card(card)


def enrich_cards(cards, limit=None):
    """0.102: enrich the top-scored cards with LIVE Assessor data (current owner,
    address, value, last sale). Overwrites stale fields, reclassifies the entity,
    emits a DEED event for the recorded sale, and re-scores. Real data only."""
    import time
    from . import assessor, events as events_mod
    limit = limit if limit is not None else config.CARDS_ENRICH_MAX
    targets = [c for c in sorted(cards, key=lambda c: c["score"], reverse=True)
               if c.get("parcel_apn")][:limit]
    new_events, ok, err = [], 0, 0
    FRESH = ("owner_name", "owner_mailing", "situs_address", "city",
             "assessed_value", "land_use", "last_sale_date", "last_sale_price",
             "last_sale_type", "year_built", "bedrooms", "bathrooms",
             "roof_type", "pool", "lot_size", "taxable_value")
    for c in targets:
        data = assessor.enrich_apn(c["parcel_apn"])
        if data.get("_error"):
            err += 1
            continue
        for k in FRESH:
            if data.get(k) not in (None, ""):
                c[k] = data[k]
        c["enriched"] = True
        c["vintage"] = "current"
        c["entity_type"] = classify_owner(c.get("owner_name"))
        c["trade_tags"] = infer_trades(c.get("land_use"))
        if data.get("last_sale_date"):
            ev = events_mod.Event(
                kind="DEED", date=data["last_sale_date"], source="clark_assessor",
                parcel_apn=c["parcel_apn"], address=c.get("situs_address"),
                description=f"recorded sale {data.get('last_sale_price','')} "
                            f"({data.get('last_sale_type','')})".strip(),
                lat=c.get("lat"), lng=c.get("lng"), raw=data)
            new_events.append(ev)
        ok += 1
        time.sleep(config.ENRICH_DELAY)
    return new_events, {"enriched": ok, "errors": err, "attempted": len(targets)}


def assign_cluster_density(cards, radius_m=None):
    """Annotate each card with the count of neighbor cards within radius_m.
    Adds a real geographic-cluster signal (no fake density)."""
    import math
    r = radius_m or config.CLUSTER_RADIUS_M
    r2 = r * r
    for c in cards:
        if c.get("lat") is None or c.get("lng") is None:
            c["cluster_density"] = 0; continue
        lat0, lng0 = c["lat"], c["lng"]
        cos_lat = math.cos(math.radians(lat0))
        count = 0
        for o in cards:
            if o is c or o.get("lat") is None:
                continue
            dy = (o["lat"] - lat0) * 111000.0
            dx = (o["lng"] - lng0) * 111000.0 * cos_lat
            if dx * dx + dy * dy <= r2:
                count += 1
        c["cluster_density"] = count


# ---- orchestration --------------------------------------------------------
def harvest():
    os.makedirs(config.DATA_DIR, exist_ok=True)

    # 1) health probe every registered source (real checks)
    health = [s.probe() for s in sources.REGISTRY]
    _write(config.HEALTH_FILE, {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": health,
    })

    # 2) pick the richest source: evaluate known candidates by SAMPLING real data
    #    (owner/address actually populated), fall back to auto-discovery only if needed.
    cards = []
    harvest_meta = {"status": "no_data", "detail": ""}
    chosen = None
    candidate_report = []

    candidates = []
    if config.CLARK_PARCEL_LAYER:
        candidates.append({"name": "manual override", "url": config.CLARK_PARCEL_LAYER,
                           "where": "1=1"})
    candidates += config.PARCEL_CANDIDATES

    for cand in candidates:
        try:
            feats, fields, info = arcgis.sample_layer(cand["url"], cand.get("where", "1=1"))
            mapping = cand.get("field_map") or build_field_map(fields)
            rich = populated_richness(feats, mapping)
            candidate_report.append({"name": cand.get("name"), "url": cand["url"],
                                     "layer": info.get("name"), "richness": rich,
                                     "mapping": mapping, "vintage": cand.get("vintage")})
            if rich["owner_pct"] + rich["address_pct"] > 0 and (
                    chosen is None or rich["score"] > chosen["rich"]["score"]):
                chosen = {"cand": cand, "mapping": mapping, "info": info, "rich": rich}
        except Exception as e:  # noqa: BLE001
            candidate_report.append({"name": cand.get("name"), "url": cand["url"],
                                     "error": f"{type(e).__name__}: {e}"})

    if chosen is None:  # last resort: crawl the servers for anything with owner data
        try:
            best = arcgis.find_parcel_layer()
            if best:
                fields = best.get("fields", [])
                mapping = build_field_map(fields)
                chosen = {"cand": {"name": "auto-discovered", "url": best["url"],
                                   "where": "1=1"}, "mapping": mapping,
                          "info": {"name": best.get("name")}, "rich": {"score": 0}}
                candidate_report.append({"name": "auto-discovered", "url": best["url"],
                                         "layer": best.get("name"), "mapping": mapping})
        except Exception as e:  # noqa: BLE001
            harvest_meta["detail"] = f"discovery failed: {type(e).__name__}: {e}"

    _write(f"{config.DATA_DIR}/discovered.json", {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selected": chosen["cand"]["url"] if chosen else None,
        "candidates": candidate_report,
    })

    # event-driven layer: load any previously-harvested events and join them to
    # cards by parcel APN, so cards carry their timeline. Empty until event
    # sources (permits, deeds, etc.) start ingesting.
    from . import events as events_mod
    existing_events = events_mod.load_existing()
    if chosen:
        cand = chosen["cand"]
        mapping = chosen["mapping"]
        feats, meta = arcgis.query_layer(cand["url"], where=cand.get("where", "1=1"))
        cards = [feature_to_card(f, mapping, "clark_gis") for f in feats]
        # event join: attach any harvested events to their parcel cards (timeline)
        events_mod.join_to_cards(cards, existing_events)
        # geographic cluster signal (real, computed from harvested points)
        assign_cluster_density(cards)
        cards = [score_card(c) for c in cards]
        # keep the top set, then LIVE-enrich those with current Assessor data
        cards.sort(key=lambda c: c["score"], reverse=True)
        cards = cards[:config.CARDS_MAX]
        enrich_events, enrich_stats = enrich_cards(cards)
        all_events = existing_events + enrich_events
        events_mod.join_to_cards(cards, all_events)   # re-join incl. fresh sales
        cards = [score_card(c) for c in cards]          # re-score with fresh data
        cards.sort(key=lambda c: c["score"], reverse=True)
        events_mod.write(all_events)
        harvest_meta = {"status": "ok", "layer": chosen["info"].get("name"),
                        "source_name": cand.get("name"), "vintage": cand.get("vintage"),
                        "layer_url": cand["url"], "field_map": mapping,
                        "richness": chosen["rich"], "enrichment": enrich_stats, **meta}
    elif not harvest_meta["detail"]:
        harvest_meta["detail"] = ("No candidate returned populated owner/address data. "
                                  "See discovered.json for what each source exposed.")

    _write(config.CARDS_FILE, {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harvest": harvest_meta,
        "count": len(cards),
        "cards": cards,
    })
    # persist events feed only if harvest didn't already write fresh ones
    if not chosen:
        events_mod.write(existing_events)
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
