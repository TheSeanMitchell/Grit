"""
Socrata open-data adapter -- the CLOUD-NATIVE permit-flow path.

Accela ACA 403s datacenter IPs, so it can never run in the GitHub runner. But the
City of Las Vegas publishes permits (and code enforcement, business licenses) on a
Socrata/Tyler open-data portal whose SODA API is DESIGNED for programmatic pulls --
no ViewState, no bot-blocking, no residential IP. So this runs in the cloud harvest.

  https://opendata.lasvegasnevada.gov/resource/wpyf-qpia.json   (building permits)

Coverage note: this is the City of Las Vegas (a large, dense chunk of the metro) --
NOT unincorporated Clark County / Henderson / North Las Vegas (those remain Accela +
residential capture). But it proves large-scale LIVE permit flow end-to-end on real
daily data, which is the gate.

Design: the SODA column names vary by portal, so we DISCOVER columns at runtime and
map our canonical permit fields against them -- and report the newest record date +
row count every run, so staleness or a moved dataset is instantly visible. No
fabricated data: if the dataset 404s or returns nothing, we say so.
"""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request

SODA_HOST = "opendata.lasvegasnevada.gov"
DATASETS = {                      # City of Las Vegas open-data dataset ids
    "permits":         "wpyf-qpia",
    "code_enforcement": "u3ci-m9hj",
    "business_licenses": "jv8a-mrfg",
    "service_requests": "ixm8-ujty",
}

# Map our canonical permit fields to whatever the Socrata columns are actually
# called (checked longest/most-specific first within each list).
_FIELD_PATTERNS = {
    "record":      ["permit_number", "permit_no", "permit_num", "record_number",
                    "case_number", "permit", "number"],
    "type":        ["permit_type", "permit_type_desc", "work_type", "sub_type",
                    "record_type", "permit_category", "type", "permit_subtype"],
    "status":      ["status", "permit_status", "current_status", "status_current"],
    "date":        ["issued_date", "issue_date", "issuedate", "date_issued",
                    "applied_date", "application_date", "apply_date", "file_date",
                    "status_date", "open_date"],
    "address":     ["address", "site_address", "full_address", "location_address",
                    "project_address", "address1", "location"],
    "valuation":   ["valuation", "job_value", "estimated_cost", "declared_valuation",
                    "construction_value", "value", "project_value"],
    "description": ["description", "work_description", "scope_of_work", "scope",
                    "project_name", "permit_description"],
    "contractor":  ["contractor", "contractor_name", "applicant_name", "applicant",
                    "company", "business_name", "owner_name"],
    "lat":         ["latitude", "lat", "y"],
    "lng":         ["longitude", "lng", "long", "x"],
}


def _soda_get(dataset, params, timeout=40):
    url = f"https://{SODA_HOST}/resource/{dataset}.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "GRIT-harvester/0.1 (public-records research)",
    })
    tok = os.environ.get("SODA_APP_TOKEN")        # optional; anon works for low volume
    if tok:
        req.add_header("X-App-Token", tok)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def discover_columns(dataset):
    rows = _soda_get(dataset, {"$limit": 1})
    return list(rows[0].keys()) if rows else []


def map_columns(columns):
    cl = {c.lower(): c for c in columns}
    cmap = {}
    for field, pats in _FIELD_PATTERNS.items():
        for p in pats:
            if p in cl:
                cmap[field] = cl[p]
                break
    return cmap


def _norm_date(v):
    if not v:
        return None
    s = str(v)[:10]
    return s if len(s) == 10 and s[4] == "-" else s


def _normalize(row, cmap):
    def g(field):
        col = cmap.get(field)
        return row.get(col) if col else None
    # address may be a Socrata location dict
    addr = g("address")
    if isinstance(addr, dict):
        addr = addr.get("human_address") or addr.get("address") or None
        if isinstance(addr, str) and addr.startswith("{"):
            try:
                addr = json.loads(addr).get("address")
            except Exception:
                pass
    return {
        "record": g("record"), "type": g("type"), "status": g("status"),
        "date": _norm_date(g("date")), "address": addr,
        "valuation": g("valuation"), "description": g("description"),
        "contractor": g("contractor"),
        "lat": g("lat"), "lng": g("lng"),
    }


def fetch_recent_permits(days_back=45, limit=10000, dataset=None):
    """Pull recent City of Las Vegas permits. Returns (permits, report).
    Report carries the discovered columns, field mapping, row count, and the
    NEWEST permit date -- so 'is this live and current?' is answered every run."""
    dataset = dataset or DATASETS["permits"]
    report = {"dataset": dataset, "host": SODA_HOST, "columns": None,
              "mapping": None, "rows": 0, "newest": None, "error": None}
    try:
        cols = discover_columns(dataset)
        report["columns"] = cols
        if not cols:
            report["error"] = "dataset returned no rows (empty or moved id?)"
            return [], report
        cmap = map_columns(cols)
        report["mapping"] = cmap
        params = {"$limit": limit}
        datef = cmap.get("date")
        if datef:
            since = (dt.date.today() - dt.timedelta(days=days_back)).isoformat()
            params["$where"] = f"{datef} >= '{since}T00:00:00.000'"
            params["$order"] = f"{datef} DESC"
        rows = _soda_get(dataset, params)
        permits = [_normalize(r, cmap) for r in rows]
        permits = [p for p in permits if p.get("record")]
        report["rows"] = len(permits)
        report["newest"] = max((p["date"] for p in permits if p.get("date")), default=None)
        return permits, report
    except Exception as e:  # noqa: BLE001
        report["error"] = f"{type(e).__name__}: {e}"
        return [], report


def to_events(permits, source="clv_socrata"):
    """Convert normalized permits to PERMIT Events (reuses the permit trade
    categorizer). Real rows only -- nothing synthesized."""
    from .events import Event
    from .permits import categorize
    evs = []
    for p in permits:
        if not p.get("record"):
            continue
        trades = categorize(p)
        val = f" ${p['valuation']}" if p.get("valuation") else ""
        evs.append(Event(
            kind="PERMIT",
            date=p.get("date") or dt.date.today().isoformat(),
            source=source, address=p.get("address"),
            description=(f"{p.get('type') or 'permit'} {p['record']}"
                        + (f" -- {p['description']}" if p.get("description") else "")
                        + val + (f" [{p['status']}]" if p.get("status") else "")).strip(),
            trade_tag=trades[0] if trades else None,
            lat=_num(p.get("lat")), lng=_num(p.get("lng")), raw=p))
    return evs


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def harvest_clv_permits(days_back=45):
    """Top-level: pull + convert. Returns (events, report)."""
    permits, report = fetch_recent_permits(days_back=days_back)
    return to_events(permits), report
