"""
GRIT CLI.

  python -m grit health     probe every registered source, write health.json
  python -m grit discover   walk the Clark County ArcGIS server, list services
                            and the REAL fields of likely parcel layers
  python -m grit harvest    health + harvest the live API source -> cards.json
  python -m grit rebuild    re-derive the .105 intelligence layer (tags, why,
                            contractors, coverage) from existing data, no network
  python -m grit coverage   print permit-completeness + category health matrix
  python -m grit contractors  print the contractor leaderboard
  python -m grit selftest   run the transform logic on a fixture (no network)

`discover` is how you pin the exact parcel layer without anyone guessing a schema.
"""
import os
import sys

from . import arcgis, config, sources, pipeline, assessor, permits


def cmd_health():
    recs = [s.probe() for s in sources.REGISTRY]
    for r in recs:
        line = f"[{r['status']:>9}] {r['name']}"
        if r["latency_ms"] is not None:
            line += f"  {r['latency_ms']}ms"
        if r["error"]:
            line += f"  ERR {r['error']}"
        print(line)
    print(f"\n{len(recs)} sources probed.")


def cmd_discover():
    root = config.CLARK_ARCGIS_ROOT
    print(f"Walking {root}\n")
    cat = arcgis.catalog(root)
    print("Folders:", ", ".join(cat["folders"]) or "(none)")
    print()
    # Look through folders for services whose layers expose owner/parcel fields.
    candidates = []
    folders = [None] + cat["folders"]
    for fld in folders:
        try:
            svcs = cat["services"] if fld is None else arcgis.folder(root, fld)
        except Exception as e:  # noqa: BLE001
            print(f"  ! folder {fld}: {e}")
            continue
        for svc in svcs:
            name = svc.get("name")
            typ = svc.get("type")
            if typ not in ("FeatureServer", "MapServer"):
                continue
            base = f"{root}/{name}/{typ}"
            for lid in range(0, 30):  # probe layer ids
                try:
                    fields, info = arcgis.layer_meta(f"{base}/{lid}")
                except Exception:
                    break
                hit = [c for c, hints in config.FIELD_HINTS.items()
                       if any(any(h in f.lower() for f in fields) for h in hints)]
                if {"owner_name", "parcel_apn"} & set(hit) or "owner_name" in hit:
                    url = f"{base}/{lid}"
                    print(f"  ✓ {info['name']}  ->  {url}")
                    print(f"      matches: {', '.join(hit)}")
                    candidates.append(url)
    print("\nCandidates with owner/parcel fields:")
    for c in candidates:
        print("  ", c)
    print("\nPaste the best one into grit/config.py as CLARK_PARCEL_LAYER, "
          "then run `python -m grit harvest`.")


def cmd_harvest():
    n, meta = pipeline.harvest()
    print(f"harvest status: {meta.get('status')}")
    if meta.get("detail"):
        print(meta["detail"])
    print(f"cards written: {n}")


