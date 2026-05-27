"""
Assessor enrichment (experimental / fragile tier).

The freshest Clark County owner + value + sale data lives in the Assessor's
per-parcel system (secured roll current as of late 2025), NOT in any clean public
feed. Getting current data therefore means querying the Assessor by APN.

This module does that ONE honest step at a time:

  1. fetch_raw(apn)      -> pull the live parcel-detail page for one APN
  2. capture_samples()   -> save a few raw responses to disk for CALIBRATION

We deliberately do NOT ship a blind HTML parser. Parsing only gets turned on
after we've seen real captured output and written an exact extractor -- otherwise
we'd risk publishing mis-parsed owner data, which violates the no-fake-data rule.

Caveats: per-APN = slow at volume; the Assessor may rate-limit or block the
free runner's datacenter IP (a residential IP may be required). Health is
reported honestly either way.
"""
import os
import time
import urllib.parse
import urllib.request

from . import config

PARCEL_DETAIL = "https://maps.clarkcountynv.gov/assessor/AssessorParcelDetail/pcl.aspx"
SECURED_ROLL = "https://maps.clarkcountynv.gov/secroll/secroll.asp"


def fetch_raw(apn, timeout=20):
    """Best-effort fetch of the live parcel-detail page for one APN.
    Returns (http_status, text). Raises on connection failure."""
    url = PARCEL_DETAIL + "?hdnParcel=" + urllib.parse.quote(str(apn))
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read().decode("utf-8", "replace")


def capture_samples(apns, out_dir="docs/data/assessor_samples"):
    """Fetch a handful of APNs and save raw responses for calibration."""
    os.makedirs(out_dir, exist_ok=True)
    report = []
    for apn in apns:
        rec = {"apn": apn}
        try:
            code, text = fetch_raw(apn)
            path = os.path.join(out_dir, f"{str(apn).replace('/', '_')}.html")
            with open(path, "w") as f:
                f.write(text)
            rec.update(status=code, bytes=len(text), saved=path)
        except Exception as e:  # noqa: BLE001
            rec.update(error=f"{type(e).__name__}: {e}")
        report.append(rec)
        time.sleep(1.2)  # be polite to the county server
    return report
