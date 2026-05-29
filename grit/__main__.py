"""
GRIT CLI.

  python -m grit health     probe every registered source, write health.json
  python -m grit discover   walk the Clark County ArcGIS server, list services
                            and the REAL fields of likely parcel layers
  python -m grit harvest    health + harvest the live API source -> cards.json
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
    print("\nselftest OK (fixture only -- never written to docs/data)")


def cmd_permits_clv(argv):
    """Pull LIVE City of Las Vegas permits from the Socrata open-data API and
    merge PERMIT events. Cloud-native -- no residential IP, no ViewState. Run it
    anywhere (your machine OR the GitHub runner). Reports recency + volume so you
    see immediately whether the feed is live and current."""
    from . import socrata, events as events_mod
    days = config.PERMIT_DAYS_BACK
    if "--days" in argv:
        try: days = int(argv[argv.index("--days") + 1])
        except Exception: pass
    print(f"Pulling City of Las Vegas permits (last {days} days) via Socrata...")
    new_events, report = socrata.harvest_clv_permits(days_back=days)
    print(f"  dataset : {report['host']}/resource/{report['dataset']}")
    if report.get("error"):
        print(f"  ERROR   : {report['error']}")
        print("  If this is a 404/None, the dataset id may have moved -- check "
              "the portal and update DATASETS['permits'] in grit/socrata.py.")
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


def main(argv):
    cmds = {"health": cmd_health, "discover": cmd_discover,
            "harvest": cmd_harvest, "selftest": cmd_selftest, "enrich": cmd_enrich,
            "permits": cmd_permits, "permits-clv": cmd_permits_clv}
    if len(argv) < 2 or argv[1] not in cmds:
        print(__doc__)
        return 1
    if argv[1] in ('enrich', 'permits', 'permits-clv'):
        cmds[argv[1]](argv)
    else:
        cmds[argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