def cmd_selftest():
    """Verify the transform on a clearly-labeled FIXTURE (not real, not shipped)."""
    fixture_fields = ["APN", "OWNER1", "MAILADDR", "SITUS", "SITUSCITY",
                      "SITUSZIP", "LANDUSE", "TOTVAL", "SALEDATE"]
    mapping = pipeline.build_field_map(fixture_fields)
    feat = {
        "geometry": {"type": "Point", "coordinates": [-115.2, 36.1]},
        "properties": {
            "APN": "138-99-000-001", "OWNER1": "TEST OWNER LLC",
            "MAILADDR": "PO BOX 999 RENO NV", "SITUS": "123 EXAMPLE AVE",
            "SITUSCITY": "LAS VEGAS", "SITUSZIP": "89101",
            "LANDUSE": "SINGLE FAMILY RESIDENTIAL - REROOF NOTED",
            "TOTVAL": 825000, "SALEDATE": "2025-02-15",
        },
    }
    card = pipeline.feature_to_card(feat, mapping, "selftest")
    print("field map:", mapping)
    print("score:", card["score"])
    print("trade_tags:", card["trade_tags"])
    print("signals:")
    for s in card["signals"]:
        print("  -", s)
    print("suggested:", card["suggested_action"])
    assert card["score"] > 0 and card["trade_tags"], "transform failed"

    # ---- 0.105 transforms (offline, fixture only) -------------------------
    from . import tagging, leads, geocode, contractors, capital
    # geocode APN helpers
    assert geocode.norm_apn("138-99-000-001") == "13899000001", "norm_apn failed"
    assert geocode.dash_apn("13899000001") == "138-99-000-001", "dash_apn failed"
    assert geocode.dash_apn("123") is None, "dash_apn should reject non-11-digit"
    # owner-origin parser: a Las Vegas property owned from out of state
    origin = capital.parse_owner_origin("100 N STATE ST, CHICAGO IL 60601")
    assert origin["owner_state"] == "IL" and origin["owner_city"] == "Chicago" \
        and origin["owner_out_of_state"] and origin["owner_origin_market"] == "Chicago, IL", \
        "owner-origin parse failed"
    assert capital.parse_owner_origin("123 S 3RD ST, LAS VEGAS NV 89101")["owner_is_local"], \
        "local NV owner should be flagged local"
    # a permit-style fixture lead owned by out-of-state (Chicago) capital
    permit_card = {
        "source": "clv_permit",
        "entity_type": "LLC", "owner_name": "ACME INVEST LLC",
        "owner_mailing": "100 N STATE ST, CHICAGO IL 60601", "situs_address": "9 TEST ST",
        "city": "HENDERSON", "land_use": "SINGLE FAMILY RESIDENTIAL",
        "assessed_value": 820000, "year_built": 1979, "has_permit": True,
        "permit_count": 2, "contractors": ["ACME ROOFING LLC"],
        "trade_tags": ["roofing"], "last_permit_date": dt_today_iso(),
        "permit_value_total": 35000, "portfolio_size": 6, "cluster_density": 7,
        "temporal_state": "IMMEDIATE", "suggested_action": "Pull contact and confirm intent.",
        "timeline": [{"kind": "PERMIT", "date": dt_today_iso(), "description": "reroof"}],
    }
    # production order: enrich (stamps location dims + origin) THEN tag
    leads.enrich_lead(permit_card)
    tags = tagging.tags_for_card(permit_card)
    print("\n0.105 tags:", ", ".join(tags))
    for must in ("entity:llc", "ownership:absentee", "ownership:investor",
                 "permit:active", "trade:roofing", "value:750k-1m",
                 "monetization:investor-relationship",
                 "origin:out-of-state", "origin:illinois"):
        assert must in tags, f"missing tag {must}"
    # four SEPARATE location dimensions, never collapsed
    assert permit_card["property_city"] == "LAS VEGAS", "CLV property city should be Las Vegas"
    assert permit_card["permit_jurisdiction"] == "City of Las Vegas", "permit jurisdiction wrong"
    assert permit_card["owner_origin_market"] == "Chicago, IL", "owner origin not preserved"
    print("dimensions: property=", permit_card["property_city"],
          "| permit_juris=", permit_card["permit_jurisdiction"],
          "| owner_origin=", permit_card["owner_origin_market"])
    print("jurisdiction:", permit_card["jurisdiction"], "| property:", permit_card["property_type"])
    print("occupancy:", permit_card["occupancy_status"])
    print("WHY THIS MATTERS:\n  " + permit_card["why"])
    assert "active work" in permit_card["why"].lower(), "why-this-matters failed"
    assert "Chicago, IL" in permit_card["why"], "why should surface out-of-state origin"
    ct = contractors.build_contractor_table([permit_card])
    assert ct and ct[0]["name"] == "ACME ROOFING LLC" and ct[0]["permit_count"] == 2, "contractor rollup failed"
    print("contractor leaderboard top:", ct[0]["name"], "->", ct[0]["permit_count"], "permits")
    # capital-flow rollup sees the imported property
    cf = capital.capital_flow([permit_card])
    assert cf["totals"]["imported_properties"] == 1 and cf["by_market"][0]["market"] == "Chicago, IL", \
        "capital-flow rollup failed"
    print("capital flow: imported", cf["totals"]["imported_properties"],
          "from", cf["by_market"][0]["market"])

    # ---- 0.106 transforms: jurisdiction resolution, dates, warehouse, audit --
    from . import geo, warehouse as wh, audit
    assert geo.jurisdiction_for_coord(36.17, -115.14) is not None, "coord resolver failed in valley"
    assert geo.jurisdiction_for_coord(40.0, -80.0) is None, "coord resolver should reject out-of-region"
    # a coordinate-only parcel with a blank city resolves to a SoNV jurisdiction (flagged)
    coord_card = {"source": "clark_gis", "lat": 36.0, "lng": -114.85, "id": "selftest-bc"}
    geo.stamp(coord_card)
    assert coord_card.get("property_jurisdiction") and coord_card.get("jurisdiction_source") == "coordinate", \
        "coordinate jurisdiction not stamped/flagged"
    # date-first fields present on the permit fixture
    assert permit_card.get("primary_date") and permit_card.get("age_days") is not None \
        and permit_card.get("urgency"), "date-first stamping failed"
    assert "urgency:" in " ".join(tags) and "jurisdiction:" in " ".join(tags), "urgency/jurisdiction tags missing"
    # per-record warehouse initialises first/last seen
    store, stats = wh.update([dict(permit_card, id="selftest-1")])
    assert stats["tracked"] >= 1 and stats["new"] >= 1, "warehouse update failed"
    # audit reports build and reflect real shape
    aud = audit.build_audit([dict(permit_card, id="a1")], [], [])
    for k in ("sonv_coverage", "source_inventory", "signal_matrix", "permit_audit",
              "data_quality", "gap_analysis"):
        assert k in aud, f"audit missing {k}"
    assert any(s["status"] == "IMPLEMENTED" for s in aud["signal_matrix"]), "signal matrix empty"
    print("0.106: jurisdiction-resolve + date-first + warehouse + audit OK")

    # ---- 0.107: full-roll enrichment mapping, confidence, denominators -------
    from . import confidence
    attrs = {"PARCELNO": "138-99-000-001", "OWNERNAME": "SMITH JOHN R",
             "SITUSADDR": "9 TEST ST", "SITUSCITY": "LAS VEGAS",
             "TOTLVALUE": "452000", "LANDVAL": "120000", "IMPRVAL": "332000",
             "BLDGSQFT": "2150", "LOTSQFT": "6534", "YEARBLT": "1998",
             "BEDRMS": "4", "BATHS": "3", "USECODE": "110",
             "SALEDATE": "2021-06-15", "SALEPRICE": "415000", "NULLCOL": "0"}
    m = geocode.map_attrs(attrs)
    for f in ("assessed_value", "land_value", "improvement_value", "building_sqft",
              "lot_sqft", "year_built", "bedrooms", "bathrooms", "last_sale_price"):
        assert m.get(f), f"parcel-layer attr mapping missed {f}"
    blank = {"parcel_apn": "13899000001", "assessed_value": None}
    rep = geocode.enrich_from_parcels([blank], {"13899000001": {"ll": (36.1, -115.1), "attrs": attrs}})
    assert rep["cards_enriched"] == 1 and blank.get("assessed_value") == "452000" \
        and blank.get("enriched_from") == "parcel_layer", "full-roll enrichment failed"
    # confidence annotation classes
    confidence.annotate(permit_card)
    conf = permit_card.get("confidence", {})
    assert conf.get("authoritative", 0) >= 1 and "score" in conf, "confidence annotation failed"
    assert permit_card["field_confidence"].get("permit_count", {}).get("c") == "authoritative", \
        "permit field should be authoritative"
    # audit's new sections
    aud2 = audit.build_audit([dict(permit_card, id="x1"), dict(coord_card, id="x2", owner_name="ACME LLC", assessed_value=300000)], [], [])
    for k in ("denominators", "confidence", "ownership_networks"):
        assert k in aud2, f"audit missing {k}"
    assert "pct" in aud2["confidence"] and aud2["confidence"]["pct"].get("unknown") is not None, "confidence dist failed"
    print("0.107: full-roll enrichment + confidence + denominators + networks OK")

    # ---- 0.109: free data saturation connector (pure-function tests) ---------
    from . import free_sources as fsrc
    ce_feats = [{"attrs": {"PARCELNO": "138-11-111-001", "SITUS": "9 A ST",
                           "VIOLATIONTYPE": "Property Maintenance", "CASESTATUS": "Open",
                           "OPENDATE": "2025-09-01"}, "ll": (36.2, -115.2)},
                {"attrs": {"APN": "16022002003", "FULLADDRESS": "5 B AVE",
                           "TYPE": "Trailer/RV", "STATUS": "Closed",
                           "DATE": 1693526400000}, "ll": (36.1, -115.1)}]
    ce = fsrc.code_enforcement_records(ce_feats)
    assert len(ce) == 2 and ce[0]["apn"] == "13811111001" and ce[0]["vtype"], "code-enf mapping failed"
    assert ce[1]["date"] and ce[1]["date"].startswith("2023"), "epoch-ms date parse failed"
    bl = fsrc.business_license_records([{"attrs": {"PARCELNO": "138-11-111-001",
                           "BUSINESSNAME": "ACME LLC", "STATUS": "Active",
                           "BUSINESSACTIVITY": "Retail", "ISSUEDATE": "2024-01-02"}, "ll": (36.2, -115.2)}])
    assert bl and bl[0]["name"] == "ACME LLC" and bl[0]["activity"] == "Retail", "biz-license mapping failed"
    evs = fsrc.to_events(ce, "VIOLATION", "clv_code_enforcement")
    assert evs and evs[0].kind == "VIOLATION" and evs[0].parcel_apn == "13811111001", "event build failed"
    seeds = fsrc.seed_cards_from_violations(ce, existing_apns={"16022002003"})
    assert len(seeds) == 1 and seeds[0]["parcel_apn"] == "13811111001" \
        and seeds[0]["code_enforcement_open"] and seeds[0]["source"] == "code_enforcement", "seed-lead failed"
    test_cards = [{"parcel_apn": "16022002003"}, {"parcel_apn": "138-11-111-001"}]
    applied = fsrc.apply_signals(test_cards, ce, bl)
    assert applied["code_enforcement_card_hits"] == 2 and applied["business_license_card_hits"] == 1, "apply_signals failed"
    assert test_cards[1].get("business_license_active") and test_cards[1].get("code_enforcement_open"), "flags not set"
    # scoring reflects the distress signal transparently
    from .pipeline import score_card as _score
    sc = _score({"owner_name": "X", "code_enforcement_open": True, "entity_type": "PERSON"})
    assert any("code-enforcement" in s for s in sc["signals"]), "distress not scored"
    print("0.109: free-saturation connector (code-enf + business + events + seeds + scoring) OK")

    # ---- 0.110: Henderson permits (Socrata) mapping --------------------------
    from . import henderson as hend
    from . import clv_permits as clv_permits_mod
    from .pipeline import permits_to_cards
    hrow = {"permitnumber": "BOTH2025372313", "permittype": "BLDG - Wall",
            "workclass": "Post Hole", "permitstatus": "Active - Issued",
            "issuedate": "2026-01-12T00:01:00.000", "applydate": "2025-12-31T16:12:00.000",
            "valuationtotal": "296.63", "parcelnumber": "16034710001",
            "parceladdressnumber": "920", "parceladdressstreet": "BOULDER",
            "parceladdressstreettype": "HWY", "parceladdresscity": "HENDERSON",
            "ownername": "P N II INC", "owneraddress": "7255 S TENAYA WAY LAS VEGAS NV 89113",
            "professionalname": "HIRSCHI IRON LLC", "professionalstatelicnbr": "0088266",
            "gisx": "-114.928970", "gisy": "36.078631",
            "permitsquarefootagetotal": "1200", "permitdescription": "Iron fence"}
    hp = hend._row_to_permit(hrow)
    assert hp["record"] == "BOTH2025372313" and hp["apn"] == "16034710001", "henderson apn/record failed"
    assert hp["contractor"] == "HIRSCHI IRON LLC" and hp["license"] == "0088266", "henderson contractor/license failed"
    assert hp["date"] == "2026-01-12" and hp["lat"] and hp["lng"], "henderson date/coords failed"
    assert hp["owner_name"] == "P N II INC" and hp["city"] == "HENDERSON", "henderson owner/city failed"
    hcards = permits_to_cards([hp], "henderson_permit")
    assert hcards and hcards[0]["source"] == "henderson_permit" and hcards[0]["parcel_apn"] == "16034710001", "henderson card failed"
    hev = clv_permits_mod.to_events([hp], source="henderson_permit")
    assert hev and hev[0].kind == "PERMIT" and hev[0].source == "henderson_permit", "henderson events failed"
    print("0.110: Henderson permits (Socrata) mapping + cards + events OK")

    # ---- 0.111: permit-signal classification (real-data derived) -------------
    from . import signals as _sig111
    sigcard = {"timeline": [
        {"kind": "PERMIT", "description": "PW - Barricade Permit Barricade"},
        {"kind": "PERMIT", "description": "Fire - Suppression/Extinguishing Systems"},
        {"kind": "PERMIT", "description": "BLDG - Dwelling Townhouse - Production"}],
        "trade_tags": ["solar"]}
    found = _sig111.classify(sigcard)
    for need in ("public_works", "fire_life_safety", "new_construction", "solar"):
        assert need in found, f"permit-signal classify missed {need}"
    assert "permit_signals" in sigcard, "permit_signals not stored"
    cc = _sig111.counts([sigcard, {"permit_signals": ["public_works"]}])
    assert cc["public_works"] == 2 and cc["fire_life_safety"] == 1, "permit-signal counts failed"
    print("0.111: permit-signal classification (public-works + fire + new-construction + solar) OK")

    # ---- 0.112: contactability engine ---------------------------------------
    from . import contact as _contact
    assert _contact.norm_phone("7025551234") == "(702) 555-1234", "phone norm failed"
    assert _contact.norm_phone("1-702-555-1234") == "(702) 555-1234", "phone 11-digit norm failed"
    assert _contact.norm_phone("000") is None and _contact.norm_phone("123") is None, "bad phone not rejected"
    cphone = {"owner_name": "P N II INC", "entity_type": "LLC", "owner_mailing": "7255 S TENAYA WAY",
              "contractors": ["HIRSCHI IRON LLC"], "contractor_phone": "7025551234",
              "contractor_license": "0088266", "permit_signals": ["new_construction"],
              "age_days": 10, "score": 80, "property_city": "HENDERSON"}
    r = _contact.classify(cphone)
    assert r["tier"] == "phone" and r["phone"] == "(702) 555-1234" and r["phone_owner"] == "contractor", "tier/phone failed"
    assert r["reachable"] and r["score"] >= 80, "reachable/score failed"
    assert any(ch["type"] == "license" for ch in r["channels"]), "license channel missing"
    assert "HIRSCHI IRON LLC" in r["summary"] and "(702) 555-1234" in r["summary"], "summary missing contact"
    cmail_card = {"owner_name": "LOPEZ ANTHONY", "owner_mailing": "464 SELDON", "age_days": 400}
    cmail = _contact.classify(cmail_card)
    assert cmail["tier"] == "mail" and not cmail["phone"], "mail tier failed"
    cname_card = {"owner_name": "DOE JANE"}
    cname = _contact.classify(cname_card)
    assert cname["tier"] == "name" and not cname["reachable"], "name tier failed"
    st = _contact.stats([cphone, cmail_card, cname_card])
    assert st["with_phone"] == 1 and st["reachable"] == 2, "contact stats failed"
    print("0.112: contactability engine (tiers + phone norm + channels + summary + stats) OK")

    # ---- 0.113: ArcGIS item-id suffix fix + per-jurisdiction contact density --
    from . import free_sources as _fs
    assert _fs._split_item_id("6a371d1a491a4a0794578b031859c768_0") == ("6a371d1a491a4a0794578b031859c768", "0"), "_0 split failed"
    assert _fs._split_item_id("b86e999491454c4290af161192ad0eba_3") == ("b86e999491454c4290af161192ad0eba", "3"), "_3 split failed"
    assert _fs._split_item_id("f48d19416d5546e5b9ee12f9746ecaa9") == ("f48d19416d5546e5b9ee12f9746ecaa9", "0"), "bare id changed (regression)"
    jcards = [{"property_jurisdiction": "City of Henderson", "contact": {"tier": "phone"}},
              {"property_jurisdiction": "City of Henderson", "contact": {"tier": "mail"}},
              {"property_jurisdiction": "City of Las Vegas", "contact": {"tier": "name"}}]
    jr = _contact.by_jurisdiction(jcards)
    assert jr[0]["jurisdiction"] == "City of Henderson" and jr[0]["phone"] == 1 and jr[0]["reachable"] == 2, "jurisdiction breakdown failed"
    print("0.113: item-id _N suffix fix (crime + Henderson biz) + per-jurisdiction contact density OK")

    # ---- 0.114: contractor-graph contact propagation -------------------------
    g1 = {"contractors": ["Sandstone Electric Inc."], "contractor_phone": "7022944497",
          "contractor_license": "0012345", "source": "henderson_permit"}
    g2 = {"contractors": ["SANDSTONE ELECTRIC LLC"], "source": "clv_permit"}   # same co, no phone
    g3 = {"contractor_license": "0012345", "source": "clark_gis"}              # match by license
    g4 = {"contractors": ["Totally Different Co"], "source": "clv_permit"}     # no match
    rep = _contact.propagate_contractor_contacts([g1, g2, g3, g4])
    assert g2.get("contractor_phone") == "(702) 294-4497", "name-propagation failed"
    assert g2.get("contractor_phone_source") == "contractor-graph", "provenance not marked"
    assert g3.get("contractor_phone") == "(702) 294-4497", "license-propagation failed"
    assert not g4.get("contractor_phone"), "propagated to a non-matching lead"
    assert rep["phone_filled"] == 2, f"expected 2 phones filled, got {rep['phone_filled']}"
    print("0.114: contractor-graph contact propagation (name + license match, provenance) OK")

    print("\nselftest OK (fixture only -- never written to docs/data)")


