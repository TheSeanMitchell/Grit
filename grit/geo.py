"""
Southern Nevada jurisdiction resolution (Alpha 0.106).

Full map activation surfaced a gap: ~500 geocoded parcels carried a real
coordinate but no jurisdiction label, because the statewide parcel layer left
their city field blank. They plot fine — the gap is the *label* the coverage
audit needs.

This module resolves a property jurisdiction from the most authoritative field
available and records HOW it was resolved, so the coverage report can separate
authoritative labels from coordinate-derived ones. Nothing is fabricated: a
coordinate-derived label is a documented geographic derivation, flagged as such;
a parcel with no coordinate and no city stays unresolved.

Order of authority:
  1. permit-feed   -- a City permit is, by definition, that city's jurisdiction
  2. assessor-city -- the parcel's own city field
  3. situs         -- the city embedded in the situs line (the layer often
                      drops the city into the address field)
  4. coordinate    -- point-in-approximate-jurisdiction (flagged, lower conf.)
  5. county        -- inside the Clark County valley but otherwise unplaced
"""

# Canonical Southern Nevada jurisdiction labels.
LABEL = {
    "LAS VEGAS": "Las Vegas", "NORTH LAS VEGAS": "North Las Vegas",
    "HENDERSON": "Henderson", "BOULDER CITY": "Boulder City",
    "ENTERPRISE": "Enterprise", "SPRING VALLEY": "Spring Valley",
    "SUNRISE MANOR": "Sunrise Manor", "PARADISE": "Paradise",
    "WHITNEY": "Whitney", "SUMMERLIN": "Summerlin", "MESQUITE": "Mesquite",
    "MOAPA": "Moapa", "MOAPA VALLEY": "Moapa Valley", "SEARCHLIGHT": "Searchlight",
    "LAUGHLIN": "Laughlin", "JEAN": "Jean", "BLUE DIAMOND": "Blue Diamond",
    "INDIAN SPRINGS": "Indian Springs", "WINCHESTER": "Winchester",
    "MOUNT CHARLESTON": "Mount Charleston", "MT CHARLESTON": "Mount Charleston",
    "CLARK COUNTY": "Clark County", "LONE MOUNTAIN": "Lone Mountain",
}

# The 19 jurisdictions the v0.106 coverage audit must account for.
SONV_JURISDICTIONS = [
    "Las Vegas", "Clark County", "North Las Vegas", "Henderson", "Boulder City",
    "Mesquite", "Moapa", "Moapa Valley", "Searchlight", "Jean", "Mount Charleston",
    "Lee Canyon", "Enterprise", "Paradise", "Spring Valley", "Summerlin",
    "Whitney", "Sunrise Manor", "Winchester",
]

# Approximate jurisdiction boxes (lat_min, lat_max, lng_min, lng_max), checked
# most-specific first. These are coarse derivations used ONLY when no
# authoritative city is available, and every hit is flagged source="coordinate"
# so the audit never presents a guess as ground truth. Authoritative refinement
# arrives when geocode.py pulls the parcel-layer city on the next harvest.
_BOXES = [
    ("Boulder City",     35.93, 36.04, -114.92, -114.78),
    ("Mesquite",         36.76, 36.86, -114.12, -114.00),
    ("Laughlin",         35.10, 35.22, -114.62, -114.52),
    ("Moapa Valley",     36.50, 36.72, -114.50, -114.36),
    ("Summerlin",        36.12, 36.22, -115.36, -115.28),
    ("Enterprise",       35.95, 36.05, -115.30, -115.10),
    ("Henderson",        35.95, 36.10, -115.10, -114.90),
    ("North Las Vegas",  36.20, 36.40, -115.22, -115.00),
    ("Spring Valley",    36.05, 36.16, -115.34, -115.22),
    ("Sunrise Manor",    36.14, 36.27, -115.10, -114.96),
    ("Whitney",          36.05, 36.12, -115.08, -114.98),
    ("Paradise",         36.04, 36.13, -115.20, -115.06),
    ("Winchester",       36.12, 36.17, -115.14, -115.06),
    ("Las Vegas",        36.10, 36.30, -115.32, -115.06),
]
# Outer envelope of the populated Clark County valley.
_COUNTY_BOX = (35.0, 37.0, -115.9, -114.0)


def label_for(name):
    if not name:
        return None
    return LABEL.get(name.strip().upper())


def _in(lat, lng, box):
    return box[0] <= lat <= box[1] and box[2] <= lng <= box[3]


def jurisdiction_for_coord(lat, lng):
    """Approximate jurisdiction for a coordinate, or 'Clark County' if inside the
    valley envelope but unplaced, or None if outside the region entirely."""
    if lat is None or lng is None:
        return None
    for name, a, b, c, d in _BOXES:
        if _in(lat, lng, (a, b, c, d)):
            return name
    if _in(lat, lng, _COUNTY_BOX):
        return "Clark County"
    return None


def resolve(card):
    """Return (jurisdiction, source) using the most authoritative field
    available. Pure function -- does not mutate the card."""
    if card.get("source") == "clv_permit":
        return "Las Vegas", "permit-feed"
    city = label_for(card.get("city") or card.get("situs_city"))
    if city:
        return city, "assessor-city"
    situs = label_for(card.get("situs_address"))
    if situs:
        return situs, "situs"
    coord = jurisdiction_for_coord(card.get("lat"), card.get("lng"))
    if coord:
        return coord, ("county" if coord == "Clark County" else "coordinate")
    return None, None


def stamp(card):
    """Attach property_jurisdiction + jurisdiction_source. Mutates and returns
    the card. Never alters coordinates or any owner-origin field."""
    j, src = resolve(card)
    if j:
        card["property_jurisdiction"] = j
        card["jurisdiction"] = j
        card["jurisdiction_source"] = src
    return card
