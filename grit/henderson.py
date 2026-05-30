"""
City of Henderson permits (Alpha 0.110).

Henderson publishes its full Development Services Center permit feed as free open
data on a Socrata portal (opendata.cityofhenderson.com, dataset fpc9-568j). Unlike
the other SoNV jurisdictions (which sit behind Accela with no clean API), this is a
clean queryable feed that carries everything GRIT needs: permit type/status, apply
and issue dates, parcel number (APN), full property address, coordinates, owner +
mailing, valuation + square footage, AND the contractor's name *with their state
license number* -- richer contractor signal than the CLV feed.

This is the second live permit jurisdiction. Records are normalized into the same
permit shape the CLV connector emits, so they flow through the existing
permits_to_cards / merge / to_events / trade-tagging path unchanged.

Verified against live data (field names below are the dataset's real columns).
Fails safe: a network/portal error returns [] and a status, never a fabricated row.
"""
import json
import time
import urllib.parse
import urllib.request

from . import config
from .clv_permits import categorize_permit

SODA_HOST = "opendata.cityofhenderson.com"
PERMITS_DATASET = "fpc9-568j"          # Henderson DSC Permits
_UA = {"User-Agent": "GRIT/0.110 (+https://github.com/grit) henderson-permits"}


def _soda_get(dataset, params, host=SODA_HOST, timeout=45):
    url = f"https://{host}/resource/{dataset}.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _digits(v):
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _date(v):
    return str(v)[:10] if v else None


def _site_address(a):
    parts = [a.get("parceladdressnumber"), a.get("parceladdresspredirection"),
             a.get("parceladdressstreet"), a.get("parceladdressstreettype")]
    street = " ".join(str(p) for p in parts if p)
    return street or a.get("locationdescription") or None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _row_to_permit(a):
    lat = _num(a.get("gisy"))
    lng = _num(a.get("gisx"))
    ptype = a.get("permittype") or "permit"
    workclass = a.get("workclass") or ""
    return {
        "record": a.get("permitnumber"),
        "type": " ".join(x for x in [ptype, workclass] if x) or "permit",
        "status": a.get("permitstatus"),
        # issue date is the activity date; fall back to apply date
        "date": _date(a.get("issuedate") or a.get("applydate")),
        "valuation": a.get("valuationtotal") or a.get("totalconstructioncostprivate"),
        "site_address": _site_address(a),
        "city": a.get("parceladdresscity") or "Henderson",
        "apn": _digits(a.get("parcelnumber")) or None,
        "owner_name": a.get("ownername") or None,
        "owner_mailing": a.get("owneraddress") or None,
        "contractor": a.get("professionalname") or None,
        "license": (a.get("professionalstatelicnbr") or "").strip() or None,
        "contractor_phone": a.get("professionalphone") or None,
        "description": a.get("permitdescription") or None,
        "trades": categorize_permit(workclass, "", "", ptype),
        "sqft": a.get("permitsquarefootagetotal") or None,
        "lat": lat, "lng": lng,
    }


def fetch_henderson_permits(limit=None, max_rows=4000):
    """Pull recent Henderson permits (newest first) -> list of CLV-shaped permit
    dicts + a report. Bounded by max_rows. Fails safe."""
    limit = limit or getattr(config, "FREE_SOURCE_MAX", max_rows)
    report = {"source": "City of Henderson (Socrata DSC Permits)",
              "dataset": PERMITS_DATASET, "status": "ok", "ingested": 0,
              "newest": None, "error": None}
    if not getattr(config, "HENDERSON_PERMITS_ENABLED", True):
        report["status"] = "disabled"
        return [], report
    try:
        rows = _soda_get(PERMITS_DATASET,
                         {"$order": "applydate DESC", "$limit": str(min(limit, max_rows))})
    except Exception as e:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"{type(e).__name__}: {e}"
        return [], report
    permits = [_row_to_permit(a) for a in rows if a.get("permitnumber")]
    permits = [p for p in permits if p.get("apn") or p.get("site_address")]
    report["ingested"] = len(permits)
    dates = [p["date"] for p in permits if p.get("date")]
    report["newest"] = max(dates) if dates else None
    report["with_apn"] = sum(1 for p in permits if p.get("apn"))
    report["with_contractor"] = sum(1 for p in permits if p.get("contractor"))
    report["with_license"] = sum(1 for p in permits if p.get("license"))
    return permits, report
