# Apt Finder

A personal Bay Area apartment research analyst with receipts. It finds studio and one-bedroom
apartments advertised at **$2,100–$3,000/month base rent** between Foster City, San Jose, and Fremont,
scores them for commute, noise, management, pests, safety, and recurring issues, and lets you trace
every score back to the evidence and the original source.

The system is an **evidence-processing pipeline**, not a set of free-form LLM agents. Evidence is
collected once, normalized into a canonical store, and then evaluated many times by deterministic
evaluators. Every claim shown in the UI passes an evidence audit first. Phase 1 needs no API keys.

## Quick start

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
# Backend
cd backend
uv sync
uv run python -m aptfinder run          # fresh search: collect, filter, evaluate, audit (≈15–30 min)
uv run python -m aptfinder serve        # API on http://localhost:8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                             # UI on http://localhost:3000
```

Useful variants:

```bash
uv run python -m aptfinder run --cities Sunnyvale,Mountain\ View   # subset of cities
uv run python -m aptfinder run --sources apartment_list            # skip Redfin
uv run python -m aptfinder run --skip-collection                   # re-filter and re-evaluate stored evidence
```

You can also start a refresh from the UI ("Refresh data"), which calls `POST /api/runs`.

### Google ratings and reviews (strongly recommended)

Google Maps is the most complete review source for these properties. With a key, every listing that
passes the price, location, and eligibility filters is matched to its Google Maps place (by name,
address, and a ≤150 m location check), and the app stores the star rating, total review count, Google's
AI summary of all reviews ("Summarized with Gemini"), and up to 5 review texts. A Google average below
3.0 across 3+ reviews excludes the property like any other low rating.

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project and attach a
   billing account (required even for free-tier use).
2. Enable **Places API (New)**. Optionally enable **Routes API** to get rush-hour commute estimates.
3. Create an API key (APIs & Services → Credentials) and restrict it to those APIs.
4. Add it to `.env` at the repo root: `APTFINDER_GOOGLE_MAPS_API_KEY=your-key`
5. Run `uv run python -m aptfinder run --skip-collection` (or a full run).

Each property costs one Text Search and one Place Details request; Google data is refreshed at most
weekly (`APTFINDER_GOOGLE_REFRESH_DAYS`), which keeps typical use inside Google's monthly free usage.

Configuration lives in environment variables prefixed with `APTFINDER_` (or a `.env` file at the repo
root). See `backend/aptfinder/config.py`. Common ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `APTFINDER_MIN_RENT` / `APTFINDER_MAX_RENT` | 2100 / 3000 | Hard base-rent filter (inclusive) |
| `APTFINDER_PRICE_FRESHNESS_HOURS` | 72 | Prices older than this are never approved |
| `APTFINDER_GOOGLE_MAPS_API_KEY` | empty | Optional: enables Google Routes (rush-hour) and Google Places (ratings/reviews) |
| `APTFINDER_APARTMENT_LIST_MIN_INTERVAL_S` | 4.0 | Minimum seconds between requests to Apartment List |
| `APTFINDER_REDFIN_MIN_INTERVAL_S` | 8.0 | Minimum seconds between requests to Redfin |

## Architecture

```text
Listing discovery ─▶ raw evidence collection ─▶ normalization ─▶ deduplication ─▶ hard filters
   (collectors/)        (http.py raw store)      (normalize.py)    (dedupe.py)     (filters.py,
                                                                                   verification.py)
        ─▶ canonical evidence store ─▶ specialized evaluators ─▶ optional synthesis ─▶ evidence auditor
             (db/models.py, store.py)    (evaluators/)            (synthesis.py)       (audit.py)
        ─▶ programmatic overall score ─▶ API ─▶ web UI
             (scoring.py)                  (api/)   (frontend/)
