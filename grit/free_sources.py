"""
Free data saturation (Alpha 0.109).

Pulls every additional FREE public signal feed GRIT can reach and folds it into
the warehouse: City of Las Vegas Code Enforcement Violations (per-property
distress), CLV Business Licenses (commercial/entity activity), and optionally
LVMPD crime (area signal). All live on the same ArcGIS Hub platform as the permit
feed, so this reuses the proven pattern.

Design principles:
  * Resolve each dataset's live FeatureServer URL from its ArcGIS Online item id
    at harvest time -- never hardcode a service name that could move.
  * Pull is paginated and capped; field mapping is hint-based (outFields=*), so a
    renamed column degrades gracefully instead of breaking.
  * Every network call is wrapped: a dead/blocked source returns 0 rows and a
    status, and the harvest continues. No fabricated records, ever.
  * Code-enforcement records with an APN we don't already hold become NEW distress
    leads; records that match an existing lead attach as signals/events.

This module's pure functions (mapping, event/seed/signal building) are unit-tested
offline; only the two network functions (resolve_layer, _pull) require live access
and they fail safe.
"""
import json
import re
import time
import urllib.parse
import urllib.request

from . import config

_UA = {"User-Agent": "GRIT/0.109 (+https://github.com/grit) free-sources"}
_AGOL_ITEM = "https://www.arcgis.com/sharing/rest/content/items/{id}?f=json"

FIELD_HINTS = {
    "apn":      ["parcelno", "parcel", "apn", "pcl", "parcel_no", "parcelnumber", "pin"],
    "address":  ["fulladdress", "situs", "address", "addr", "location", "site_address",
                 "streetaddress", "propertyaddress"],
    "date":     ["opendate", "violationdate", "casedate", "issuedate", "recordeddate",
                 "date", "opened", "createddate", "dateopened", "issued", "licensedate",
                 "applicationdate", "incidentdate", "eventdate", "occurred"],
    "status":   ["casestatus", "status", "state", "licensestatus", "dispostion",
                 "disposition", "current_status"],
    "vtype":    ["violationtype", "violation", "casetype", "type", "code", "description",
                 "codedescription", "naturecode", "offense", "crimetype", "category"],
    "bizname":  ["businessname", "business", "dba", "name", "legalname", "licensee"],
    "activity": ["businessactivity", "activity", "naics", "category", "licensetype",
                 "business_type", "classification"],
}


def _http_json(url, params=None, timeout=45):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def resolve_layer(item_id):
    """Resolve an ArcGIS Online item id to a queryable layer URL. Returns the URL
    or None. A feature-layer item's `url` is the layer; a service item's `url` is
    the FeatureServer root, so we append /0. Fails safe (returns None)."""
    if not item_id:
        return None
    try:
        meta = _http_json(_AGOL_ITEM.format(id=item_id))
    except Exception:  # noqa: BLE001
        return None
    url = (meta.get("url") or "").rstrip("/")
    if not url:
        return None
    low = url.lower()
    if low.endswith("featureserver") or low.endswith("mapserver"):
        url += "/0"
    return url


def _centroid(geom):
    if not geom:
        return None, None
    if "x" in geom and "y" in geom:
        return geom.get("y"), geom.get("x")
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Point" and c:
        return c[1], c[0]
    if t in ("Polygon", "MultiPolygon") and c:
        pts = c[0][0] if t == "MultiPolygon" else c[0]
        if pts:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            return sum(ys) / len(ys), sum(xs) / len(xs)
    return None, None


def _pull(layer_url, max_records=4000, page=2000, where="1=1", timeout=45):
    """Paginate a FeatureServer layer -> list of {"attrs":..., "ll":(lat,lng)}.
    Capped at max_records. Fails safe (returns what it has)."""
    out, offset = [], 0
    base = layer_url.rstrip("/") + "/query"
    while len(out) < max_records:
        params = {"where": where, "outFields": "*", "returnGeometry": "true",
                  "outSR": "4326", "f": "geojson",
                  "resultOffset": str(offset),
                  "resultRecordCount": str(min(page, max_records - len(out)))}
        try:
            data = _http_json(base, params, timeout=timeout)
        except Exception:  # noqa: BLE001
            break
        feats = data.get("features", []) or []
        if not feats:
            break
        for f in feats:
            props = f.get("properties") or f.get("attributes") or {}
            lat, lng = _centroid(f.get("geometry"))
            out.append({"attrs": props, "ll": (lat, lng)})
        if len(feats) < page:
            break
        offset += len(feats)
        time.sleep(getattr(config, "GEOCODE_DELAY", 0.15))
    return out[:max_records]