def dt_today_iso():
    import datetime as _dt
    return _dt.date.today().isoformat()


def cmd_rebuild(argv):
    """Re-derive the 0.105 intelligence layer (clusters, operators, universal
    tags, WHY-THIS-MATTERS, contractor leaderboard, coverage + category matrix,
    append-only ledger) from the EXISTING harvested data -- NO network harvest.

    Use it to apply changes to tag/why/contractor/coverage logic instantly
    without re-pulling sources. Reads docs/data/{cards,events}.json, recomputes,
    and rewrites cards.json + operators/contractors/coverage. Real data only:
    it never invents fields, only restates what was already harvested.
    """
    import json
    from . import (events as events_mod, entities, tagging, leads as leads_mod,
                   contractors as contractors_mod, coverage as coverage_mod)
    cd = pipeline._read_json(config.CARDS_FILE)
    if not cd or not cd.get("cards"):
        print("No cards.json to rebuild from -- run `harvest` first."); return
    cards = cd["cards"]
    events = events_mod.load_existing()
    print(f"rebuilding intelligence over {len(cards)} cards / {len(events)} events (offline)...")

    events_mod.join_to_cards(cards, events)
    pipeline.assign_cluster_density(cards)
    operators = entities.build_operator_graph(cards)
    cards = [pipeline.score_card(c) for c in cards]
    cards.sort(key=lambda c: c["score"], reverse=True)
    for c in cards:
        leads_mod.enrich_lead(c)
        c["tags"] = tagging.tags_for_card(c)
    from . import contact as _contact_mod
    contact_graph = _contact_mod.propagate_contractor_contacts(cards)
    for c in cards:
        _contact_mod.classify(c)
    print(f"  contact-graph: +{contact_graph['phone_filled']} phones, "
          f"+{contact_graph['license_filled']} licenses, +{contact_graph['address_filled']} addresses")
    from . import warehouse as warehouse_mod
    wh_store, wh_stats = warehouse_mod.update(cards)   # append-only per-record history
    warehouse_mod.save(wh_store)
    for c in cards:
        warehouse_mod.stamp(c, wh_store)               # first_seen / last_seen / last_updated
        if not c.get("harvested_at"):
            c["harvested_at"] = c.get("last_seen")
    print(f"  warehouse: {wh_stats['tracked']} records tracked "
          f"({wh_stats['new']} new, {wh_stats['changed']} changed, {wh_stats['dormant']} dormant)")
    contractor_table = contractors_mod.build_contractor_table(cards)

    harvest = cd.get("harvest", {})
    harvest["density"] = {**harvest.get("density", {}),
                          "cards_total": len(cards),
                          "cards_with_owner": sum(1 for c in cards if c.get("owner_name")),
                          "cards_mapped": sum(1 for c in cards if c.get("lat") and c.get("lng")),
                          "operators_detected": len(operators),
                          "contractors": len(contractor_table)}
    pipeline._write_cards(config.CARDS_FILE, {
        "generated_at": cd.get("generated_at"), "version": config.VERSION,
        "harvest": harvest, "count": len(cards),
        "cards": [pipeline._slim_card(c) for c in cards]})
    pipeline._write(f"{config.DATA_DIR}/operators.json", {
        "generated_at": cd.get("generated_at"), "version": config.VERSION,
        "count": len(operators),
        "portfolios_2plus": sum(1 for o in operators if o["parcel_count"] >= 2),
        "operators": operators})
    pipeline._write(config.CONTRACTORS_FILE, {
        "generated_at": cd.get("generated_at"), "version": config.VERSION,
        "count": len(contractor_table), "contractors": contractor_table})
    health = (pipeline._read_json(config.HEALTH_FILE) or {}).get("sources", [])
    geo_rep = harvest.get("geocode")
    ev_dicts = [pipeline.dc_asdict(e) for e in events]
    cov, _ = coverage_mod.build(cards, ev_dicts, health, contractor_table, geo_rep)
    pipeline._write(config.COVERAGE_FILE, cov)

    mapped = sum(1 for c in cards if c.get("lat") and c.get("lng"))
    print(f"  rebuilt: {len(cards)} cards ({mapped} mapped), {len(operators)} operators, "
          f"{len(contractor_table)} contractors")
    print(f"  wrote cards.json, operators.json, contractors.json, coverage.json + ledger")


