"""
GRIT engine configuration.

Everything here is real and editable. No source is invented; each entry below
is a live public endpoint confirmed to exist. Where an exact layer index still
needs confirming against the live server, that is marked and resolved by the
`discover` command at runtime -- never guessed into the output.
"""

# ---------------------------------------------------------------------------
# Target geography: the Las Vegas metro zone (Clark County).
# WGS84 (lon/lat) envelope, generous enough to cover the City of Las Vegas,
# Henderson, North Las Vegas, Summerlin, Enterprise/Paradise/Spring Valley,
# Boulder City, and out toward Moapa Valley.
# ---------------------------------------------------------------------------
METRO_BBOX = {
    "xmin": -115.55,  # west (toward Red Rock / Summerlin)
    "ymin": 35.85,    # south (toward Sloan / Jean)
    "xmax": -114.35,  # east (toward Lake Mead / Moapa)
    "ymax": 36.80,    # north (toward Moapa Valley / Apex)
}

# ---------------------------------------------------------------------------
# Clark County GIS (CONFIRMED LIVE ArcGIS REST server).
# The `discover` command enumerates folders/services/layers and finds the
# parcel/owner/address layer automatically by inspecting real field names.
# ---------------------------------------------------------------------------
CLARK_ARCGIS_ROOT = "https://gisgate.co.clark.nv.us/arcgis/rest/services"

# Servers to crawl during auto-discovery, richest first. maps.clarkcountynv.gov
# is the modern server with Assessor / BuildingDepartment / Accela folders.
DISCOVERY_ROOTS = [
    "https://maps.clarkcountynv.gov/arcgis/rest/services",
    "https://gisgate.co.clark.nv.us/arcgis/rest/services",
]

# Manual override: pin one layer and skip everything below. Usually leave None.
CLARK_PARCEL_LAYER = None

# Ordered, KNOWN parcel/owner candidates. The harvester samples each, checks that
# owner/address fields are actually POPULATED, and uses the richest one. A candidate
# may carry an explicit field_map (use when we already know the real column names)
# and a `where` filter. First good one wins; if all fail, auto-discovery runs.
PARCEL_CANDIDATES = [
    {
        # Fresh county Assessor parcels (modern server). Fields auto-mapped.
        "name": "Clark Assessor parcels (current)",
        "url": "https://maps.clarkcountynv.gov/arcgis/rest/services/GISMO/AssessorMap/FeatureServer/1",
        "where": "1=1",
        "vintage": "current",
    },
    {
        # CONFIRMED schema fallback: statewide parcels w/ real owner + site address.
        # Vintage 2018 -- owner names may be stale; site address is stable.
        "name": "NV statewide parcels (owner+address, 2018)",
        "url": "https://gis.dot.nv.gov/agsphs/rest/services/Reference/Statewide_Parcels/MapServer/0",
        "where": "County='Clark'",
        "vintage": "2018-12-31",
        "field_map": {
            "parcel_apn": "APN",
            "owner_name": "OwnerName",
            "situs_address": "SiteAddress",
            "city": "SiteCity",
        },
    },
]

# gisgate.co.clark.nv.us serves a hostname-mismatched TLS certificate (confirmed
# 2026-05). It's a public, read-only government endpoint, so we skip cert
# verification for it to connect. Tradeoff: no protection against tampering in
# transit -- acceptable for public parcel data; do NOT reuse this for anything
# involving credentials. Set False once/if the county fixes their certificate.
ARCGIS_INSECURE_SSL = True

# Field auto-mapping. The harvester matches a source's REAL field names against
# these fragments (case-insensitive substring) so it adapts to whatever the
# live layer exposes. Order = priority.
FIELD_HINTS = {
    "parcel_apn":    ["apn", "parcelno", "parcel_no", "pcl_no", "parcelid"],
    "owner_name":    ["owner1", "ownername", "owner_name", "ownerofrec", "owner"],
    "owner_mailing": ["owneraddress", "owner_addr", "owneraddr", "mailaddr",
                      "mail_addr", "mailingadd", "mailing"],
    "situs_address": ["situsaddr", "situs_addr", "situs", "siteaddress",
                      "site_addr", "siteaddr", "propaddr", "physical_addr",
                      "address_full", "full_address", "street_address"],
    "city":          ["situscity", "sitecity", "site_city", "city"],
    "zip":           ["situszip", "sitezip", "zipcode", "zip", "postal"],
    "land_use":      ["landuse", "land_use", "usecode", "usedesc",
                      "property_use", "luse", "luc"],
    "assessed_value":["assessed", "totval", "total_value", "taxvalue",
                      "av_total", "totalvalue", "assdvalue"],
    "last_sale_date":["saledate", "sale_date", "lastsale", "deed_date", "recdate"],
    "last_sale_price":["saleprice", "sale_price", "saleamt", "deed_amt"],
}

# Substrings that DISQUALIFY a field from matching the given card field. Stops the
# "Address_Parcel_Number" -> situs_address false match that produced empty cards.
FIELD_NEGATIVE = {
    "situs_address": ["parcel", "number", "apn", "pcl", "_no", "subdivision"],
    "owner_mailing": ["parcel", "apn"],
}