def _f(attrs, key):
    """Hint-based field lookup (exact, then substring), skipping null sentinels."""
    hints = FIELD_HINTS.get(key, [])
    low = {str(k).lower(): k for k in attrs}
    for h in hints:
        if h in low:
            v = attrs[low[h]]
            if v not in (None, "", " ", "null", "<Null>"):
                return v
    for h in hints:
        for lk, orig in low.items():
            if h in lk:
                v = attrs[orig]
                if v not in (None, "", " ", "null", "<Null>"):
                    return v
    return None


def _digits(apn):
    return "".join(ch for ch in str(apn or "") if ch.isdigit())


def _date(v):
    """Normalize a date/epoch-ms to ISO yyyy-mm-dd (best effort)."""
    if v in (None, ""):
        return None
    try:
        n = float(v)
        if n > 1e11:  # epoch milliseconds
            return time.strftime("%Y-%m-%d", time.gmtime(n / 1000.0))
    except (TypeError, ValueError):
        pass
    s = str(v)
    return s[:10] if len(s) >= 10 else s


def code_enforcement_records(features):
    recs = []
    for f in features:
        a = f["attrs"]
        recs.append({"apn": _digits(_f(a, "apn")), "address": _f(a, "address"),
                     "date": _date(_f(a, "date")), "status": _f(a, "status"),
                     "vtype": _f(a, "vtype"), "lat": f["ll"][0], "lng": f["ll"][1]})
    return [r for r in recs if r["apn"] or r["address"]]


def business_license_records(features):
    recs = []
    for f in features:
        a = f["attrs"]
        recs.append({"apn": _digits(_f(a, "apn")), "address": _f(a, "address"),
                     "date": _date(_f(a, "date")), "status": _f(a, "status"),
                     "name": _f(a, "bizname"), "activity": _f(a, "activity"),
                     "lat": f["ll"][0], "lng": f["ll"][1]})
    return [r for r in recs if r["apn"] or r["address"]]


def _is_open(status):
    return str(status or "").strip().lower() in ("open", "active", "in progress",
                                                 "pending", "1", "true", "violation")


def to_events(records, kind, source):
    from .events import Event
    evs = []
    for r in records:
        if kind == "VIOLATION":
            desc = f"code enforcement: {r.get('vtype') or 'violation'}" + \
                   (f" [{r['status']}]" if r.get("status") else "")
        elif kind == "BUSINESS_LICENSE":
            desc = f"business license: {r.get('name') or 'license'}" + \
                   (f" — {r['activity']}" if r.get("activity") else "") + \
                   (f" [{r['status']}]" if r.get("status") else "")
        else:
            desc = f"{kind.lower()}: {r.get('vtype') or ''}".strip()
        evs.append(Event(kind=kind, date=r.get("date") or "", source=source,
                         parcel_apn=r.get("apn") or None, address=r.get("address"),
                         description=desc, lat=r.get("lat"), lng=r.get("lng"), raw=r))
    return evs


def seed_cards_from_violations(records, existing_apns):
    """Code-enforcement records on parcels we don't already hold become NEW
    distress leads (a code violation is a motivated-seller signal)."""
    seeds, seen = [], set()
    for r in records:
        apn = r.get("apn")
        if not apn or apn in existing_apns or apn in seen:
            continue
        seen.add(apn)
        seeds.append({
            "id": f"code_enforcement:{apn}", "source": "code_enforcement",
            "parcel_apn": apn, "situs_address": r.get("address"),
            "owner_name": None, "entity_type": "UNKNOWN", "trade_tags": [],
            "lat": r.get("lat"), "lng": r.get("lng"), "contractors": [],
            "permit_count": 0, "has_permit": False,
            "code_enforcement_open": _is_open(r.get("status")),
            "code_enforcement_type": r.get("vtype"),
            "distress_signal": "code-enforcement"})
    return seeds


def _norm_addr(s):
    """Normalize a street address for fuzzy joining: uppercase, drop unit/suite,
    strip the city/state/zip tail, collapse whitespace and punctuation."""
    if not s:
        return ""
    a = str(s).upper()
    a = re.split(r"\b(STE|SUITE|UNIT|APT|#|BLDG)\b", a)[0]
    a = re.sub(r",.*$", "", a)                       # drop ", LAS VEGAS NV 89..."
    a = re.sub(r"\b(NV|NEVADA)\b.*$", "", a)
    a = re.sub(r"\b\d{5}(-\d{4})?\b", "", a)          # strip zip
    a = re.sub(r"[^A-Z0-9 ]", " ", a)
    return " ".join(a.split())


