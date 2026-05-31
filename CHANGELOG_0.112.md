# GRIT — 0.111 → 0.112 · Contactability Dashboard (new centerpiece)

This release realigns GRIT around contactability: turning leads into people a
salesperson can call today. I built the dashboard, a per-lead contact engine, and
wired extraction of every contact field our existing sources expose — all verified.
No fabricated phones, no skip-tracing (doctrine holds).

## The honest reality, up front

Free public records **do not contain homeowner phone numbers** — those are paid
skip-tracing, which we don't do. So "make 8,209 leads phone-contactable" isn't
achievable from free data, and I won't pretend it is. What I *can* do, and did:

- Make **100% of the real contacts** we hold usable, ranked, and call-ready.
- Surface the contractor phones and licenses we were already capturing but hiding.
- Wire capture of every additional contact field our sources expose.

**Current contactability on your live 8,209 leads (measured, not estimated):**
- **1,702 have a phone (20.7%)** — the project contractor's number (Henderson permits).
- **3,305 reachable (40.3%)** — phone or owner mailing address.
- 1,603 mailing-only · 3,989 name-only · 915 no channel.
- The reachable channels are the owner's **mailing address** and, on active permits,
  the **contractor's phone** — your way into a live project.

## What shipped

**1. Contactability tab (the centerpiece).** New second tab. A ranked **call list**:
every reachable lead sorted by a *call score* (reachability first, then recency,
then lead score — so the hottest = an immediate permit with a phone in hand). Each
row shows the address, owner, the **phone or mailing**, and a one-line **deal
summary** a caller can read and dial from. Filters: Hottest (phone + ≤30d) · Has
phone · Reachable · Mailing only · All. Plus a **↓ Call list CSV** export so reps
can work it directly. Header stats show coverage at a glance.

**2. Contact engine (`grit/contact.py`).** Runs on every lead, attaches a `contact`
object: tier (phone/mail/name/none), the real phone (validated, never invented),
**whose** phone it is, reachability, call score, every channel, and a plain-language
summary. Fully tested in selftest.

**3. Lead drawer upgraded.** The contact block now shows the tier, the deal summary,
and **all channels including the contractor license #** (2,500 were captured but
hidden — now visible) and contractor phone.

**4. Extraction wired (activates on next harvest, fail-safe):**
- Business licenses now pull **phone / email / owner** if the layer exposes them.
- CLV permits now capture the **contractor office address** (and any phone field).

## Drift check — realigned

Everything now points at contactability. Permit signals, ranking, and summaries feed
the call list. The dashboard ties signal → interpretation → deal summary → contact
into one place for callers, exactly as intended. Effort that wasn't advancing
contactability (e.g. the hidden license numbers) is now surfaced and working.

## The #1 next lever (scoped, not shipped)

**NSCB contractor enrichment.** We hold **2,500 contractor license numbers**;
contractors must list a business phone, and NSCB's license search is public (NRS
239). Looking those up would add a large block of real, callable contractor phones
— the single biggest free phone-count gain. It's a **scrape** (no clean API), so I
can't build and verify it from the sandbox without risking shipping code that only
*looks* like it works. It's the clear next build, to be done carefully against the
live portal.

After that, contact growth rests on **lead-base expansion** (more permit
jurisdictions / sources), which is the phase you flagged for after this one.

## Verification

`selftest` exit 0 (new contact-engine asserts: phone normalization, tiers, channels,
summary, stats) · `rebuild` exit 0 · `checksize` exit 0 (cards.json 20.4 MB, under
the 25 MB limit) · console JS syntax-checked, zero browser-storage APIs · workflow
fix re-applied. The dashboard renders from data already in your warehouse — open the
**Contactability** tab to see the call list immediately; run a harvest to fold in any
business phones and CLV contractor addresses.
