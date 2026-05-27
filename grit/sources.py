"""
Source registry + health probes.

Every resource the metro offers is registered here as a first-class Source.
Each Source knows:
  - what kind it is (clean API vs. browser-scrape vs. RSS)
  - whether the free GitHub runner can harvest it, or it needs a local/residential run
  - how to probe its health (is it live right now?)

The health probe is what powers the on-page Health Matrix. It NEVER fabricates
records; it reports reachability, latency, and (for the API source) real record
counts and the actual field names discovered.
"""
import time
import urllib.error
import urllib.request

from . import config, arcgis

# kind values: "arcgis_rest" (clean API, runs free) | "accela" | "aspx" | "rss"
# tier values: "live" (harvested now) | "reachable" (probed, harvest is next wave)
#              | "manual" (needs local/residential IP run)


class Source:
    def __init__(self, key, name, kind, url, tier, note=""):
        self.key = key
        self.name = name
        self.kind = kind
        self.url = url
        self.tier = tier
        self.note = note

    def probe(self):
        """Return a health record. Real checks only."""
        rec = {
            "key": self.key, "name": self.name, "kind": self.kind,
            "tier": self.tier, "url": self.url, "note": self.note,
            "status": "unknown", "latency_ms": None, "records": None,
            "fields": None, "error": None, "checked_at": _now(),
        }
        try:
            if self.kind == "arcgis_rest":
                self._probe_arcgis(rec)
            else:
                self._probe_http(rec)
        except Exception as e:  # noqa: BLE001 - health must never crash the run
            rec["status"] = "down"
            rec["error"] = f"{type(e).__name__}: {e}"
        return rec

    def _probe_arcgis(self, rec):
        if config.CLARK_PARCEL_LAYER:
            fields, info = arcgis.layer_meta(config.CLARK_PARCEL_LAYER)
            rec["fields"] = fields
            rec["status"] = "live"
            rec["note"] = f"layer ready: {info.get('name')} ({len(fields)} fields)"
        else:
            cat = arcgis.catalog(self.url)
            rec["status"] = "reachable"
            rec["records"] = len(cat["folders"]) + len(cat["services"])
            rec["note"] = ("server live; parcel layer not yet pinned -- "
                           "run `python -m grit discover` then set CLARK_PARCEL_LAYER")

    def _probe_http(self, rec):
        req = urllib.request.Request(self.url, headers={"User-Agent": config.USER_AGENT})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as resp:
                code = resp.getcode()
            rec["latency_ms"] = int((time.time() - t0) * 1000)
            rec["status"] = "reachable" if code == 200 else f"http {code}"
        except urllib.error.HTTPError as e:
            rec["latency_ms"] = int((time.time() - t0) * 1000)
            # Server is alive but refused the bot -- expected for manual-tier
            # portals; the real harvest uses a browser / residential IP.
            if e.code in (401, 403, 429):
                rec["status"] = "reachable"
                rec["note"] = (self.note + f" [server up; bot-blocked HTTP {e.code} "
                               "-- harvest needs browser/residential IP]").strip()
            else:
                rec["status"] = "down"
                rec["error"] = f"HTTPError: HTTP {e.code}"


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- The registry. Every URL here is a real, confirmed public endpoint. -----
REGISTRY = [
    Source("clark_gis", "Clark County GIS (parcels / owner / address)",
           "arcgis_rest", config.CLARK_ARCGIS_ROOT, "live",
           "Clean ArcGIS REST API. Harvests free from the GitHub runner."),

    Source("clark_accela", "Clark County permits (Accela Citizen Access)",
           "accela", "https://aca-prod.accela.com/clarkco/Default.aspx", "manual",
           "Permit events: who pulled what, where, value. ViewState portal -- "
           "headless browser; may need a residential IP."),

    Source("nscb", "Nevada State Contractors Board (license search)",
           "aspx", "https://app.nvcontractorsboard.com/Clients/NVSCB/Public/"
           "ContractorLicenseSearch/ContractorLicenseSearch.aspx", "manual",
           "Every licensed contractor by trade = your buyer list + verification."),

    Source("clark_assessor", "Clark County Assessor (parcel / owner / sales)",
           "aspx", "https://www.clarkcountynv.gov/government/assessor/", "manual",
           "Authoritative current owner + sale detail; complements the GIS layer."),

    Source("clark_recorder", "Clark County Recorder (deeds / NOD / liens)",
           "aspx", "https://www.clarkcountynv.gov/government/elected_officials/"
           "county_recorder/", "manual",
           "Leading indicators: sales (new owners), defaults, mechanics liens."),

    Source("lv_permits", "City of Las Vegas permits",
           "accela", "https://www.lasvegasnevada.gov/", "manual",
           "Incorporated-city permits (separate from county)."),

    Source("henderson_permits", "City of Henderson permits",
           "accela", "https://www.cityofhenderson.com/", "manual",
           "Incorporated-city permits (separate from county)."),

    Source("nlv_permits", "City of North Las Vegas permits",
           "accela", "https://www.cityofnorthlasvegas.com/", "manual",
           "Incorporated-city permits (separate from county)."),
]


def by_key(key):
    for s in REGISTRY:
        if s.key == key:
            return s
    return None
