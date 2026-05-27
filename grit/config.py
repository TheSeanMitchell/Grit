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

# A configured layer query URL. Leave as None to force `discover` first.
# Once `discover` finds the parcel layer, paste its .../FeatureServer/<id> URL here.
CLARK_PARCEL_LAYER = None  # e.g. ".../SomeService/FeatureServer/13"

# Field auto-mapping. The harvester matches a source's REAL field names against
# these fragments (case-insensitive substring) so it adapts to whatever the
# live layer exposes. Order = priority.
FIELD_HINTS = {
    "parcel_apn":    ["apn", "parcelno", "parcel_no", "parcel", "pcl"],
    "owner_name":    ["owner1", "ownername", "owner_name", "owner"],
    "owner_mailing": ["mailaddr", "mail_addr", "mailing", "mailadr", "owneraddr"],
    "situs_address": ["situs", "siteaddr", "site_addr", "propaddr", "address", "location"],
    "city":          ["situscity", "city"],
    "zip":           ["situszip", "zip", "zipcode", "postal"],
    "land_use":      ["landuse", "land_use", "usecode", "usedesc", "property_use", "luse"],
    "assessed_value":["assessed", "totval", "total_value", "taxvalue", "av_total", "value"],
    "last_sale_date":["saledate", "sale_date", "lastsale", "deed_date", "recdate"],
    "last_sale_price":["saleprice", "sale_price", "saleamt", "deed_amt", "price"],
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

# Where harvested JSON is written (served by GitHub Pages).
DATA_DIR = "docs/data"
CARDS_FILE = "docs/data/cards.json"
HEALTH_FILE = "docs/data/health.json"

# Politeness: page size + max pages per harvest (keeps the free Action well-behaved).
PAGE_SIZE = 1000
MAX_PAGES = 5
HTTP_TIMEOUT = 30
USER_AGENT = "GRIT-harvester/0.1 (public-records research; contact: repo owner)"
