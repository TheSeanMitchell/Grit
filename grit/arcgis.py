"""
Minimal, dependency-free ArcGIS REST client (urllib only).

Runs anywhere Python runs, including a free GitHub Actions runner. No paid SDK,
no API key. Talks to standard ArcGIS REST endpoints:

  metadata : {layer}?f=json
  query    : {layer}/query?where=...&outFields=*&f=geojson&...

It self-discovers: given a server root it walks folders -> services -> layers,
and reports the REAL field names each layer exposes so we never guess a schema.
"""
import json
import ssl
import time
import urllib.parse
import urllib.request

from . import config


def _ssl_ctx():
    """Unverified context for the cert-broken gov GIS endpoint (see config)."""
    if getattr(config, "ARCGIS_INSECURE_SSL", False):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _get(url, params=None, timeout=None):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT,
                                context=_ssl_ctx()) as resp:
        body = resp.read().decode("utf-8", "replace")
    latency_ms = int((time.time() - t0) * 1000)
    return json.loads(body), latency_ms


def catalog(root):
    """List folders and services at an ArcGIS REST server root."""
    data, _ = _get(root, {"f": "json"})
    return {
        "folders": data.get("folders", []),
        "services": [s for s in data.get("services", [])],
    }


def folder(root, name):
    data, _ = _get(f"{root}/{name}", {"f": "json"})
    return data.get("services", [])


def layer_meta(layer_url, timeout=None):
    """Return (fields, info) for a FeatureServer/MapServer layer."""
    data, _ = _get(layer_url, {"f": "json"}, timeout=timeout)
    fields = [f["name"] for f in data.get("fields", [])]
    info = {
        "name": data.get("name"),
        "type": data.get("type"),
        "geometryType": data.get("geometryType"),
        "maxRecordCount": data.get("maxRecordCount"),
        "fields": fields,
    }
    return fields, info


# --- auto-discovery: find the best parcel/owner/address layer, bounded -------
DISCOVERY_TIMEOUT = 10
DISCOVERY_BUDGET = 120      # max layer probes per harvest
STRONG_SCORE = 8            # good enough -> stop early


def _score_layer(fields, info):
    low = [f.lower() for f in fields]
    def has(hints):
        return any(any(h in f for f in low) for h in hints)
    s = 0
    if has(config.FIELD_HINTS["owner_name"]):    s += 3
    if has(config.FIELD_HINTS["parcel_apn"]):    s += 2
    if has(config.FIELD_HINTS["situs_address"]): s += 2
    if has(config.FIELD_HINTS["last_sale_date"]):s += 1
    name = (info.get("name") or "").lower()
    if any(k in name for k in ("parcel", "assessor", "ownership", "property")):
        s += 3
    if info.get("geometryType") in ("esriGeometryPolygon", "esriGeometryPoint"):
        s += 1
    return s


def find_parcel_layer(roots=None):
    """
    Crawl the configured ArcGIS servers (bounded) and return the best candidate:
    {"url","name","score","fields"} or None. Prioritizes Assessor/Address/parcel
    folders and services so the right layer is found in the first few probes.
    """
    roots = roots or getattr(config, "DISCOVERY_ROOTS", [config.CLARK_ARCGIS_ROOT])
    probes, best = 0, None

    for root in roots:
        try:
            cat = catalog(root)
        except Exception:
            continue
        services = list(cat.get("services", []))
        # prioritize promising folders
        folders = sorted(cat.get("folders", []),
                         key=lambda f: 0 if any(k in f.lower() for k in
                         ("assessor", "address", "parcel", "adminserv")) else 1)
        for fld in folders:
            try:
                services += folder(root, fld)
            except Exception:
                continue
        services = [s for s in services if s.get("type") in ("FeatureServer", "MapServer")]
        services.sort(key=lambda s: 0 if any(k in (s.get("name") or "").lower() for k in
                      ("parcel", "assessor", "ownership", "property", "cadastr")) else 1)

        for svc in services:
            if probes >= DISCOVERY_BUDGET:
                break
            base = f"{root}/{svc['name']}/{svc['type']}"
            for lid in range(0, 20):
                if probes >= DISCOVERY_BUDGET:
                    break
                try:
                    fields, info = layer_meta(f"{base}/{lid}", timeout=DISCOVERY_TIMEOUT)
                except Exception:
                    break
                probes += 1
                score = _score_layer(fields, info)
                if score > 0 and (best is None or score > best["score"]):
                    best = {"url": f"{base}/{lid}", "name": info.get("name"),
                            "score": score, "fields": fields}
                if best and best["score"] >= STRONG_SCORE:
                    return best
    return best


def _envelope_param():
    b = config.METRO_BBOX
    return {
        "geometry": json.dumps({
            "xmin": b["xmin"], "ymin": b["ymin"],
            "xmax": b["xmax"], "ymax": b["ymax"],
            "spatialReference": {"wkid": 4326},
        }),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


def query_layer(layer_url, where="1=1", page_size=None, max_pages=None,
                use_bbox=True, out_sr=4326):
    """
    Page through a layer and yield GeoJSON features (real records only).
    Returns (features, meta) where meta carries counts + latency for health.
    """
    page_size = page_size or config.PAGE_SIZE
    max_pages = max_pages or config.MAX_PAGES
    features, offset, pages, total_latency = [], 0, 0, 0

    base = {
        "where": where,
        "outFields": "*",
        "f": "geojson",
        "returnGeometry": "true",
        "outSR": str(out_sr),
        "resultRecordCount": str(page_size),
    }
    if use_bbox:
        base.update(_envelope_param())

    while pages < max_pages:
        params = dict(base, resultOffset=str(offset))
        data, latency = _get(f"{layer_url}/query", params)
        total_latency += latency
        page = data.get("features", [])
        features.extend(page)
        pages += 1
        if len(page) < page_size:
            break
        offset += page_size

    return features, {"records": len(features), "pages": pages,
                      "latency_ms": total_latency}


def sample_layer(layer_url, where="1=1", n=40, timeout=None):
    """Pull a small sample (schema + a few records) to evaluate a candidate."""
    fields, info = layer_meta(layer_url, timeout=timeout or DISCOVERY_TIMEOUT)
    params = {
        "where": where, "outFields": "*", "f": "geojson",
        "returnGeometry": "false", "resultRecordCount": str(n),
    }
    b = config.METRO_BBOX
    params.update({
        "geometry": json.dumps({"xmin": b["xmin"], "ymin": b["ymin"],
                                "xmax": b["xmax"], "ymax": b["ymax"],
                                "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryEnvelope", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    })
    data, _ = _get(f"{layer_url}/query", params, timeout=timeout or DISCOVERY_TIMEOUT)
    return data.get("features", []), fields, info
