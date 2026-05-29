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
    """Weighted multi-factor scoring with multi-layer temporal intelligence.
    Old signals reclassify (IMMEDIATE/WARM/PERSISTENT/HISTORICAL/STRUCTURAL),
    they never disappear -- the directive's 'old != dead' rule. Cards that
    belong to a detected operator portfolio get a portfolio bonus ('money
    moving as a herd'). All contributions are shown in signals[] for audit."""
    from . import temporal
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
        signals.append("absentee owner -- mailing != situs (+10)")

    # Multi-layer temporal classification on the sale signal.
    state = temporal.classify(card.get("last_sale_date"))
    card["temporal_state"] = state
    sale_bonus = temporal.score_signal(state, kind="sale")
    if sale_bonus:
        signals.append(f"sale {state.lower()} (+{sale_bonus})")
        score += sale_bonus

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

    # Portfolio bonus -- the "herd" signal. Annotated by entities.build_operator_graph.
    psize = card.get("portfolio_size") or 1
    if psize >= 2:
        # bonus saturates: 2 parcels +6, 5 +12, 10 +18, capped at 20
        pbonus = min(6 + (psize - 2) * 2, 20)
        score += pbonus
        signals.append(f"portfolio: operator controls {psize} parcels (+{pbonus})")

    # event-driven (timeline) bonus -- fires once event sources are live
    recent_events = [e for e in (card.get("timeline") or [])
                     if temporal.classify(e.get("date")) in ("IMMEDIATE", "WARM")]
    if recent_events:
        bonus = min(30 * len(recent_events), 40)
        score += bonus
        signals.append(f"{len(recent_events)} recent event(s) (+{bonus})")
        # reflect the freshest event in the temporal lens (permits are activity now)
        newest = max((e.get("date") for e in card["timeline"] if e.get("date")), default=None)
        ev_state = temporal.classify(newest)
        order = ["STRUCTURAL", "HISTORICAL", "PERSISTENT", "WARM", "IMMEDIATE"]
        def _rank(s):
            return order.index(s) if s in order else -1
        if _rank(ev_state) > _rank(card.get("temporal_state")):
            card["temporal_state"] = ev_state

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


# ---- permits as leads (EVENT -> ENTITY -> MONEY) --------------------------
def permits_to_cards(permits):
    """Turn recent permits into lead cards. A permit is an active-work signal:
    owner + site + APN + contractor + valuation + date. Multiple permits on one
    parcel collapse into a single card (union of trades/contractors, newest date)."""
    by_key, cards = {}, []
    for p in permits:
        owner = p.get("owner_name")
        entity = classify_owner(owner)
        if entity in ("HOA", "GOVERNMENT"):       # not contractor leads
            continue
        key = p.get("apn") or ("ADDR:" + (p.get("site_address") or p.get("record") or ""))
        c = by_key.get(key)
        if c is None:
            c = {"id": f"clv_permit:{key}", "source": "clv_permit",
                 "parcel_apn": p.get("apn"), "situs_address": p.get("site_address"),
                 "situs_city": p.get("city"), "owner_name": owner,
                 "owner_mailing": p.get("owner_mailing"), "entity_type": entity,
                 "trade_tags": [], "lat": p.get("lat"), "lng": p.get("lng"),
                 "permit_count": 0, "contractors": [], "last_permit_date": None,
                 "permit_value_total": 0.0, "has_permit": True}
            by_key[key] = c
            cards.append(c)
        c["permit_count"] += 1
        for t in p.get("trades", []):
            if t not in c["trade_tags"]:
                c["trade_tags"].append(t)
        ct = p.get("contractor")
        if ct and ct not in c["contractors"]:
            c["contractors"].append(ct)
        v = _num(p.get("valuation"))
        if v:
            c["permit_value_total"] += v
        d = p.get("date")
        if d and (not c["last_permit_date"] or d > c["last_permit_date"]):
            c["last_permit_date"] = d
        if not c.get("lat") and p.get("lat"):
            c["lat"], c["lng"] = p.get("lat"), p.get("lng")
        if not c.get("owner_name") and owner:
            c["owner_name"], c["entity_type"] = owner, entity
    return cards