def cmd_permits_clv(argv):
    """Pull LIVE City of Las Vegas permits from the ArcGIS Hub open-data API and
    merge PERMIT events. Cloud-native -- no residential IP, no ViewState. Run it
    anywhere (your machine OR the GitHub runner). Reports recency + volume so you
    see immediately whether the feed is live and current."""
    from . import clv_permits, events as events_mod
    days = config.PERMIT_DAYS_BACK
    if "--days" in argv:
        try: days = int(argv[argv.index("--days") + 1])
        except Exception: pass
    print(f"Pulling City of Las Vegas permits (last {days} days) via ArcGIS Hub...")
    new_events, report = clv_permits.harvest_clv_permits(days_back=days)
    print(f"  dataset : {report['host']}/resource/{report['dataset']}")
    if report.get("status") == "needs_config":
        print("  NOT CONFIGURED: paste the CLV Building Permits FeatureServer url into\n"
              "  config.CLV_PERMITS_FEATURESERVER. Portal: opendataportal-lasvegas.\n"
              "  opendata.arcgis.com/datasets/building-permits -> API Resources.")
        return
    if report.get("error"):
        print(f"  ERROR   : {report['error']}")
        print("  If this is a 404/None, the dataset id may have moved -- check "
              "config.CLV_PERMITS_FEATURESERVER (paste the FeatureServer layer url).")
        return
    print(f"  columns : {report.get('columns')}")
    print(f"  mapping : {report.get('mapping')}")
    print(f"  rows    : {report['rows']}   newest permit: {report['newest']}")
    traded = sum(1 for e in new_events if e.trade_tag)
    from collections import Counter
    mix = Counter(e.trade_tag for e in new_events if e.trade_tag)
    print(f"  events  : {len(new_events)} PERMIT ({traded} trade-tagged: {dict(mix)})")
    if not new_events:
        return
    existing = events_mod.load_existing()
    seen = {(e.kind, e.date, e.description) for e in existing}
    merged = list(existing) + [e for e in new_events if (e.kind, e.date, e.description) not in seen]
    events_mod.write(merged)
    print(f"\n  + merged into {config.EVENTS_FILE} ({len(merged)} total events). "
          f"Next harvest joins them to cards; fresh permits score IMMEDIATE.")


