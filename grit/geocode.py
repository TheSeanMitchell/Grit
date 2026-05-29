"""
Geocoding spine (Alpha 0.105) -- put EVERY signal on the map.

The problem this solves: the City of Las Vegas permit feed is the freshest, most
valuable signal GRIT has, but the hosted permit layer ships rows with no usable
point geometry. So ~900 active-work leads were invisible on the map -- the
console only ever plotted the parcel base layer, which clusters in a few
new-construction subdivisions. The map looked tiny; the city's real activity was
hidden.

The fix is authoritative, not approximate: a permit already carries a parcel APN
(PRCLID). The county parcel layer has a real centroid for every APN. So we build
an APN -> (lat, lng) lookup from the parcel layer and stamp it onto every permit
(and any other coordless card). No address-string geocoding, no guessed points,
no fabricated locations -- a permit only gets a coordinate if its parcel's real
centroid is found. APNs that can't be resolved stay coordless and are counted in
the coverage report (honest empty state, never a fake pin).

Cloud-safe: same ArcGIS REST transport as the parcel harvest, so it runs in the
free GitHub Action -- no residential IP, no ViewState.
"""
import json
import ssl
import time
import urllib.parse
import urllib.request

from . import config


def _ctx():
    if getattr(config, "ARCGIS_INSECURE_SSL", False):
        c = ssl.create_default_context()
        c.check_hostname = False
        c.verify_mode = ssl.CERT_NONE
        return c
    return None


def _get(url, params, timeout=45):
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={"User-Agent": config.USER_AGENT,
                                                "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def norm_apn(apn):
    """Digits-only APN -- the format-agnostic join key (parcel layers use dashes,
    permit PRCLIDs don't)."""
    return "".join(ch for ch in str(apn or "") if ch.isdigit())


def dash_apn(digits):
    """Reconstruct Clark County's BBB-BB-BBB-BBB dashed APN from 11 digits.
    Returns None if the input isn't an 11-digit APN (so we don't query garbage)."""
    d = norm_apn(digits)
    if len(d) != 11:
        return None
    return f"{d[0:3]}-{d[3:5]}-{d[5:8]}-{d[8:11]}"


def _centroid(geom):
    """Centroid of a GeoJSON geometry (Point passes through; polygons averaged)."""
    if not geom:
        return None
    t, c = geom.get("type"), geom.get("coordinates")
    try:
        if t == "Point":
            return (c[1], c[0])
        if t in ("Polygon", "MultiPolygon"):
            ring = c[0][0] if t == "MultiPolygon" else c[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            return (sum(ys) / len(ys), sum(xs) / len(xs))
    except Exception:  # noqa: BLE001 - never let one bad geometry break the run
        return None
    return None


def _resolve_apn_field(layer_url):
    """Find the APN field name on the geocode layer from its REAL field list,
    using config.FIELD_HINTS['parcel_apn']. Never guesses a schema."""
    from . import arcgis
    try:
        fields, _ = arcgis.layer_meta(layer_url, timeout=20)
    except Exception:  # noqa: BLE001
        return None
    low = {f.lower(): f for f in fields}
    for hint in config.FIELD_HINTS["parcel_apn"]:
        for lf, orig in low.items():
            if hint in lf:
                return orig
    return None


def _query_batch(layer_url, apn_field, apns_dashed, apns_digit, timeout=45):
    """Query one batch of APNs and return {digits: (lat,lng)}. Tries the dashed
    form first (typical for county parcel layers); if a batch comes back empty,
    retries with the raw-digit form (some layers store APN without dashes).
    Results are indexed by digits-only, so the query format never matters."""
    out = {}
    for values in (apns_dashed, apns_digit):
        values = [v for v in values if v]
        if not values:
            continue
        in_list = ",".join("'" + v.replace("'", "''") + "'" for v in values)
        params = {
            "where": f"{apn_field} IN ({in_list})",
            "outFields": apn_field,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": str(len(values) + 10),
        }
        try:
            data = _get(f"{layer_url}/query", params, timeout=timeout)
        except Exception:  # noqa: BLE001
            continue
        feats = data.get("features", []) or []
        for f in feats:
            props = f.get("properties") or f.get("attributes") or {}
            apn = props.get(apn_field)
            ll = _centroid(f.get("geometry"))
            k = norm_apn(apn)
            if k and ll and k not in out:
                out[k] = ll
        if out:                 # dashed form worked -> don't double-query
            break
    return out


def centroids_for_apns(apns, layer_url=None, batch=80, max_batches=60):
    """Build {digits_apn: (lat,lng)} for the given APNs from the parcel layer.

    Returns (lookup, report). Bounded by max_batches so a huge APN set can't run
    the Action forever; report.resolved/requested makes the geocode yield visible
    every harvest (a low yield means the layer or APN format moved -- not a fake
    coordinate). Real centroids only.
    """
    layer_url = (layer_url or getattr(config, "PARCEL_GEOCODE_LAYER", "")
                 or "").strip().rstrip("/")
    want = sorted({norm_apn(a) for a in apns if norm_apn(a)})
    report = {"layer": layer_url, "requested": len(want), "resolved": 0,
              "batches": 0, "apn_field": None, "status": "ok", "error": None}
    if not layer_url or not want:
        report["status"] = "needs_config" if not layer_url else "no_apns"
        return {}, report

    apn_field = _resolve_apn_field(layer_url)
    report["apn_field"] = apn_field
    if not apn_field:
        report["status"] = "no_apn_field"
        report["error"] = "could not resolve an APN field on the geocode layer"
        return {}, report

    lookup = {}
    try:
        for i in range(0, len(want), batch):
            if report["batches"] >= max_batches:
                report["status"] = "truncated"
                break
            chunk = want[i:i + batch]
            dashed = [dash_apn(d) for d in chunk]
            got = _query_batch(layer_url, apn_field, dashed, chunk)
            lookup.update(got)
            report["batches"] += 1
            time.sleep(getattr(config, "GEOCODE_DELAY", 0.15))
    except Exception as e:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"{type(e).__name__}: {e}"
    report["resolved"] = len(lookup)
    report["yield_pct"] = round(100 * len(lookup) / len(want), 1) if want else 0.0
    return lookup, report


def stamp_cards(cards, lookup):
    """Fill lat/lng on any coordless card whose APN is in the lookup. Mutates in
    place; returns the number of cards newly placed on the map."""
    placed = 0
    for c in cards:
        if c.get("lat") not in (None, "") and c.get("lng") not in (None, ""):
            continue
        ll = lookup.get(norm_apn(c.get("parcel_apn")))
        if ll:
            c["lat"], c["lng"] = ll[0], ll[1]
            c["geocoded"] = "parcel_centroid"
            placed += 1
    return placed


def stamp_events(events, lookup):
    """Fill lat/lng on coordless Event objects by APN (so playback can animate
    them). Mutates in place; returns the count newly placed."""
    placed = 0
    for e in events:
        if getattr(e, "lat", None) not in (None, "") and getattr(e, "lng", None) not in (None, ""):
            continue
        ll = lookup.get(norm_apn(getattr(e, "parcel_apn", None)))
        if ll:
            e.lat, e.lng = ll[0], ll[1]
            placed += 1
    return placed