```

| Path | Responsibility |
| --- | --- |
| `backend/aptfinder/http.py` | The only way the pipeline touches the web: robots.txt checks, per-host throttling with jitter, disk cache, raw-page storage, and an immediate stop for a host that returns 429, 403, a rate-limit redirect, or a challenge page |
| `backend/aptfinder/collectors/` | Source-specific parsing into normalized records (`types.py`). No scoring logic |
| `backend/aptfinder/store.py` | Persists listings, units, price and fee observations, reviews, and facts as evidence with deterministic IDs |
| `backend/aptfinder/dedupe.py` | Merges the same property across sources using address, ZIP, and coordinates — never names alone |
| `backend/aptfinder/filters.py`, `verification.py` | Hard filters: price, unit type, geography, freshness, low ratings; price-conflict detection |
| `backend/aptfinder/routing/`, `safety/`, `geocoding.py` | Commute, public-safety, and geocoding providers |
| `backend/aptfinder/evaluators/` | Deterministic category evaluators over shared review evidence |
| `backend/aptfinder/audit.py` | Evidence auditor; corrects or removes unsupported claims before storage |
| `backend/aptfinder/scoring.py` | Overall score from component scores only |
| `backend/aptfinder/api/` | FastAPI endpoints (contract in `docs/api-contract.md`) |
| `frontend/` | Next.js UI |

Collection, normalization, persistence, evaluation, audit, and presentation are separate modules;
collectors never score, and React components never fetch third-party sites.

## Data sources

| Source | Used for | Access notes |
| --- | --- | --- |
| [Apartment List](https://www.apartmentlist.com) | Listings, unit-level base and total prices, required monthly fees, fee text, specials, amenities, pet/parking/lease facts, official website links, verified resident reviews with sub-ratings | Public pages allowed by robots.txt; requests are throttled (≥4 s apart) and cached for 12 h |
| [Redfin Rentals](https://www.redfin.com) | Second listing source for cross-checking prices; unit-level base rent, sqft, availability | Public pages allowed by robots.txt (its APIs are disallowed and never called directly); ≥8 s between requests. In testing, Redfin began answering with an AWS WAF JavaScript challenge after a few dozen requests, so the collector stops at the first challenge and the run records the limitation. Expect little or no Redfin data until access recovers |
| [OSRM](https://project-osrm.org) public server | Driving distance and free-flow driving time to the office | ≤1 request/second policy; batched table requests, cached 7 days |
| [U.S. Census Geocoder](https://geocoding.geo.census.gov) | Address → coordinates when a listing lacks them, and the office location | Free, no key |
| [California DOJ OpenJustice](https://openjustice.doj.ca.gov) | City-level reported violent and property crime counts (annual) | Public CSV |
| [California Department of Finance E-1](https://dof.ca.gov/forecasting/demographics/estimates-e1/) | City populations for crime rates | Public spreadsheet |
| [Google Places API](https://developers.google.com/maps/documentation/places/web-service) | Star rating and total review count for each property, Google's AI summary of all reviews, up to 5 review texts (Google chooses them by relevance; the API offers no other ordering), Google Maps link | Requires `APTFINDER_GOOGLE_MAPS_API_KEY`. Google Search and Google Maps pages were tested with a browser and rejected: Search returns a CAPTCHA immediately and Maps hides reviews from signed-out sessions |
| Google Routes API (optional) | Traffic-aware rush-hour estimates | Same key, with Routes API enabled |

Sources that could not be used and why (checked October 2026): Apartments.com, Zillow, HotPads,
Trulia, Yelp, ApartmentRatings, RentCafe, Apartment Finder, and Niche returned HTTP 403 to plain
requests; Zumper and PadMapper serve a JavaScript anti-bot challenge; Rent.com and ApartmentGuide
disallow their listing paths in robots.txt or rate-limited immediately. The project does not bypass
CAPTCHAs, challenges, or access controls, so these sources are recorded as unavailable.

Several of the usable sites' terms of service restrict automated access. The owner of this project
reviewed that and chose to collect at a low, robots.txt-compliant rate for personal research only.

## Evidence model

```text
Property ──┬── ListingSource (one per site; never discarded on merge)
           ├── Unit ── PriceObservation (every observation kept, with collected_at and source_updated_at)
           ├── FeeObservation
           ├── Evidence (canonical record: review, listing_fact, price, fee, rating_summary,
           │             commute_fact, safety_fact) ── Review / RatingSummary / CommuteResult
           ├── CategoryAssessment ── Claim ── ClaimEvidence ──▶ Evidence ──▶ source URL
           ├── OverallScore
           └── AuditFinding