def cmd_permits(argv):
    """Ingest recent Clark County permits from Accela (run from a residential
    Vegas IP -- the cloud runner gets 403d). Searches permits issued in the last
    N days, parses the results grid, and merges PERMIT events into events.json.
    On a parse miss it saves the raw HTML for one-pass calibration -- never fakes."""
    from . import events as events_mod
    days = 14
    if "--days" in argv:
        try: days = int(argv[argv.index("--days") + 1])
        except Exception: pass
    if "--capture-only" in argv:
        print("Capturing Accela search page only...")
        for r in permits.capture_search_form():
            print(" ", r)
        return
    print(f"Ingesting Clark County permits issued in the last {days} days "
          f"(residential IP required)...")
    new_events, report = permits.harvest_permits(days_back=days)
    print("  search:", report.get("search_meta"))
    print("  step  :", report.get("step"), "| rows:", report.get("rows"),
          ("| error: " + report["error"]) if report.get("error") else "")
    if not new_events:
        if report.get("saved"):
            print(f"\n  No permit rows parsed. Raw HTML saved under {report['saved']}.")
            print("  Upload aca_results.html (or aca_search_page.html) and the "
                  "parser/field-map gets calibrated in one pass. No fake data is "
                  "ever published.")
        return
    # merge with existing events, de-dupe on (kind, date, description)
    existing = events_mod.load_existing()
    seen = {(e.kind, e.date, e.description) for e in existing}
    merged = list(existing) + [e for e in new_events
                               if (e.kind, e.date, e.description) not in seen]
    events_mod.write(merged)
    permit_n = sum(1 for e in new_events)
    traded = sum(1 for e in new_events if e.trade_tag)
    print(f"\n  + {permit_n} PERMIT events ({traded} trade-tagged) merged into "
          f"{config.EVENTS_FILE} ({len(merged)} total).")
    print("  Commit + push. Next harvest joins them to cards by address/APN; "
          "fresh permits score IMMEDIATE and rise to the top.")


