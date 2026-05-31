"""
Contactability engine (Alpha 0.112).

GRIT's centerpiece is shifting from "find activity" to "find activity we can ACT
on" -- a lead a salesperson can call today. This module reads only REAL contact
fields already on a card and produces a single `contact` object:

  tier        phone > mail > name > none  (best channel actually available)
  phone       the real phone we hold (today: the permit contractor's number)
  phone_owner whose phone it is -- never implies a homeowner phone we don't have
  reachable   True if there's a usable channel beyond a bare name
  score       0-100 ranking: reachability first, then recency, then lead score
              (the hottest lead = immediate activity + a phone in hand)
  channels    every real channel, labelled, for the drawer + call list
  summary     one plain-language line a caller can read and dial from

Doctrine holds: no fabricated phones, no skip-tracing, no invented contacts. If a
field isn't on the card, it isn't in the output. Homeowner phone numbers are not
present in free public records, so the homeowner-direct channel here is the mailing
address; the phone we surface is the contractor's (the way into a live project).
"""
import re


def _digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def norm_phone(p):
    """Format a 10-digit US phone as (NPA) NXX-XXXX. Returns None if not a real
    10/11-digit number -- never invents digits."""
    d = _digits(p)
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) != 10 or d[0] in "01":
        return None
    return f"({d[0:3]}) {d[3:6]}-{d[6:]}"


def best_phone(card):
    for k in ("contractor_phone", "business_phone", "owner_phone"):
        ph = norm_phone(card.get(k))
        if ph:
            return ph, {"contractor_phone": "contractor", "business_phone": "business",
                        "owner_phone": "owner"}[k]
    return None, None


def _channels(card, phone, phone_owner):
    ch = []
    if phone:
        ch.append({"type": "phone", "label": f"{phone_owner.title()} phone",
                   "value": phone, "who": phone_owner})
    if card.get("owner_name"):
        ent = card.get("entity_type")
        lbl = "Owner" + (f" ({ent})" if ent and ent not in ("PERSON", "UNKNOWN") else "")
        ch.append({"type": "owner", "label": lbl, "value": card["owner_name"]})
    if card.get("owner_mailing"):
        ch.append({"type": "mail", "label": "Owner mailing address",
                   "value": card["owner_mailing"], "who": "owner"})
    if card.get("contractors"):
        ch.append({"type": "contractor", "label": "Contractor",
                   "value": card["contractors"][0]})
    if card.get("contractor_license"):
        ch.append({"type": "license", "label": "Contractor license #",
                   "value": card["contractor_license"]})
    if card.get("contractor_address"):
        ch.append({"type": "addr", "label": "Contractor office",
                   "value": card["contractor_address"]})
    if card.get("business_activity"):
        ch.append({"type": "business", "label": "Business at site",
                   "value": card["business_activity"]})
    return ch


_SIG_WORDS = {
    "new_construction": "new-construction", "solar": "solar", "pool_spa": "pool/spa",
    "roofing": "roofing", "demolition": "demolition", "grading_site": "grading",
    "commercial_ti": "commercial tenant-improvement", "public_works": "public-works",
    "fire_life_safety": "fire/life-safety", "telecom_infrastructure": "telecom",
    "certificate_of_occupancy": "certificate-of-occupancy",
}


def _recency_phrase(card):
    age = card.get("age_days")
    if age is None:
        return ""
    if age <= 14:
        return "just filed"
    if age <= 30:
        return "fresh (<30d)"
    if age <= 90:
        return "recent (<90d)"
    if age <= 365:
        return "this year"
    return "older"


def _what(card):
    sigs = card.get("permit_signals") or []
    if sigs:
        words = [_SIG_WORDS.get(s) for s in sigs if _SIG_WORDS.get(s)]
        if words:
            kind = words[0]
            return f"{kind} permit"
    if card.get("trade_tags"):
        return f"{card['trade_tags'][0]} permit"
    if card.get("permit_count"):
        return "permit activity"
    if card.get("code_enforcement_open"):
        return "open code-enforcement case"
    if card.get("last_sale_date"):
        return "recent sale"
    return "property activity"


def _summary(card, phone, phone_owner):
    """One plain-language line for a caller. Built only from real fields."""
    what = _what(card)
    rec = _recency_phrase(card)
    where = card.get("property_city") or card.get("property_jurisdiction") or ""
    head = what + (f" in {where.title()}" if where else "")
    if rec:
        head += f", {rec}"
    owner = card.get("owner_name")
    ent = card.get("entity_type")
    who = ""
    if owner:
        who = f" Owner: {owner}"
        if ent and ent not in ("PERSON", "UNKNOWN"):
            who += f" ({ent})"
        if card.get("owner_out_of_state"):
            who += " — out-of-state"
        who += "."
    # the action line: how to reach
    if phone and phone_owner == "contractor":
        act = f" Call the contractor {card.get('contractors',[''])[0]} at {phone}."
    elif phone:
        act = f" Call {phone} ({phone_owner})."
    elif card.get("owner_mailing"):
        act = f" No phone on file — owner mailing: {card['owner_mailing']}."
    elif owner:
        act = " No phone or mailing on file — owner name only."
    else:
        act = " No contact channel on file."
    return (head + "." + who + act).strip()


def classify(card):
    phone, phone_owner = best_phone(card)
    has_mail = bool(card.get("owner_mailing"))
    has_name = bool(card.get("owner_name"))
    if phone:
        tier = "phone"
    elif has_mail:
        tier = "mail"
    elif has_name:
        tier = "name"
    else:
        tier = "none"

    # ranking: reachability dominates, then recency, then the lead's own score
    age = card.get("age_days")
    recency = 1.0 if (age is not None and age <= 30) else \
        0.7 if (age is not None and age <= 90) else \
        0.45 if (age is not None and age <= 365) else 0.25
    cs = 0
    if phone:
        cs += 58
    elif has_mail:
        cs += 30
    elif has_name:
        cs += 12
    cs += int(recency * 27)
    cs += min(int((card.get("score") or 0) / 10), 15)

    card["contact"] = {
        "tier": tier,
        "phone": phone,
        "phone_owner": phone_owner,
        "reachable": tier in ("phone", "mail"),
        "score": min(cs, 100),
        "channels": _channels(card, phone, phone_owner),
        "summary": _summary(card, phone, phone_owner),
    }
    return card["contact"]


def stats(cards):
    """Warehouse-level contactability coverage for the dashboard header."""
    n = len(cards) or 1
    phone = sum(1 for c in cards if (c.get("contact") or {}).get("tier") == "phone")
    mail = sum(1 for c in cards if (c.get("contact") or {}).get("tier") == "mail")
    name = sum(1 for c in cards if (c.get("contact") or {}).get("tier") == "name")
    none = sum(1 for c in cards if (c.get("contact") or {}).get("tier") == "none")
    reachable = phone + mail
    hot = sum(1 for c in cards if (c.get("contact") or {}).get("tier") == "phone"
              and (c.get("age_days") is not None and c["age_days"] <= 30))
    return {
        "total": len(cards),
        "with_phone": phone, "with_mail_only": mail, "name_only": name, "no_channel": none,
        "reachable": reachable, "reachable_pct": round(100 * reachable / n, 1),
        "phone_pct": round(100 * phone / n, 1),
        "hot_phone_immediate": hot,
    }