def merge_permit_cards(parcel_cards, permit_cards):
    """Merge permit lead-cards into the parcel set. If a permit's APN matches a
    parcel card, enrich it (fill owner gaps + attach permit activity); otherwise
    add the permit as a new lead. Returns the combined list + a small stat dict."""
    def norm(apn):
        return "".join(ch for ch in str(apn or "") if ch.isdigit())
    idx = {}
    for c in parcel_cards:
        k = norm(c.get("parcel_apn"))
        if k:
            idx[k] = c
    enriched = added = 0
    for pc in permit_cards:
        k = norm(pc.get("parcel_apn"))
        host = idx.get(k) if k else None
        if host:
            if not host.get("owner_name") and pc.get("owner_name"):
                host["owner_name"], host["entity_type"] = pc["owner_name"], pc["entity_type"]
            if not host.get("owner_mailing") and pc.get("owner_mailing"):
                host["owner_mailing"] = pc["owner_mailing"]
            host.setdefault("trade_tags", [])
            for t in pc.get("trade_tags", []):
                if t not in host["trade_tags"]:
                    host["trade_tags"].append(t)
            host["contractors"] = pc.get("contractors")
            host["permit_count"] = pc.get("permit_count")
            host["permit_value_total"] = pc.get("permit_value_total")
            host["last_permit_date"] = pc.get("last_permit_date")
            host["has_permit"] = True
            if not host.get("lat") and pc.get("lat"):
                host["lat"], host["lng"] = pc.get("lat"), pc.get("lng")
            enriched += 1
        else:
            parcel_cards.append(pc)
            if k:
                idx[k] = pc
            added += 1
    return parcel_cards, {"permit_cards_added": added, "permit_cards_enriched_existing": enriched}


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
    emits a DEED event for the recorded sale, and re-scores. Real data only.

    0.103: track silent parser misses (fetched but no fields parsed) separately
    from network errors -- the silent-miss rate is the real density bottleneck."""
    import time
    from . import assessor, events as events_mod
    limit = limit if limit is not None else config.CARDS_ENRICH_MAX
    targets = [c for c in sorted(cards, key=lambda c: c["score"], reverse=True)
               if c.get("parcel_apn")][:limit]
    new_events, ok, err, silent = [], 0, 0, 0
    silent_apns = []
    FRESH = ("owner_name", "owner_mailing", "situs_address", "city",
             "assessed_value", "land_use", "last_sale_date", "last_sale_price",
             "last_sale_type", "year_built", "bedrooms", "bathrooms",
             "roof_type", "pool", "lot_size", "taxable_value")
    for c in targets:
        data = assessor.enrich_apn(c["parcel_apn"])
        if data.get("_error"):
            err += 1
            continue
        if data.get("_silent"):
            silent += 1
            silent_apns.append(c["parcel_apn"])
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
    attempted = len(targets)
    yield_pct = round(100 * ok / attempted, 1) if attempted else 0.0
    return new_events, {"enriched": ok, "silent_misses": silent, "errors": err,
                        "attempted": attempted, "yield_pct": yield_pct,
                        "silent_sample_apns": silent_apns[:5]}


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

    import time as _time
    for cand in candidates:
        last_err = None
        for attempt in (1, 2, 3, 4):                    # owner-rich layers are flaky (5xx/timeout) -- keep trying
            try:
                feats, fields, info = arcgis.sample_layer(
                    cand["url"], cand.get("where", "1=1"), timeout=60)
                mapping = cand.get("field_map") or build_field_map(fields)
                rich = populated_richness(feats, mapping)
                candidate_report.append({"name": cand.get("name"), "url": cand["url"],
                                         "layer": info.get("name"), "richness": rich,
                                         "mapping": mapping, "vintage": cand.get("vintage"),
                                         "attempts": attempt})
                if rich["owner_pct"] + rich["address_pct"] > 0 and (
                        chosen is None or rich["score"] > chosen["rich"]["score"]):
                    chosen = {"cand": cand, "mapping": mapping, "info": info, "rich": rich}
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                # retry transient server errors / timeouts with backoff; give up on hard 4xx
                transient = any(t in last_err for t in
                                ("500", "502", "503", "504", "timed out", "TimeoutError",
                                 "URLError", "Connection", "reset"))
                if attempt < 4 and transient:
                    _time.sleep(2 * attempt)            # 2s, 4s, 6s backoff
                    continue
                break
        if last_err:
            candidate_report.append({"name": cand.get("name"), "url": cand["url"],
                                     "error": last_err, "attempts": attempt})

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
        # CLOUD-NATIVE LIVE PERMIT FLOW (City of Las Vegas ArcGIS Hub; not IP-blocked,
        # so this runs right here in the GitHub runner -- no residential capture).
        # Permits ARE leads: each becomes/enriches a lead card (EVENT->ENTITY->MONEY).
        from . import clv_permits
        permits, permit_report = clv_permits.fetch_clv_permits(days_back=config.PERMIT_DAYS_BACK)
        permit_events = clv_permits.to_events(permits)
        cards, permit_merge = merge_permit_cards(cards, permits_to_cards(permits))
        all_events = existing_events + enrich_events + permit_events
        events_mod.join_to_cards(cards, all_events)   # re-join incl. fresh sales + permits
        # 0.103: build the operator graph BEFORE the final re-score so the
        # portfolio bonus ('money moving as a herd') lands in each card's score.
        from . import entities
        operators = entities.build_operator_graph(cards)
        cards = [score_card(c) for c in cards]          # re-score with fresh data + portfolio
        cards.sort(key=lambda c: c["score"], reverse=True)
        owner_pct = round(100 * sum(1 for c in cards if c.get("owner_name")) / max(len(cards),1), 1)
        harvest_meta = {"status": "ok", "layer": chosen["info"].get("name"),
                        "source_name": cand.get("name"), "vintage": cand.get("vintage"),
                        "layer_url": cand["url"], "field_map": mapping,
                        "richness": chosen["rich"], "enrichment": enrich_stats,
                        "density": {"cards_total": len(cards),
                                    "cards_with_owner": sum(1 for c in cards if c.get("owner_name")),
                                    "owner_pct": owner_pct,
                                    "operators_detected": len(operators),
                                    "portfolios_2plus": sum(1 for o in operators if o["parcel_count"] >= 2)},
                        "permits": {"source": "City of Las Vegas (ArcGIS Hub)", "status": permit_report.get("status"),
                                    "ingested": len(permit_events),
                                    "leads_added": permit_merge.get("permit_cards_added"),
                                    "leads_enriched": permit_merge.get("permit_cards_enriched_existing"),
                                    "trade_tagged": sum(1 for e in permit_events if e.trade_tag),
                                    "newest": permit_report.get("newest"),
                                    "error": permit_report.get("error")},
                        **meta}

        # ---- REGRESSION GUARD (before ANY data write) ----------------------
        # A transient 5xx/timeout that drops us to an APN-only layer must never
        # overwrite a good harvest. If the prior cards.json had real owner
        # density and this run collapsed, KEEP all prior outputs, quarantine the
        # bad run, flag it loudly. The failure mode is binary (~67% vs ~1-7%).
        prev = _read_json(config.CARDS_FILE)
        prev_pct = (prev or {}).get("harvest", {}).get("density", {}).get("owner_pct")
        if prev_pct is None and prev and prev.get("cards"):
            prev_pct = round(100 * sum(1 for c in prev["cards"] if c.get("owner_name")) / max(len(prev["cards"]), 1), 1)
        if prev_pct is not None and prev_pct >= 30.0 and owner_pct < prev_pct * 0.35:
            _write(f"{config.DATA_DIR}/cards_quarantine.json", {
                "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reason": f"owner density collapsed {prev_pct}% -> {owner_pct}% "
                          f"(source: {cand.get('name')}); kept prior harvest",
                "harvest": harvest_meta, "count": len(cards), "cards": cards})
            _write(config.HEALTH_FILE, {
                "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sources": health,
                "harvest_skipped": {"reason": "regression_guard", "prev_owner_pct": prev_pct,
                                    "new_owner_pct": owner_pct, "source": cand.get("name")}})
            print(f"  REGRESSION GUARD: owner density {prev_pct}% -> {owner_pct}%. "
                  f"Kept prior harvest; bad run quarantined. Transient source "
                  f"5xx/timeout -- re-run when the owner layer recovers.")
            return (prev or {}).get("count", 0), {
                "status": "regression_skipped", "prev_owner_pct": prev_pct,
                "new_owner_pct": owner_pct,
                "detail": f"kept prior harvest ({prev_pct}% owners); run collapsed to {owner_pct}%"}

        # passed the guard -> commit all outputs
        events_mod.write(all_events)
        _write(f"{config.DATA_DIR}/operators.json", {
            "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "version": config.VERSION,
            "count": len(operators),
            "portfolios_2plus": sum(1 for o in operators if o["parcel_count"] >= 2),
            "operators": operators,
        })
    elif not harvest_meta["detail"]:
        harvest_meta["detail"] = ("No candidate returned populated owner/address data. "
                                  "See discovered.json for what each source exposed.")

    _write(config.CARDS_FILE, {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": config.VERSION,
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


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return None


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
