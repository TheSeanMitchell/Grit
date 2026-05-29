"""
Permit ingestion -- Accela Citizen Access (the permit gate).

Clark County permits are the single highest-value live activity signal: a permit
pulled last week is a far stronger "active right now" flag than a sale (sales are
a ~1-2%/quarter base-rate event; a metro issues thousands of permits a month).
Permits are what fills the IMMEDIATE temporal bucket with real activity.

ARCHITECTURAL REALITY (not a bug): the ACA portal is an ASP.NET ViewState site
that 403s datacenter IPs. So this RUNS LOCALLY from the operator's residential
Las Vegas IP -- `python -m grit permits`. The cloud runner cannot reach it.

DESIGN -- capture-then-build, self-calibrating:
  1. GET the General Search page (public, no login) + pull the ASP.NET state.
  2. POST a date-range search (permits issued in the last N days).
  3. Parse the results GridView with a HEADER-DRIVEN parser (maps columns by
     their labels, so it adapts to column-order differences).
  4. Emit PERMIT events (deterministic; nothing emitted without real rows).
  5. If 0 rows parse, SAVE the raw HTML to docs/data/permit_samples/ and report
     -- never fabricate. One real capture finishes calibration.

No login, low volume, polite throttling. Public records only.
"""
import datetime as dt
import http.cookiejar
import os
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from . import config

ACA_BASE = "https://aca-prod.accela.com/CLARKCO"
ACA_SEARCH = ACA_BASE + "/Cap/CapHome.aspx?module=Building&TabName=Building"

# Column-label synonyms -> canonical field. Header-driven: depends on the labels
# Accela renders, NOT on column order.
_COL_SYNONYMS = {
    "date":        ["date", "open date", "opened", "issued", "issue date", "file date"],
    "record":      ["record number", "record #", "permit number", "permit #",
                    "case number", "number", "record"],
    "type":        ["record type", "permit type", "type"],
    "description": ["description", "project name", "project", "short notes"],
    "address":     ["address", "site address", "location"],
    "status":      ["status", "record status"],
}


# ---- HTTP (session-aware: ViewState needs the cookie set on the GET) --------
def _opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return op


def _get(op, url, timeout=30):
    with op.open(urllib.request.Request(url), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _post(op, url, data, referer, timeout=40):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Referer": referer})
    with op.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---- ASP.NET ViewState extraction ------------------------------------------
def extract_aspnet_state(html):
    state = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
                 "__EVENTTARGET", "__EVENTARGUMENT", "__VIEWSTATEENCRYPTED"):
        m = re.search(r'id="%s"[^>]*value="([^"]*)"' % re.escape(name), html)
        state[name] = m.group(1) if m else ""
    return state


def _find_field(html, substr):
    for m in re.finditer(r'(?:name|id)="([^"]*%s[^"]*)"' % re.escape(substr), html, re.I):
        return m.group(1)
    return None


def build_search_post(html, days_back=14):
    """General Search POST for permits issued in the last `days_back` days.
    Field names discovered from the page with ACA conventions as fallback."""
    state = extract_aspnet_state(html)
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=days_back)).strftime("%m/%d/%Y")
    d_to = today.strftime("%m/%d/%Y")
    from_field = _find_field(html, "FromDate") or _find_field(html, "txtGSStartDate")
    to_field   = _find_field(html, "ToDate")   or _find_field(html, "txtGSEndDate")
    btn = (_find_field(html, "btnNewSearch") or _find_field(html, "btnSearch")
           or "ctl00$PlaceHolderMain$btnNewSearch")
    post = dict(state)
    post["__EVENTTARGET"] = ""
    post["__EVENTARGUMENT"] = ""
    if from_field:
        post[from_field] = d_from
    if to_field:
        post[to_field] = d_to
    post[btn] = "Search"
    ok = bool(from_field and to_field)
    return post, ok, {"from": d_from, "to": d_to, "from_field": from_field,
                      "to_field": to_field, "button": btn}


