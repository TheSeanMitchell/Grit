"""
City of Las Vegas permits -- ArcGIS Feature Service (VERIFIED real endpoint + schema).

The CLV open-data portal moved off Socrata to ArcGIS Hub. Permits live at a hosted
ArcGIS Feature Service, queried over ArcGIS REST -- the same transport GRIT already
uses for parcels, so it runs in the GitHub runner (no residential IP, no ViewState).

Endpoint + schema are verified against the live service (config.CLV_PERMITS_FEATURESERVER).
Each permit is an EVENT -> ENTITY -> MONEY lead: a property with active work, a known
owner, a known contractor, a valuation, and a date.

Schema notes that matter (these are easy to get wrong):
  * The PROPERTY address is built from STNO + PREDIR + STNAME + SUFFIX + POSTDIR
    (e.g. "289 JACKALBERRY ST"). APL_ADDRESS is the APPLICANT/CONTRACTOR office --
    NOT the property -- and is deliberately ignored.
  * PRCLID is the parcel APN (digits, no dashes) -> used to join permits to parcels.
  * NAME / LEGALOWNER = owner; ADDR1/CITY/STATE/ZIP = owner mailing (absentee if != site).
  * APPLICANT = contractor; NSCB = contractor license # + class.
  * The real trade lives in WORKTYPE (Sign/Patio/Plumbing/Electrical/TI) and in
    MISC_FEES text (PHOTOVOLTAIC / HVAC / WATER HEATER / ...).
  * ISSDTTM = issue date (epoch ms). DECLVLTN = declared job valuation.
"""
import datetime as dt
import json
import ssl
import urllib.parse
import urllib.request

from . import config


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _get(url, params, timeout=45):
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={
        "Accept": "application/json",
        "User-Agent": "GRIT-harvester/0.1 (public-records research)"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ---- field extraction (exact, verified schema) -----------------------------
# These are City of Las Vegas building permits, so every record's issuing
# jurisdiction is Las Vegas. The feed's CITY column is the owner's mailing
# city (kept for owner_mailing only), NOT the property's city.
CLV_JURISDICTION = "LAS VEGAS"


def _build_site_address(a):
    out = []
    stno = a.get("STNO")
    try:
        if stno not in (None, "", 0) and float(stno) != 0:
            out.append(str(int(float(stno))))
    except (TypeError, ValueError):
        pass
    for k in ("PREDIR", "STNAME", "SUFFIX", "POSTDIR"):
        v = a.get(k)
        if v and str(v).strip():
            out.append(str(v).strip())
    return " ".join(out).strip()


def _apn_from_prclid(p):
    if p in (None, ""):
        return None
    s = "".join(ch for ch in str(p) if ch.isdigit())
    return s or None


def _join_mailing(addr1, city, state, zc):
    if not addr1:
        return None
    tail = " ".join(x for x in [city, state, zc] if x)
    return (f"{addr1}, {tail}".strip().rstrip(",")) if tail else str(addr1)


def _norm_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) and v > 1e10:          # ArcGIS epoch ms
        try:
            return dt.datetime.utcfromtimestamp(v / 1000).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(v)[:10]


def _desc(misc, code):
    bits = []
    if misc:
        # MISC_FEES = "BLDGANALYSIS | DESCRIPTION 3D_082 | PHOTOVOLTAIC SYSTEM PER KW..."
        tail = str(misc).split("|")[-1].strip()
        if tail and not tail.upper().startswith("DESCRIPTION"):
            bits.append(tail)
    if code:
        bits.append(str(code).replace("OCCDESC", "").strip())
    return " -- ".join(b for b in bits if b) or None


def _clean_license(nscb):
    if not nscb:
        return None
    # "LICENSE # | TYPE 0083098 | C-2" -> "0083098 | C-2"
    s = str(nscb).split("TYPE", 1)
    return s[1].strip(" |") if len(s) > 1 else str(nscb).strip()


# WORKTYPE-authoritative buckets, then MISC/CODE text rules (verified on real data).
_WT_DIRECT = {"sign": "sign", "patio": "patio", "plumbing": "plumbing",
              "electrical": "electrical", "ti": "remodeling"}
_TEXT_RULES = [
    ("solar",      ["photovoltaic", "solar"]),
    ("hvac",       ["heating ventilation", "air conditioning", "hvac", "furnace", "heat pump"]),
    ("plumbing",   ["water heater", "water softener", "plumbing fixtures",
                    "water and sewer", "sewer", "repipe"]),
    ("roofing",    ["reroof", "re-roof", "shingle", "roof recover", "roofing"]),
    ("remodeling", ["remodel", "addition", "renovat", "kitchen", "bath"]),
    ("pools",      ["pool", "spa"]),
    ("concrete",   ["driveway", "flatwork", "slab"]),
    ("fencing",    ["block wall", "fence"]),
]


def categorize_permit(worktype, misc, code, aptype):
    tags = []
    wt = (worktype or "").strip().lower()
    if wt in _WT_DIRECT:
        tags.append(_WT_DIRECT[wt])
    blob = " ".join([misc or "", code or ""]).lower()
    for trade, subs in _TEXT_RULES:
        if trade not in tags and any(s in blob for s in subs):
            tags.append(trade)
    return tags