# Trade tags inferred from land-use / permit description text (substring match).
TRADE_KEYWORDS = {
    "roofing":     ["roof", "reroof", "shingle"],
    "hvac":        ["hvac", "air condition", "a/c", "mechanical", "furnace", "heat pump"],
    "solar":       ["solar", "photovoltaic", "pv "],
    "plumbing":    ["plumb", "water heater", "repipe", "sewer"],
    "electrical":  ["electric", "panel", "rewire", "ev charger"],
    "pools":       ["pool", "spa"],
    "landscaping": ["landscap", "yard", "irrigation", "turf"],
    "remodeling":  ["remodel", "addition", "renovat", "tenant improvement", "ti ", "kitchen", "bath"],
    "fencing":     ["fence", "wall", "block wall"],
    "concrete":    ["concrete", "driveway", "slab", "flatwork"],
    "security":    ["alarm", "security", "low voltage", "camera"],
    "pest":        ["pest", "termite"],
}

# ── Version ─────────────────────────────────────────────────────────────────
VERSION = "0.103"

# Entity normalization tokens. Order in pipeline.classify_owner is:
#   HOA → GOVERNMENT → LLC/INC → TRUST → COMMERCIAL → PERSON
ENTITY_TOKENS = {
    "HOA": [" HOA", " H O A ", "HOMEOWNERS", "OWNERS ASSN", "OWNERS ASSOCIATION",
            "CONDOMINIUM ASSN", "MASTER ASSN", "COMMUNITY ASSN", "TOWNHOMES ASSN",
            "MAINTENANCE ASSN"],
    "GOVERNMENT": ["CITY OF", "COUNTY OF", "STATE OF", "CLARK COUNTY",
                   "LAS VEGAS REDEVELOPMENT", "SCHOOL DISTRICT", "WATER DISTRICT",
                   "REGIONAL TRANSPORTATION", "DEPARTMENT OF", "UNITED STATES",
                   " AUTHORITY", "BUREAU OF", "BOARD OF EDUCATION", "MUNICIPAL",
                   "PUBLIC WORKS", "REDEVELOPMENT AGENCY"],
    "LLC":        [" LLC", " L L C", " L.L.C", " INC", " INCORPORATED", " CORP",
                   " CORPORATION", " LP", " L P", " LTD"],
    "TRUST":      ["TRUST", " TR "],
    "COMMERCIAL": ["PROPERTIES", "HOLDINGS", "INVESTMENTS", "CAPITAL", "VENTURES",
                   "GROUP", "PARTNERS", "BUILDERS", "DEVELOPMENT", "REALTY",
                   "PROPERTY MGMT", "MANAGEMENT", " HOMES"],
}

# Base score by entity type. PERSON > LLC ≈ TRUST > COMMERCIAL >> HOA/GOV.
# LLCs score high because absentee LLC owners are often investors/flippers
# (high project frequency = great leads for contractor work).
ENTITY_BASE_SCORE = {
    "PERSON": 30, "LLC": 25, "TRUST": 22, "COMMERCIAL": 18,
    "UNKNOWN": 8, "HOA": 0, "GOVERNMENT": 0,
}

# Geographic clustering: how many cards within this radius count as "neighbors"
CLUSTER_RADIUS_M = 500
CLUSTER_MAX_BONUS = 10  # bonus added at saturation (10+ neighbors)

# Owner-name tokens that mark a record as NOT an individual-homeowner lead
# (HOAs, government, large associations). NOTE: trusts and LLCs are intentionally
# NOT here -- many real homeowners hold title in a family trust, and an LLC is
# often an investor/flipper = a legitimate lead.
NON_LEAD_OWNER_TOKENS = [
    "HOMEOWNER", " HOA", "HOA ", "ASSOCIATION", " ASSN", "MASTER ASSN",
    "COMMUNITY ASSN", "CITY OF", "COUNTY OF", "STATE OF", "CLARK COUNTY",
    "SCHOOL DISTRICT", "WATER DISTRICT", " AUTHORITY", "CHURCH", "MINISTRIES",
    "DEPARTMENT OF", "UNITED STATES", "BUREAU OF", "REGIONAL",
]

# Owner tokens that suggest an absentee investor/business (still a lead, often a
# GOOD one for contractors -- flips/rentals need work), used for tagging only.
INVESTOR_OWNER_TOKENS = ["LLC", " INC", "INCORPORATED", " LP", "L P", "PROPERTIES",
                         "HOLDINGS", "CAPITAL", "INVESTMENTS", "GROUP", "VENTURES"]

# Where harvested JSON is written (served by GitHub Pages).
DATA_DIR = "docs/data"
CARDS_FILE = "docs/data/cards.json"
HEALTH_FILE = "docs/data/health.json"

# Politeness: page size + max pages per harvest (keeps the free Action well-behaved).
CARDS_MAX = 500   # keep only the top-scored leads in the console output
CARDS_ENRICH_MAX = 150  # live Assessor enrichment for top N leads/run (current
                        # owner/value/sale). Reliable floor even if the bulk
                        # owner layer 5xx's. ~75s at ENRICH_DELAY spacing.
ENRICH_DELAY = 0.5      # seconds between per-APN Assessor fetches (be polite)
PAGE_SIZE = 1000
MAX_PAGES = 5
HTTP_TIMEOUT = 30
USER_AGENT = "GRIT-harvester/0.1 (public-records research; contact: repo owner)"
