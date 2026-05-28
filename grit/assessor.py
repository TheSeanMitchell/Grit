"""
Assessor enrichment (Alpha 0.102) -- LIVE, FREE, current data.

Breakthrough source (verified 2026-05):
  https://maps.clarkcountynv.gov/assessor/AssessorParcelDetail/parceldetail.aspx
  ?hdnparcel=<APN>&logo=1

A plain GET returns the CURRENT assessor record for one parcel: owner + mailing,
situs address, current assessed/taxable value, last sale (price/date/type), land
use, year built, and structure characteristics. This is the fresh data the 2018
statewide layer lacked.

Parsing is DETERMINISTIC and label-anchored against the real observed page
structure (no blind guessing). Each extracted field maps to a labeled cell.
"""
import html as _html
import re
import urllib.parse
import urllib.request

from . import config

PARCEL_DETAIL = ("https://maps.clarkcountynv.gov/assessor/"
                 "AssessorParcelDetail/parceldetail.aspx")

_LABELS = [
    "Parcel No.", "Location Address", "City/Unincorporated Town",
    "Recorded Document No.", "Recorded Date", "Total Assessed Value",
    "Total Taxable Value", "Estimated Size", "Original Const. Year",
    "Land Use", "Dwelling Units", "1st Floor Sq. Ft.", "Bedrooms",
    "Bathrooms", "Roof Type", "Pool", "Spa", "Type of Construction", "Style",
]

# Connector words / label fragments that are NOT values (skipped when scanning)
_IGNORE = set(_LABELS) | {"Owner", "and", "Mailing Address", "Month/Year",
                         "Sale Type", "Comments", "Vesting"}


def _norm_label(s: str) -> str:
    """Aggressively normalize for tolerant matching: NBSP -> space, lower-case,
    strip trailing punctuation, collapse whitespace. Stops the parser from
    silently missing 'Parcel No' vs 'Parcel No.' vs 'Parcel&nbsp;No.'."""
    if s is None:
        return ""
    t = str(s).replace("\xa0", " ").replace("\u00a0", " ")
    t = t.strip().rstrip(":.,").strip().lower()
    return " ".join(t.split())


# Pre-normalize the ignore set once for fast tolerant comparison
_IGNORE_NORM = {_norm_label(x) for x in _IGNORE}


def fetch_parcel(apn, timeout=20):
    """GET the live parcel-detail page for one APN. Returns raw HTML text."""
    url = f"{PARCEL_DETAIL}?hdnparcel={urllib.parse.quote(str(apn))}&logo=1"
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _flatten(html_text):
    """HTML -> ordered list of visible text cells (each tag boundary = a break)."""
    t = _html.unescape(html_text)
    t = t.replace("\xa0", " ").replace("\u00a0", " ")
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    cells = [re.sub(r"\s+", " ", c).strip() for c in t.split("\n")]
    return [c for c in cells if c]


def _find_label(cells, label):
    """Tolerant label finder. Returns the index of the cell that 'is' the label
    under normalization, or the cell that STARTS with the label as a word
    prefix (handles 'Parcel No. 138-99-...' all in one cell). -1 if not found."""
    target = _norm_label(label)
    for i, c in enumerate(cells):
        nc = _norm_label(c)
        if nc == target:
            return i
        # prefix-as-word: "parcel no" matches the start of "parcel no 138..."
        if nc.startswith(target + " "):
            return i
    return -1


def _value_after(cells, label):
    """First substantive cell after `label`. Handles two layouts:
      (a) label and value in adjacent cells   -> return the next cell
      (b) label and value in the SAME cell    -> return the tail after the label
    Skips glossary echoes (cells starting with '[') and ignored connector words."""
    i = _find_label(cells, label)
    if i < 0:
        return None
    # (b) same-cell: tail after the label text
    nc = _norm_label(cells[i])
    nt = _norm_label(label)
    if nc != nt and nc.startswith(nt + " "):
        tail = cells[i][len(label):].lstrip(" .:,\xa0").strip()
        if tail and _norm_label(tail) not in _IGNORE_NORM and not tail.startswith("["):
            return tail
    # (a) adjacent: scan forward a small window
    for j in range(i + 1, min(i + 6, len(cells))):
        cand = cells[j]
        if cand and _norm_label(cand) not in _IGNORE_NORM and not cand.startswith("["):
            return cand
    return None