def _normalize(feature):
    a = feature.get("properties") or feature.get("attributes") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") if isinstance(geom, dict) else None
    lng = coords[0] if isinstance(coords, list) and len(coords) >= 2 else None
    lat = coords[1] if isinstance(coords, list) and len(coords) >= 2 else None
    # esri-json fallback: some hosted layers return {x,y} instead of GeoJSON
    # coordinates even when f=geojson is requested. Read it so a permit that
    # DOES carry a point isn't dropped (APN geocoding covers the rest).
    if lat is None and isinstance(geom, dict) and geom.get("x") not in (None, "") \
            and geom.get("y") not in (None, ""):
        try:
            lng, lat = float(geom["x"]), float(geom["y"])
        except (TypeError, ValueError):
            lng = lat = None
    worktype, aptype = a.get("WORKTYPE"), a.get("APTYPE")
    misc, code = a.get("MISC_FEES"), a.get("CODE_ANALYSIS")
    return {
        "record": a.get("APNO"),
        "type": " ".join(x for x in [aptype, worktype] if x) or "permit",
        "status": a.get("BLDGAPPLSTATUS"),
        "date": _norm_date(a.get("ISSDTTM")),
        "valuation": a.get("DECLVLTN"),
        "site_address": _build_site_address(a) or None,
        # NOTE: the CLV feed's CITY field is the OWNER's mailing city, not the
        # property's city. These are City of Las Vegas permits, so the SITE
        # jurisdiction is Las Vegas by definition (the issuing authority). We
        # set the site city accordingly and keep CITY only for owner_mailing,
        # so an owner mailing from Chicago no longer mislabels a LV property.
        "city": CLV_JURISDICTION,
        "apn": _apn_from_prclid(a.get("PRCLID")),
        "owner_name": (a.get("NAME") or None),
        "owner_mailing": _join_mailing(a.get("ADDR1"), a.get("CITY"),
                                       a.get("STATE"), a.get("ZIP")),
        "contractor": (a.get("APPLICANT") or None),
        "license": _clean_license(a.get("NSCB")),
        # contractor office address (APL_*) -- a real contact channel for the
        # contractor; CLV exposes no contractor phone, so this + license is what
        # we get here (Henderson supplies the phone).
        "contractor_address": _join_mailing(a.get("APL_ADDRESS"), a.get("APL_CITY"),
                                            a.get("APL_STATE"), a.get("APL_ZIP")) or None,
        "contractor_phone": (a.get("APL_PHONE") or a.get("PHONE") or None),
        "description": _desc(misc, code),
        "trades": categorize_permit(worktype, misc, code, aptype),
        "comm": a.get("COMM"), "res": a.get("RES"),
        "lat": lat, "lng": lng,
    }


# ---- fetch (paged, recent-first) -------------------------------------------
def fetch_clv_permits(days_back=90, page_size=2000, max_pages=4):
    """Pull recent CLV permits (ordered newest-first, filtered to days_back).
    Returns (permits, report). Report carries row count + newest date + any
    error -- so the harvest log shows immediately whether the feed is live."""
    url = (config.CLV_PERMITS_FEATURESERVER or "").strip().rstrip("/")
    report = {"layer": url, "rows": 0, "newest": None, "pages": 0,
              "status": "ok", "error": None}
    if not url:
        report["status"] = "needs_config"
        return [], report
    cutoff = (dt.date.today() - dt.timedelta(days=days_back)).isoformat() if days_back else None
    permits, offset = [], 0
    try:
        for _ in range(max_pages):
            params = {"where": "1=1", "outFields": "*", "f": "geojson",
                      "returnGeometry": "true", "outSR": "4326",
                      "orderByFields": "ISSDTTM DESC",
                      "resultRecordCount": str(page_size), "resultOffset": str(offset)}
            data = _get(f"{url}/query", params)
            feats = data.get("features", [])
            if not feats:
                break
            batch = [p for p in (_normalize(f) for f in feats) if p.get("record")]
            permits.extend(batch)
            report["pages"] += 1
            oldest = min((p["date"] for p in batch if p.get("date")), default=None)
            if cutoff and oldest and oldest < cutoff:
                break
            if len(feats) < page_size:
                break
            offset += page_size
        if cutoff:
            permits = [p for p in permits if not p.get("date") or p["date"] >= cutoff]
        report["rows"] = len(permits)
        report["newest"] = max((p["date"] for p in permits if p.get("date")), default=None)
        return permits, report
    except Exception as e:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"{type(e).__name__}: {e}"
        return permits, report


def to_events(permits, source="clv_permit"):
    """Permits -> PERMIT Events (carry APN so they join to parcels by APN)."""
    from .events import Event
    today = dt.date.today().isoformat()
    evs = []
    for p in permits:
        if not p.get("record"):
            continue
        val = ""
        try:
            if p.get("valuation"):
                val = f" ${int(float(p['valuation'])):,}"
        except (TypeError, ValueError):
            pass
        desc = (f"{p.get('type') or 'permit'} {p['record']}"
                + (f" -- {p['description']}" if p.get("description") else "")
                + val
                + (f" by {p['contractor']}" if p.get("contractor") else "")
                + (f" [{p['status']}]" if p.get("status") else "")).strip()
        evs.append(Event(
            kind="PERMIT", date=p.get("date") or today, source=source,
            parcel_apn=p.get("apn"), address=p.get("site_address"),
            description=desc, trade_tag=p["trades"][0] if p.get("trades") else None,
            lat=p.get("lat"), lng=p.get("lng"), raw=p))
    return evs


def harvest_clv_permits(days_back=90):
    permits, report = fetch_clv_permits(days_back=days_back)
    return to_events(permits), report
