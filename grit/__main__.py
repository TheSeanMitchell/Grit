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
    pipeline._write(config.CARDS_FILE, {
        "generated_at": cd.get("generated_at"), "version": config.VERSION,
        "harvest": harvest, "count": len(cards),
        "cards": [{k: v for k, v in c.items() if k != "raw"} for c in cards]})
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


def main(argv):
    cmds = {"health": cmd_health, "discover": cmd_discover,
            "harvest": cmd_harvest, "selftest": cmd_selftest, "enrich": cmd_enrich,
            "permits": cmd_permits, "permits-clv": cmd_permits_clv,
            "rebuild": cmd_rebuild, "coverage": cmd_coverage,
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