def _split_owner(cells):
    """Owner + mailing live in one cell: 'NAME  STREET CITY ST ZIP'. The name is
    the run before the street number; the rest is the mailing address. Tolerant
    of 'Owner', 'OWNER', 'Owner and Mailing Address', etc."""
    raw = None
    for i, c in enumerate(cells):
        nc = _norm_label(c)
        if nc == "owner" or nc.startswith("owner and"):
            for j in range(i + 1, min(i + 8, len(cells))):
                cand = cells[j]
                if cand and _norm_label(cand) not in _IGNORE_NORM and not cand.startswith("["):
                    raw = cand
                    break
            break
    if not raw:
        return None, None
    m = re.search(r"\s(\d{1,6}\s+[A-Z0-9])", raw)
    if m:
        return raw[:m.start()].strip(), raw[m.start():].strip()
    return raw.strip(), None


def _last_number(cells, label):
    """Two fiscal-year columns; take the later numeric cell (current year)."""
    i = _find_label(cells, label)
    if i < 0:
        return None
    nums = []
    for j in range(i + 1, min(i + 4, len(cells))):
        v = cells[j].replace(",", "")
        if re.fullmatch(r"\d+", v):
            nums.append(cells[j])
    return nums[-1] if nums else None


def _norm_sale_date(s):
    """'8/2022' -> '2022-08-01' so it scores on recency like other dates."""
    m = re.match(r"(\d{1,2})\s*/\s*(\d{4})", s.strip())
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}-01"
    return s


def _postprocess_sale(cells, out):
    """'Last Sale Price' cell holds 'PRICE  M/YYYY  SALETYPE' across columns."""
    for i, c in enumerate(cells):
        nc = _norm_label(c)
        if nc.startswith("last sale price"):
            vals = []
            for j in range(i + 1, min(i + 10, len(cells))):
                cand = cells[j]
                if cand and _norm_label(cand) not in _IGNORE_NORM and not cand.startswith("["):
                    vals.append(cand)
                if len(vals) >= 3:
                    break
            if vals:
                out["last_sale_price"] = vals[0]
                if len(vals) > 1:
                    out["last_sale_date"] = _norm_sale_date(vals[1])
                if len(vals) > 2:
                    out["last_sale_type"] = vals[2]
            return


def parse_parcel_detail(html_text):
    """Deterministic extraction. Missing labels => None (never fabricated)."""
    cells = _flatten(html_text)
    owner_name, owner_mailing = _split_owner(cells)
    out = {
        "parcel_apn": _value_after(cells, "Parcel No."),
        "owner_name": owner_name,
        "owner_mailing": owner_mailing,
        "situs_address": _value_after(cells, "Location Address"),
        "city": _value_after(cells, "City/Unincorporated Town"),
        "assessed_value": _last_number(cells, "Total Assessed Value"),
        "taxable_value": _last_number(cells, "Total Taxable Value"),
        "land_use": _value_after(cells, "Land Use"),
        "year_built": _value_after(cells, "Original Const. Year"),
        "lot_size": _value_after(cells, "Estimated Size"),
        "recorded_doc": _value_after(cells, "Recorded Document No."),
        "recorded_date": _value_after(cells, "Recorded Date"),
        "bedrooms": _value_after(cells, "Bedrooms"),
        "bathrooms": _value_after(cells, "Bathrooms"),
        "roof_type": _value_after(cells, "Roof Type"),
        "pool": _value_after(cells, "Pool"),
    }
    _postprocess_sale(cells, out)
    return {k: v for k, v in out.items() if v not in (None, "")}


def enrich_apn(apn, timeout=20):
    """Fetch + parse one parcel. Returns one of:
        {field: value, ...}            -- parsed at least owner_name or situs
        {"_silent": "no-parse", ...}   -- fetch ok but parser extracted nothing
                                          (signals a real parser-coverage gap)
        {"_error": "<type>: <msg>"}    -- fetch failed (network / 404 / timeout)
    Never raises. Real diagnostic states only -- no fabricated success."""
    try:
        html_text = fetch_parcel(apn, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}
    parsed = parse_parcel_detail(html_text)
    # If the page was the "no record found" stub or the labels drifted, the
    # parser returns an empty dict. Mark that explicitly so the pipeline can
    # count silent misses and the operator sees parser-yield in the matrix.
    if not parsed.get("owner_name") and not parsed.get("situs_address"):
        return {"_silent": "no-parse", "_html_bytes": len(html_text), **parsed}
    return parsed