def cmd_enrich(argv):
    """Capture a few live Assessor parcel-detail responses for calibration.
    Reads top APNs from the latest harvest and saves raw HTML to docs/data/."""
    import json
    n = 3
    if "--sample" in argv:
        try: n = int(argv[argv.index("--sample") + 1])
        except (IndexError, ValueError): pass
    try:
        cards = json.load(open(config.CARDS_FILE)).get("cards", [])
    except Exception:
        cards = []
    apns = [c["parcel_apn"] for c in cards if c.get("parcel_apn")][:n]
    if not apns:
        print("No APNs in cards.json yet -- run `harvest` first."); return
    print(f"Capturing {len(apns)} Assessor samples (calibration): {apns}")
    for r in assessor.capture_samples(apns):
        print(" ", r)
    print("\nSaved raw responses under docs/data/assessor_samples/. "
          "Upload one so the exact parser can be written -- no parsed data is "
          "trusted until then (no fake data).")


def cmd_coverage(argv):
    """Print the permit-completeness table + category health matrix from the
    last build (docs/data/coverage.json). Read-only; no network."""
    import json
    cov = pipeline._read_json(config.COVERAGE_FILE)
    if not cov:
        print("No coverage.json yet -- run `rebuild` or `harvest` first."); return
    h = cov.get("headline", {})
    print(f"COVERAGE  (generated {cov.get('generated_at','?')})")
    print(f"  {h.get('leads',0)} leads | {h.get('mapped',0)} mapped | "
          f"{h.get('permit_events',0)} permit events | {h.get('contractors',0)} contractors "
          f"| {h.get('tagged_pct',0)}% tagged")
    pc = cov.get("permits", {})
    print("\nPERMIT COMPLETENESS BY JURISDICTION (top 12)")
    print(f"  {'jurisdiction':<22}{'parcels':>9}{'permits':>9}{'mapped':>8}"
          f"{'fresh(d)':>9}{'conf':>6}  newest")
    for r in pc.get("by_jurisdiction", [])[:12]:
        print(f"  {r['jurisdiction']:<22}{r['parcels']:>9}{r['permits']:>9}"
              f"{r['mapped']:>8}{str(r['freshness_days']):>9}{r['confidence']:>6}"
              f"  {r.get('newest') or '-'}")
    t = pc.get("total", {})
    if t:
        print(f"  {'TOTAL ('+str(t.get('jurisdictions_with_data',0))+' juris)':<22}"
              f"{t.get('permit_parcels',0):>9}{t.get('permit_events_stored',0):>9}"
              f"{t.get('mapped',0):>8}{str(t.get('freshness_days','-')):>9}")
    print("\nCATEGORY HEALTH MATRIX")
    print(f"  {'category':<16}{'status':<10}{'vol':>7}{'fresh':>10}{'conf':>6}  coverage")
    for r in cov.get("categories", []):
        print(f"  {r['category']:<16}{r['status']:<10}{str(r.get('volume','-')):>7}"
              f"{str(r.get('freshness','-')):>10}{str(r.get('confidence','-')):>6}"
              f"  {r.get('coverage','')}")
    w = cov.get("warehouse", {})
    print(f"\nWAREHOUSE  append_only={w.get('append_only')} | "
          f"{w.get('event_total',0)} events | {w.get('ledger_entries',0)} ledger entries")


