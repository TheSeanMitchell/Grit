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
            # Manual-tier ViewState portals are EXPECTED to refuse/stall bots
            # (that's why they're manual). A timeout/connection error there is
            # the expected state, not an outage -- don't flag it red.
            if self.tier == "manual":
                rec["status"] = "manual"
                rec["note"] = (self.note + " [no bot access from here -- "
                               "residential capture]").strip()
            else:
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


# --- The registry. Every URL here is a real, confirmed public endpoint. ------
# Tiers (see EVENT_MATRIX.md):
#   "live"      harvested now, cloud-safe
#   "reachable" sanctioned channel verified; ingestion is the next build wave
#   "manual"    ViewState/session portal -> residential IP, low-volume capture
REGISTRY = [
    # ── TIER A: clean / sanctioned, cloud-safe ──────────────────────────────
    Source("clark_gis", "Clark County GIS (parcels / owner / address)",
           "arcgis_rest", config.CLARK_ARCGIS_ROOT, "live",
           "Clean ArcGIS REST API + Hub open data (ccgismo). Spatial spine; "
           "harvests free from the GitHub runner. Do NOT redistribute raw GIS (NRS 250)."),

    Source("clark_assessor", "Clark County Assessor (parcel / owner / sales)",
           "aspx", "https://maps.clarkcountynv.gov/assessor/AssessorParcelDetail/"
           "parceldetail.aspx", "live",
           "LIVE per-APN enrichment (0.102): current owner, address, value, last "
           "sale, characteristics via parceldetail.aspx GET. Deterministic parser."),

    Source("clv_permits_arcgis", "City of Las Vegas permits (ArcGIS Hub — LIVE permit flow)",
           "soda", "https://opendataportal-lasvegas.opendata.arcgis.com/", "live",
           "★ LIVE PERMIT FLOW. CLV building permits via ArcGIS Hub Feature Service "
           "(portal moved off Socrata). Cloud-native ArcGIS REST -- same transport as "
           "parcels, no residential IP. Set CLV_PERMITS_FEATURESERVER, then pulled every "
           "harvest -> PERMIT events -> IMMEDIATE scoring."),

    Source("nv_sos", "Nevada SOS business entities (SilverFlume / ORION)",
           "api", "https://esos.nv.gov/EntitySearch/OnlineEntitySearch", "reachable",
           "LLC_REGISTRATION + officer/registered-agent graph. Official BULK "
           "DOWNLOAD + API exist (sanctioned -- no scraping). Powers entity graph."),

    Source("nscb", "Nevada State Contractors Board (license search)",
           "aspx", "https://app.nvcontractorsboard.com/Clients/NVSCB/Public/"
           "ContractorLicenseSearch/ContractorLicenseSearch.aspx", "reachable",
           "Every licensed contractor by trade = buyer list + permit-puller "
           "verification + license-status events. Bulk via public-records request."),

    # ── TIER B: ViewState / session portals (residential, low-volume) ───────
    Source("clark_accela", "Clark County permits (Accela Citizen Access)",
           "accela", "https://citizenaccess.clarkcountynv.gov/CitizenAccess/Cap/"
           "CapHome.aspx?module=Building&TabName=Building", "manual",
           "★ Highest-value signal. PERMIT events (who/where/value/date) + Code "
           "Cases. ViewState portal; 403s the runner -- residential capture."),

    Source("clark_recorder", "Clark County Recorder (deeds / NOD / liens)",
           "aspx", "https://recorderecomm.clarkcountynv.gov/AcclaimWeb/", "manual",
           "★ Distress engine. Search by Document Type + Record Date: DEED, "
           "Notice of Default, Trustee's Sale, Lis Pendens, mechanics/tax liens. "
           "Signals only -- never resell document copies (NV AG alert)."),

    Source("lv_permits", "City of Las Vegas permits",
           "accela", "https://www.lasvegasnevada.gov/", "manual",
           "Incorporated-city permits (separate from county). Same parser as county."),

    Source("henderson_permits", "City of Henderson permits",
           "accela", "https://www.cityofhenderson.com/", "manual",
           "Incorporated-city permits (separate from county)."),

    Source("nlv_permits", "City of North Las Vegas permits",
           "accela", "https://www.cityofnorthlasvegas.com/", "manual",
           "Incorporated-city permits (separate from county)."),

    # ── TIER C: validate-before-build (court / distress) ────────────────────
    Source("clark_courts", "Clark County courts (eviction / probate)",
           "aspx", "https://cvpublicaccess.co.clark.nv.us/eservices/", "manual",
           "Eviction filings (Justice Court) + probate (District Court). NEEDS "
           "VALIDATION + compliance read (FCRA line, NRS 645F outreach rules)."),
]


def by_key(key):
    for s in REGISTRY:
        if s.key == key:
            return s
    return None
