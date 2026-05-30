# GRIT — Manifesto

*Ground-truth Real-estate Intelligence & Targeting for Southern Nevada.*
*Reset as of Alpha 0.109.*

## What GRIT is

GRIT is a definitive, self-updating warehouse of economic activity across
Southern Nevada (Clark County). It exists to turn public signals into acquisition
intelligence for a single operator by chaining one relationship end to end:

> **EVENT → ENTITY → MONEY**
>
> Something happens to a property (a permit, a sale, a code-enforcement case, a
> new business license). That event ties to an owner entity. That entity ties to
> capital — where it comes from, how much moves, and who controls it.

GRIT is not a CRM, not a list broker, and not a national platform. It is a
focused instrument for understanding who is doing what, where, with whose money,
in one metro.

## Geography is fixed

GRIT covers **Southern Nevada only** — Clark County and its jurisdictions (Las
Vegas, North Las Vegas, Henderson, Boulder City, Mesquite, and the unincorporated
townships). This is deliberate and permanent. Out-of-state **owner** data is
intelligence about *capital origin* — it is never a reason to expand the map
beyond Southern Nevada. An owner in California still plots on the Las Vegas
parcel they own.

## The doctrine (non-negotiable)

1. **No synthetic data, ever.** Empty is honest; fabricated is forbidden. GRIT
   never invents a coordinate, a valuation, an owner, or a count. A blank field
   is a measured gap, surfaced as such.
2. **Append-only warehouse.** Records are never deleted. When a parcel stops
   appearing in a harvest it is marked dormant, not removed. History is the
   product; growth is the feature.
3. **Transparent scoring.** Every score ships its `signals[]` — the exact
   reasons and point values that built it. There is no black box.
4. **Four location dimensions, never collapsed.** `property_city`,
   `permit_jurisdiction`, `owner_mailing`, and `owner_origin_market` are distinct
   facts. Conflating "where the property is" with "where the owner lives" is a
   bug, not a simplification.
5. **Date-first.** Recency is a first-class signal. Every lead carries a primary
   date, an age, and a temporal state; the console sorts freshest-first.
6. **Confidence is measured.** Every significant field carries a class
   (authoritative / derived / inferred / unknown), a source, and a resolution
   method. "How much can we trust this, and why" is a distribution, not a vibe.
7. **Free data first.** GRIT runs on zero paid infrastructure. Every signal it
   can get for free, it gets. Paid sources are documented honestly and chosen
   deliberately, never assumed.

## Coverage philosophy: breadth vs depth

Full coverage has two independent ceilings, and conflating them hides the truth:

- **Breadth** — how many of Clark County's ~900,000 parcels we hold. This is
  limited by *us* (a deliberate cap), not by data: the free county parcel layer
  carries address + owner + mailing + land-use for the whole valley. Breadth is
  free; the only real limit is that ~900k parcels cannot render as individual
  pins on a static site (past ~10–15k, that needs slim records or vector tiles).
- **Depth** — how complete each field is (value, square footage, beds, baths,
  year built, sale history). This is limited by *data access*: those fields are
  not in any free public API. Clark County sells them as the paid AOEXTRACT
  (ownership + value) and AORES (residential characteristics) bulk extracts.

GRIT's answer is to be **signal-driven**: capture every permit, sale, distress
event, and license across the metro, enrich the parcels behind them, and measure
coverage against the real universe — rather than trying to paint 900,000 dormant
pins. Depth on every parcel is available only by choosing to pay; that choice is
the operator's, made with the real cost in view, never made silently.

## What "done" looks like

A living system that, every day, knows more about Southern Nevada than it did
yesterday — every signal it can legally and freely obtain, captured, attributed,
scored, and preserved; every gap named with the reason it exists and the path to
close it. The Signal Acquisition Matrix is the scoreboard, and it is meant to
keep turning green.
