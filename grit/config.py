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

# ---------------------------------------------------------------------------
# Geocoding spine (0.105). Permits ship without usable point geometry, so we
# resolve each permit's parcel APN to a real centroid here. This is the modern
# county Assessor parcel layer -- it exposes APN + geometry for EVERY parcel,
# which is exactly what an APN->point lookup needs (the owner data it lacks is
# why it isn't the harvest base). Centroids are real; unresolved APNs stay
# coordless (no fabricated pins). Empty = geocoding reports 'needs_config'.
# ---------------------------------------------------------------------------
PARCEL_GEOCODE_LAYER = ("https://maps.clarkcountynv.gov/arcgis/rest/services/"
                        "GISMO/AssessorMap/FeatureServer/1")
GEOCODE_DELAY = 0.15    # seconds between geocode batches (be polite)

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
                      "av_total", "totalvalue", "assdvalue", "totlvalue", "fullvalue"],
    "land_value":    ["landval", "land_value", "landvalue", "av_land", "lndvalue", "assdland"],
    "improvement_value":["imprval", "improvement", "imp_value", "av_imp", "impvalue",
                      "improvementvalue", "bldgvalue", "assdimp"],
    "building_sqft": ["bldgsqft", "buildingsqft", "sqft", "sqft_living", "livingarea",
                      "totsqft", "bldg_sqft", "gross_sqft", "finsqft", "structsqft"],
    "lot_sqft":      ["lotsqft", "lot_sqft", "lotsize", "land_sqft", "parcelsqft",
                      "lot_size", "acreage", "acres", "landsqft"],
    "year_built":    ["yearbuilt", "year_built", "yrblt", "actyrblt", "constyear",
                      "yearblt", "effyrblt", "yr_built"],
    "bedrooms":      ["bedrooms", "beds", "bedroom", "bedrm", "bdrm", "nbed",
                      "num_bed", "bed_rms", "bedrms", "bed"],
    "bathrooms":     ["bathrooms", "baths", "bathroom", "bathrm", "nbath",
                      "num_bath", "bath_rms", "bathrms", "fullbath", "bath"],
    "property_use_code":["usecode", "use_code", "luc", "luccode", "proptype",
                      "propertyuse", "use_cd", "class"],
    "last_sale_date":["saledate", "sale_date", "lastsale", "deed_date", "recdate",
                      "salesdate", "transferdate", "doc_date"],
    "last_sale_price":["saleprice", "sale_price", "saleamt", "deed_amt", "salesprice",
                      "transferamt", "doc_amt", "saleamount"],
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
VERSION = "0.112"

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
CONTRACTORS_FILE = "docs/data/contractors.json"   # 0.105 contractor leaderboard
COVERAGE_FILE = "docs/data/coverage.json"         # 0.105 completeness + category matrix
WAREHOUSE_DIR = "docs/data/warehouse"             # 0.105 append-only ledger

# Politeness: page size + max pages per harvest (keeps the free Action well-behaved).
# 0.105 opens the map up: keep a much wider parcel base (was 500) so the console
# shows the whole metro, not just the top-scored new-construction cluster. The
# permit activity layer (geocoded) spreads across every neighborhood on top.
CARDS_MAX = 4000  # 0.108: raised from 1500. The free parcel layer carries
                  # address+owner+mailing+land-use for the whole valley, so
                  # breadth is bounded by us, not the data. Beyond ~10-15k cards
                  # the static-JSON/browser-pin model strains (slim records or
                  # vector tiles become necessary) -- a deliberate ceiling.
CARDS_ENRICH_MAX = 150  # live Assessor enrichment for top N leads/run (current
                        # owner/value/sale). Reliable floor even if the bulk
                        # owner layer 5xx's. ~75s at ENRICH_DELAY spacing.
PERMIT_DAYS_BACK = 90   # CLV permit window pulled each harvest (cloud-native)
# Paste the City of Las Vegas "Building Permits" FeatureServer LAYER url here
# (portal: opendataportal-lasvegas.opendata.arcgis.com/datasets/building-permits
#  -> "I Want To Use This" -> API Resources -> GeoJSON/FeatureServer url, ending /0).
# Empty = permit source reports 'needs_config' (no error). ArcGIS REST = cloud-native.
CLV_PERMITS_FEATURESERVER = "https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/OpenData_Building_Permits_/FeatureServer/0"

# ── 0.109 FREE DATA SATURATION ──────────────────────────────────────────────
# Every additional FREE signal feed GRIT can pull, by ArcGIS Online item id.
# The connector (free_sources.py) resolves each item's live FeatureServer URL at
# harvest time, so we never hardcode a service name that could move. All of these
# are free public open data on the same ArcGIS Hub platform as the permit feed.
#   - Code Enforcement Violations (CLV): violation type + status + APN + coords,
#     since 2015 -> per-property DISTRESS signal (and new distress leads).
#   - CLV Business Licenses: name + type + status + activity + location, daily
#     -> commercial / entity signal.
# Item ids were confirmed from the City of Las Vegas open data portal.
FREE_SOURCES_ENABLED = True
HENDERSON_PERMITS_ENABLED = True   # 0.110: City of Henderson DSC permits (Socrata)
FREE_SOURCE_MAX = 4000          # cap records pulled per free source per harvest
CLV_OPENDATA_ITEMS = {
    "code_enforcement": "f48d19416d5546e5b9ee12f9746ecaa9",
    "business_licenses": "f6b923ee5eb9450baf6adebaf0f307ed",
}
# Henderson business licenses (free ArcGIS Hub item) -- 0.111
HENDERSON_OPENDATA_ITEMS = {
    "business_licenses": "b86e999491454c4290af161192ad0eba_0",
}
# LVMPD crime, free (opendata.lvmpd.com). Calls-for-service, last 30 days, geocoded
# -> wired as an AREA activity signal in 0.111. Verified item id.
LVMPD_CRIME_ITEM = "6a371d1a491a4a0794578b031859c768_0"
ENRICH_DELAY = 0.5      # seconds between per-APN Assessor fetches (be polite)
PAGE_SIZE = 1000
MAX_PAGES = 16          # 0.105: wider candidate pool (was 5) for metro-wide spread
HTTP_TIMEOUT = 30
USER_AGENT = "GRIT-harvester/0.1 (public-records research; contact: repo owner)"
