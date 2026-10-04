# Apartment Finder — web UI

The localhost web interface for the evidence-backed Bay Area apartment finder. It is a Next.js (App Router)
app that renders data from the FastAPI backend described in [`docs/api-contract.md`](../docs/api-contract.md).
Every score, claim, price, and fact links back to its evidence and original source.

## Requirements

- Node.js 20 or newer
- The backend API running on `http://localhost:8000` (see the project README)

## Run it

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

Production build:

```bash
npm run build
npm start          # http://localhost:3000
```

### Backend URL

The app talks to the backend in two ways:

- Server-rendered pages fetch `${BACKEND_URL}/api/...` directly (read at request time).
- Browser requests go to `/api/...`, which `next.config.ts` rewrites to `${BACKEND_URL}/api/...`. Rewrites are
  resolved when `next dev` starts or when `next build` runs, so set the variable for both build and start.

`BACKEND_URL` defaults to `http://localhost:8000`.

```bash
BACKEND_URL=http://localhost:9000 npm run dev
```

If the backend isn't reachable, pages show an error state asking you to start it.

## Routes

| Route | What it shows |
| ----- | ------------- |
| `/` | Browse: card grid with optional map, client-side filters and sorting, last run info, and a “Refresh data” button (`POST /api/runs`, then polls `/api/runs/latest`). |
| `/properties/[id]` | Detail research page: overview, original listing links, price conflicts, monthly cost breakdown, units, fees, commute, scorecard with evidence drill-down, overall score breakdown, review intelligence, ratings by source, listing facts, and data limitations. |
| `/excluded` | Properties removed by hard filters, with the reasons. |

## Display rules the UI enforces

- A `null` score is always shown as “N/A — insufficient evidence”; it is never treated as 0 and always sorts last.
- A `null` URL is shown as “Source URL unavailable”. The UI never builds URLs; it only links URLs from the API, and
  every external link opens in a new tab with `rel="noopener noreferrer"`.
- Missing evidence is never phrased positively, conflicts are always shown, and old evidence shows its age.
- Time-sensitive values show timestamps in Pacific time, e.g. “October 3, 2026 at 8:42 PM”.
- Effective/promotional rent is labeled “Derived — not a quoted price”.
- Every card shows the Google Maps rating and total Google review count (color-coded: red below 3.0, amber 3.0–3.9,
  green 4.0+), Google's own review summary with its disclosure label when Google provides one, and Apt Finder's
  keyword-based “What Google reviewers say” summary (`comments_summary`) with its method note. When Google data is unavailable, the card shows
  `google.explanation` instead — never “No reviews”. Uncertain matches are flagged “Matched by address/location —
  verify this is the right place”.
- The base-rent range filter (dual-handle slider in $50 steps plus clamped inputs) is bounded by `/api/meta`
  `search.min_rent`/`max_rent` and is unit-accurate: a property matches only if a value in `qualifying_rents` falls
  inside the range, never because its overall min–max range overlaps.
- The “Rating” sort and the minimum-rating filter use the Google rating when available and fall back to the other
  sources' average; a separate “Google rating” sort uses Google only.

## Project layout

```
src/
  app/                 routes (server components fetch data)
  components/
    browse/            browse page (filters, cards, map, run status)
    property/          detail page sections and evidence drill-down
    ui/                shared primitives (badges, links, timestamps, icons)
  lib/
    types.ts           TypeScript mirror of docs/api-contract.md
    api.ts             typed API client (the only place that calls fetch)
    browse.ts          filtering and null-last sorting
    format.ts          money, date, and unit formatting
    presentation.ts    labels, tones, and source-link rules
    evidence.ts        evidence index and theme helpers
```

## Dev-only mock API (synthetic data)

`dev/mock-api.mjs` serves **clearly synthetic fixtures** (“Sample Property A”, `example.com` URLs, a
“SYNTHETIC DEV DATA” marker in limitations) that follow the API contract. It exists only for working on the UI
while the real backend is unavailable. It is never used by `npm run dev`, `npm run build`, or `npm start`, and it
must never be pointed at by a real deployment.

```bash
npm run mock-api    # terminal 1: mock API on http://localhost:8010
npm run dev:mock    # terminal 2: Next.js dev server using the mock (http://localhost:3000)
```

The fixtures cover: no reviews, price conflicts, stale prices, promotions with effective-rent estimates, unknown
required fees, null coordinates, null source URLs, all-N/A scores, conflicting ratings, older evidence, eligibility
restrictions, an evidence ID that has to be fetched from `/api/evidence/{id}`, and Google review states (low and high
ratings, keyword comment summaries with and without Google's own summary, a Google AI summary used as evidence,
probable and weak matches, not configured, not checked, no match).
Sample Property A has qualifying rents of $2,650 and $2,950, so a $2,700–$2,900 base-rent range must exclude it.

Options: `MOCK_API_PORT` (default `8010`) and `MOCK_SCENARIO=empty` (no properties, to see the empty state).

## Checks

```bash
npm run lint
npm run build
```