RawDocument: every fetched page, content-addressed and gzip-compressed under data/raw/
```

Every evidence record answers: what was observed (`content`, `data`), where it came from (`source_id`,
`source_url`, `source_page_url`), when it was published (`published_at`) and collected
(`first_collected_at`, `collected_at`), which property it refers to, which categories it can support,
and whether it is raw or derived (`is_derived`). Evidence IDs are deterministic hashes, so a refresh
updates records instead of duplicating them, and the raw page behind each record is retained.

## Pipeline details

**Hard filters** (a property must pass all of them to appear in the main results):

1. **Geography**: the city must be on the allowlist (Foster City through San Jose on the Peninsula
   and South Bay; Fremont, Newark, and Union City in the East Bay) *and* the coordinates must fall
   inside the search corridor. San Francisco, Oakland, Hayward, Burlingame and north, and Morgan Hill
   and south are rejected programmatically.
2. **Unit type and price**: at least one studio or one-bedroom whose *advertised base rent* is between
   $2,100 and $3,000 inclusive. A floor-plan price range qualifies only if one of its endpoints (each a
   real advertised price) is in range.
3. **Freshness**: the qualifying price must have been fetched within 72 hours, its source must have
   updated it within 21 days, and the unit must still appear in that source's latest fetch. Properties
   whose only in-range prices are stale are held as "needs re-verification" and never shown as
   verified.
4. **Eligibility**: senior (55+/62+) and income-restricted (affordable, BMR) housing is excluded, based on
   source flags (Apartment List occupancy types, Redfin senior/income-restricted flags) or an unambiguous
   property name. Student or military restrictions are shown as warnings rather than excluded.
5. **Review rating**: excluded only when a reliably matched source shows an average below 3.0/5 across
   at least 3 reviews. One review, no reviews, or a weakly matched source never excludes. When credible
   sources disagree by a star or more, the property is kept and flagged as conflicting.

Properties that fail a filter stay in the database with their reasons and are listed on the UI's
"Excluded properties" page, so nothing disappears silently.

**Price handling.** Base rent, the source's published total, required monthly fees, lease term,
availability date, promotions, and timestamps are stored per observation. The estimated monthly total
is base rent plus fees the source declares mandatory and recurring; required costs without a published
amount (for example, "renter's insurance required") and recurring fees whose mandatory status is
unclear are listed separately rather than guessed. Promotions are flagged; an effective rent is only
computed for unconditional offers with a known lease term and is labeled as derived, never as a quoted
price. When sources report non-overlapping prices for the same floor plan (same bedrooms, square
footage within 2%), the property is marked **price conflict** and both source links are shown.

**Commute.** Distance and free-flow driving time to 242 Humboldt Ct, Sunnyvale (Google Sunnyvale
Humboldt buildings) come from OSRM. They do not include traffic. Rush-hour fields read
"Unavailable — traffic-aware routing API required" unless a Google Maps key is configured.

**Safety.** Building safety comes only from resident reports. Neighborhood safety uses official
city-wide crime rates (CA DOJ counts ÷ CA DOF population) compared with the statewide rate; it is
always at most low confidence because it is not neighborhood-specific. Demographics, income, and
similar proxies are never used.

## Scoring methodology

Scores run 1–10 (10 is best). Review-based categories need at least 3 relevant reviews; otherwise they
show **N/A — insufficient evidence**. A lack of complaints is never treated as a positive signal.
Recent reviews weigh more (≤2 years: 1.0, 2–4 years: 0.6, 4–7 years: 0.3, older: 0.15); old evidence is
kept but labeled with its age.

A review-based score is `5.5 + 4.5 × net`, where `net` is the recency- and severity-weighted balance of
positive and negative mentions and resident sub-ratings. Two units of neutral weight are added to the
denominator, so three agreeing reviews produce 8.2 rather than a perfect 10; scores approach the extremes
only as evidence accumulates. Confidence is assigned separately from the number, recency, and source
diversity of the reviews.

| Category | Weight |
| --- | ---: |
| Commute | 25% |
| Noise | 20% |
| Management | 20% |
| Safety (building 7.5% + neighborhood 7.5%) | 15% |
| Pests | 10% |
| Other recurring issues | 10% |

Categories without sufficient evidence are excluded and the remaining weights are renormalized; the UI
lists what was excluded. Overall confidence combines how much weight is covered with each component's
confidence, and the reasons for any reduction are shown. No overall score is given when fewer than two
categories, or less than 30% of the weight, have evidence. The overall score is always computed in code
from the component scores.

## Source links

Source URLs are copied from the data that produced each record — never constructed or guessed. When a
review cannot be deep-linked, the closest page (the property's review section) is kept along with the
reviewer name, date, and rating. Records without any URL display "Source URL unavailable." The only
generated links are clearly labeled conveniences, such as "Check live traffic on Google Maps," which
open a documented Google Maps directions URL and are not presented as evidence.

## Known limitations

- **What a typical run looks like (October 3, 2026).** Apartment List surfaced 639 properties across the 18
  cities; 153 had a studio or one-bedroom at or below $3,150 and were fetched (161 requests, no rate
  limiting); 67 passed every hard filter. Only 10 review texts exist across those 67, so most properties are
  scored on commute and city-level safety alone, at low overall confidence — the UI says so on every card.
- **Google review texts are capped at 5 per property.** The rating and count cover every Google review,
  and Google's AI summary describes all of them, but category scores can only cite the 5 texts Google
  returns plus that summary. The summary is treated as derived evidence (it counts as one item, and it
  is always shown with Google's "Summarized with Gemini" label).
- **Thin review coverage.** Without API keys, the only reachable review source is Apartment List's
  verified reviews, which are sparse (often zero to a few per property, and some come from people who
  toured rather than lived there). Most noise, management, pest, and safety categories will honestly
  read N/A. Adding a Google Maps key enables Google ratings and up to 5 reviews per property.
- **No rush-hour data** without a traffic-aware routing key; commute scores use free-flow time.
- **City-level crime data** cannot distinguish neighborhoods within large cities such as San Jose.
- **Redfin is challenge-gated.** Its bot protection (AWS WAF) started challenging plain requests mid-run.
  Solving that challenge would mean circumventing anti-bot measures, so Redfin is effectively a
  best-effort source and cross-source price conflicts will be rare until another listing source is added.
- **Coverage** is limited to what Apartment List and Redfin list; major sites that block automated
  access are not searched.
- **Site changes.** Collectors parse embedded page data; a site redesign can break a collector. Runs
  record such failures as limitations instead of guessing.

## APIs that can be added later

- **Google Routes API**: traffic-aware AM/PM estimates (implemented, activated by key).
- **Google Places API**: ratings and review excerpts (implemented, activated by key).
- **Yelp Fusion**, **RentCast**, or licensed listing feeds: additional review and listing coverage
  through new collectors that emit the same normalized records.
- **City open-data portals** (for example, San Jose police calls for service) for finer-grained safety
  data.
- **An LLM classifier/synthesizer**: plug into `evaluators/classifier.py` (`SemanticClassifier`) and
  `synthesis.py` (`Synthesizer`). Outputs still pass through the evidence auditor.

## Future chatbot

The chatbot is not part of Phase 1, but the store is built for it: every claim links to evidence IDs,
every evidence record keeps its text, dates, and source URLs, and assessments store their theme counts.
A chatbot endpoint would retrieve relevant evidence for the question (by property, category, theme, and
date, plus full-text search over `evidence.content`), pass only those records to the model with
instructions to cite evidence IDs, then validate that every cited ID exists and belongs to the
properties in question before showing an answer with source links — the same audit discipline used for
scores.

## Development

```bash
cd backend && uv run pytest -q      # backend tests
cd frontend && npm run lint && npm run build
```