def cmd_contractors(argv):
    """Print the contractor leaderboard from docs/data/contractors.json.
    Read-only; no network."""
    n = 25
    if "--top" in argv:
        try: n = int(argv[argv.index("--top") + 1])
        except (IndexError, ValueError): pass
    data = pipeline._read_json(config.CONTRACTORS_FILE)
    if not data or not data.get("contractors"):
        print("No contractors.json yet -- run `rebuild` or `harvest` first."); return
    rows = data["contractors"][:n]
    print(f"CONTRACTOR LEADERBOARD  ({data.get('count',len(rows))} total, top {len(rows)})")
    print(f"  {'#':>3} {'contractor':<34}{'permits':>8}{'recent':>7}"
          f"{'sites':>6}{'top trade':>14}{'share%':>7}  top city")
    for i, c in enumerate(rows, 1):
        print(f"  {i:>3} {(c['name'][:33]):<34}{c['permit_count']:>8}"
              f"{c['recent_count']:>7}{c['job_sites']:>6}"
              f"{(c.get('top_trade') or '-'):>14}{c.get('trade_share_pct',0):>7}"
              f"  {c.get('top_city') or '-'}")


def cmd_checksize(argv=None):
    """Drag-and-drop safety guard (0.111). GitHub's web uploader rejects any single
    file > 25 MB. Walk the repo, flag anything that would break a manual upload, and
    exit non-zero if so. Generated data files (docs/data/*) are regenerated by the
    harvest, so the fix for an oversize one is to exclude it from the manual upload
    and let the GitHub Action commit it (git push is not bound by the 25 MB limit)."""
    LIMIT = pipeline.MAX_DRAGDROP_MB
    big, warn = [], []
    for dirpath, dirs, files in os.walk("."):
        if any(skip in dirpath for skip in (".git", "__pycache__", "node_modules")):
            continue
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                mb = os.path.getsize(p) / 1048576
            except OSError:
                continue
            if mb >= LIMIT:
                big.append((mb, p))
            elif mb >= LIMIT * 0.8:
                warn.append((mb, p))
    for mb, p in sorted(warn, reverse=True):
        print(f"  NEAR LIMIT  {mb:5.1f} MB  {p}")
    for mb, p in sorted(big, reverse=True):
        gen = "/docs/data/" in p.replace("\\", "/")
        hint = " (generated -- exclude from manual upload; the Action regenerates it)" if gen else ""
        print(f"  OVER {LIMIT}MB  {mb:5.1f} MB  {p}{hint}")
    if big:
        print(f"\nFAIL: {len(big)} file(s) exceed the {LIMIT} MB drag-and-drop limit.")
        sys.exit(1)
    print(f"OK: every file is under the {LIMIT} MB drag-and-drop limit"
          + (f" ({len(warn)} approaching)." if warn else "."))


def main(argv):
    cmds = {"health": cmd_health, "discover": cmd_discover,
            "harvest": cmd_harvest, "selftest": cmd_selftest, "enrich": cmd_enrich,
            "permits": cmd_permits, "permits-clv": cmd_permits_clv,
            "rebuild": cmd_rebuild, "coverage": cmd_coverage,
            "checksize": cmd_checksize,
            "contractors": cmd_contractors}
    if len(argv) < 2 or argv[1] not in cmds:
        print(__doc__)
        return 1
    if argv[1] in ('enrich', 'permits', 'permits-clv', 'rebuild',
                   'coverage', 'contractors'):
        cmds[argv[1]](argv)
    else:
        cmds[argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