# ---- Results GridView parser (header-driven, deterministic) -----------------
class _TableExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._tbl, self._row, self._cell = [], None, None, None
        self._href = None; self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._tbl = []
        elif tag == "tr" and self._tbl is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []; self._href = None; self._in_cell = True
        elif tag == "a" and self._in_cell and self._href is None:
            for k, v in attrs:
                if k == "href":
                    self._href = v

    def handle_data(self, data):
        if self._in_cell and self._cell is not None:
            t = data.strip()
            if t:
                self._cell.append(t)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append({"text": " ".join(self._cell).strip(), "href": self._href})
            self._cell = None; self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._tbl.append(self._row)
            self._row = None
        elif tag == "table" and self._tbl is not None:
            self.tables.append(self._tbl); self._tbl = None


def _match_columns(header_cells):
    labels = [c["text"].lower().strip() for c in header_cells]
    colmap = {}
    for field, syns in _COL_SYNONYMS.items():
        for idx, lab in enumerate(labels):
            if lab and any(s == lab or s in lab for s in syns):
                colmap[field] = idx
                break
    return colmap


def parse_results_grid(html):
    """Return a list of permit dicts from the results GridView. Header-driven, so
    column order doesn't matter. [] if no parseable permit grid is found."""
    ex = _TableExtractor()
    try:
        ex.feed(html)
    except Exception:
        return []
    best = None
    for tbl in ex.tables:
        if len(tbl) < 2:
            continue
        colmap = _match_columns(tbl[0])
        if "record" in colmap and ("date" in colmap or "type" in colmap):
            if best is None or len(tbl) > len(best[0]):
                best = (tbl, colmap)
    if not best:
        return []
    rows, colmap = best
    out = []
    for r in rows[1:]:
        def cell(field):
            i = colmap.get(field)
            return r[i]["text"] if (i is not None and i < len(r)) else None
        rec = cell("record")
        if not rec:
            continue
        out.append({"record": rec, "date": _norm_date(cell("date")),
                    "type": cell("type"), "description": cell("description"),
                    "address": cell("address"), "status": cell("status")})
    return out


def _norm_date(s):
    if not s:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else s


# ---- Categorization + event emission ---------------------------------------
def categorize(permit):
    blob = " ".join(str(permit.get(k) or "") for k in ("type", "description")).lower()
    return [trade for trade, kws in config.TRADE_KEYWORDS.items()
            if any(k in blob for k in kws)]


def to_events(permits, source="clark_accela"):
    from .events import Event
    evs = []
    for p in permits:
        if not p.get("record"):
            continue
        trades = categorize(p)
        evs.append(Event(
            kind="PERMIT", date=p.get("date") or dt.date.today().isoformat(),
            source=source, address=p.get("address"),
            description=f"{p.get('type') or 'permit'} {p.get('record')}"
                        + (f" -- {p['description']}" if p.get("description") else "")
                        + (f" [{p['status']}]" if p.get("status") else ""),
            trade_tag=trades[0] if trades else None, raw=p))
    return evs


# ---- Orchestration (run locally; residential IP) ---------------------------
def harvest_permits(days_back=14, save_dir="docs/data/permit_samples"):
    op = _opener()
    report = {"step": None, "rows": 0, "saved": None, "search_meta": None}
    try:
        report["step"] = "get_search_page"
        page = _get(op, ACA_SEARCH)
        post, ok, meta = build_search_post(page, days_back=days_back)
        report["search_meta"] = meta
        if not ok:
            _save(save_dir, "aca_search_page.html", page)
            report.update(step="no_date_fields", saved=save_dir); return [], report
        time.sleep(1.5)
        report["step"] = "submit_search"
        results = _post(op, ACA_SEARCH, post, referer=ACA_SEARCH)
        permits = parse_results_grid(results)
        report["rows"] = len(permits)
        if not permits:
            _save(save_dir, "aca_results.html", results)
            report.update(step="no_rows_parsed", saved=save_dir); return [], report
        report["step"] = "ok"
        return to_events(permits), report
    except Exception as e:  # noqa: BLE001
        report.update(step="error", error=f"{type(e).__name__}: {e}")
        return [], report


def _save(d, name, text):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w") as f:
        f.write(text)


def capture_search_form(out_dir="docs/data/permit_samples"):
    op = _opener()
    try:
        page = _get(op, ACA_SEARCH)
        _save(out_dir, "aca_search_page.html", page)
        return [{"label": "aca_search_page", "bytes": len(page), "saved": out_dir}]
    except Exception as e:  # noqa: BLE001
        return [{"error": f"{type(e).__name__}: {e}"}]
