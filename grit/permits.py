"""
Permits event source (Accela Citizen Access).

The Accela ACA portal (citizenaccess.clarkcountynv.gov / aca-prod.accela.com)
is the freshest free source of "current project" signal: who pulled a building,
roofing, HVAC, solar, electrical, or plumbing permit, where, when, by whom.

Reality: ACA is a ViewState .aspx portal that blocks datacenter IPs (the free
GitHub runner gets 403s from these). So this module is built to RUN LOCALLY
from a residential IP -- e.g. your own machine in Las Vegas -- not the cloud.

This file is a CAPTURE scaffold, by design. It fetches real ACA responses and
saves them raw for parser calibration. It does NOT publish parsed events until
a verified extractor exists, because publishing mis-parsed events would
fabricate activity and break the no-synthetic-data rule.
"""
import os
import time
import urllib.parse
import urllib.request

from . import config

ACA_BUILDING = ("https://citizenaccess.clarkcountynv.gov/CitizenAccess/Cap/"
                "CapHome.aspx?module=Building&TabName=Building")
ACA_HOME = "https://aca-prod.accela.com/clarkco/Default.aspx"


def fetch_raw(url, timeout=25):
    """Fetch a raw ACA page (HTML). Returns (status, text). For residential IPs."""
    req = urllib.request.Request(url, headers={
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read().decode("utf-8", "replace")


def capture_search_form(out_dir="docs/data/permit_samples"):
    """Capture the ACA Building search form + landing page. The HTML carries the
    ViewState and the field names a real submission needs -- this is what calibrates
    the search step before any parsing of results is trusted."""
    os.makedirs(out_dir, exist_ok=True)
    report = []
    for label, url in (("aca_home", ACA_HOME), ("aca_building_search", ACA_BUILDING)):
        try:
            code, text = fetch_raw(url)
            path = os.path.join(out_dir, f"{label}.html")
            with open(path, "w") as f:
                f.write(text)
            report.append({"label": label, "status": code, "bytes": len(text),
                           "saved": path})
        except Exception as e:  # noqa: BLE001
            report.append({"label": label, "error": f"{type(e).__name__}: {e}"})
        time.sleep(1.5)  # polite
    return report
