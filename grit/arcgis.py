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
import time
import urllib.parse
import urllib.request

from . import config


def _get(url, params=None):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as resp:
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


def layer_meta(layer_url):
    """Return (fields, info) for a FeatureServer/MapServer layer."""
    data, _ = _get(layer_url, {"f": "json"})
    fields = [f["name"] for f in data.get("fields", [])]
    info = {
        "name": data.get("name"),
        "type": data.get("type"),
        "geometryType": data.get("geometryType"),
        "maxRecordCount": data.get("maxRecordCount"),
        "fields": fields,
    }
    return fields, info


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