def apply_signals(cards, ce_records, bl_records):
    """Attach free-source signals to cards. Joins by APN first, then by normalized
    street address (business licenses carry an address but no APN). Mutates cards."""
    def index(records):
        by_apn, by_addr = {}, {}
        for r in records:
            if r.get("apn"):
                by_apn.setdefault(r["apn"], []).append(r)
            na = _norm_addr(r.get("address"))
            if na:
                by_addr.setdefault(na, []).append(r)
        return by_apn, by_addr
    ce_apn, ce_addr = index(ce_records)
    bl_apn, bl_addr = index(bl_records)
    ce_hits = bl_hits = 0
    for c in cards:
        apn = _digits(c.get("parcel_apn"))
        na = _norm_addr(c.get("situs_address"))
        ce = (ce_apn.get(apn) if apn else None) or (ce_addr.get(na) if na else None)
        if ce:
            c["code_enforcement_open"] = any(_is_open(r.get("status")) for r in ce)
            c["code_enforcement_type"] = ce[0].get("vtype") or c.get("code_enforcement_type")
            c["distress_signal"] = "code-enforcement"
            ce_hits += 1
        bl = (bl_apn.get(apn) if apn else None) or (bl_addr.get(na) if na else None)
        if bl:
            c["business_license_active"] = any(
                str(r.get("status") or "").lower() in ("active", "open", "1", "issued") for r in bl)
            c["business_activity"] = bl[0].get("activity") or bl[0].get("name")
            bl_hits += 1
    return {"code_enforcement_card_hits": ce_hits, "business_license_card_hits": bl_hits}


def harvest(cards):
    """Pull every configured free source, fold results in. Returns
    (events, new_card_seeds, report). Each source is isolated: a failure in one
    never aborts the harvest or the others."""
    report = {"enabled": getattr(config, "FREE_SOURCES_ENABLED", False), "sources": {}}
    events, seeds = [], []
    if not report["enabled"]:
        return events, seeds, report
    cap = getattr(config, "FREE_SOURCE_MAX", 4000)
    existing_apns = {_digits(c.get("parcel_apn")) for c in cards if c.get("parcel_apn")}
    items = getattr(config, "CLV_OPENDATA_ITEMS", {}) or {}
    ce_records = bl_records = []

    # Code Enforcement Violations -> distress signals + new leads
    try:
        url = resolve_layer(items.get("code_enforcement"))
        rows = _pull(url, max_records=cap) if url else []
        ce_records = code_enforcement_records(rows)
        events += to_events(ce_records, "VIOLATION", "clv_code_enforcement")
        seeds += seed_cards_from_violations(ce_records, existing_apns)
        report["sources"]["code_enforcement"] = {
            "status": "ok" if url else "unresolved", "layer": url,
            "records": len(ce_records), "new_leads": len(seeds)}
    except Exception as e:  # noqa: BLE001
        report["sources"]["code_enforcement"] = {"status": "error", "error": str(e)}

    # Business Licenses -> commercial / entity signals (CLV + Henderson)
    try:
        url = resolve_layer(items.get("business_licenses"))
        rows = _pull(url, max_records=cap) if url else []
        bl_records = business_license_records(rows)
        # Henderson business licenses (free ArcGIS Hub) -- 0.111
        hend_items = getattr(config, "HENDERSON_OPENDATA_ITEMS", {}) or {}
        h_url = resolve_layer(hend_items.get("business_licenses"))
        if h_url:
            bl_records = bl_records + business_license_records(_pull(h_url, max_records=cap))
        events += to_events(bl_records, "BUSINESS_LICENSE", "city_business_licenses")
        report["sources"]["business_licenses"] = {
            "status": "ok" if (url or h_url) else "unresolved",
            "records": len(bl_records), "clv_layer": url, "henderson_layer": h_url}
    except Exception as e:  # noqa: BLE001
        report["sources"]["business_licenses"] = {"status": "error", "error": str(e)}

    # LVMPD crime (optional, area-level) -> CRIME events only (no per-lead join)
    try:
        crime_item = getattr(config, "LVMPD_CRIME_ITEM", "")
        if crime_item:
            url = resolve_layer(crime_item)
            rows = _pull(url, max_records=cap) if url else []
            crime = code_enforcement_records(rows)  # reuse generic mapper
            events += to_events(crime, "CRIME", "lvmpd_crime")
            report["sources"]["crime"] = {"status": "ok" if url else "unresolved",
                                          "layer": url, "records": len(crime)}
        else:
            report["sources"]["crime"] = {"status": "not_configured",
                                          "note": "set LVMPD_CRIME_ITEM to wire (free, area signal)"}
    except Exception as e:  # noqa: BLE001
        report["sources"]["crime"] = {"status": "error", "error": str(e)}

    report["applied"] = apply_signals(cards, ce_records, bl_records)
    report["events_emitted"] = len(events)
    report["new_leads"] = len(seeds)
    return events, seeds, report
