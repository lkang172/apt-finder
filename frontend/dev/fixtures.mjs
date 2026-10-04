// SYNTHETIC DEV DATA. Every name, review, price, and URL below is invented for UI development.
// URLs use the reserved example.com domain. Never load this from application code.

export const SYNTHETIC_MARKER = "SYNTHETIC DEV DATA — served by frontend/dev/mock-api.mjs, not real listings";

const SOURCES = {
  listings: { id: "example_listings", name: "Example Listings (synthetic)" },
  rentals: { id: "sample_rentals", name: "Sample Rentals (synthetic)" },
  official: { id: "official_site", name: "Official website (synthetic)" },
  reviews: { id: "example_reviews", name: "Example Reviews (synthetic)" },
  osrm: { id: "osrm", name: "OSRM routing (synthetic)" },
  crime: { id: "city_open_data", name: "Example City Open Data (synthetic)" },
};

const COLLECTED = "2026-10-03T18:30:00Z";
const STALE_COLLECTED = "2026-09-08T17:05:00Z";
const CATEGORIES = ["commute", "noise", "management", "pests", "building_safety", "neighborhood_safety", "other_issues"];
const LABELS = {
  commute: "Commute",
  noise: "Noise",
  management: "Management",
  pests: "Pests",
  building_safety: "Building safety",
  neighborhood_safety: "Neighborhood safety",
  other_issues: "Other issues",
};
const BASE_WEIGHTS = { commute: 0.25, noise: 0.2, management: 0.2, building_safety: 0.075, neighborhood_safety: 0.075, pests: 0.1, other_issues: 0.1 };

function ageLabel(iso) {
  const years = (Date.parse("2026-10-03T00:00:00Z") - Date.parse(iso)) / (365.25 * 24 * 3600 * 1000);
  if (years >= 2) return `${Math.floor(years)} years ago`;
  if (years >= 1) return "1 year ago";
  const months = Math.max(1, Math.round(years * 12));
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

function review(slug, n, { rating, date, text, categories = [], reviewer = `Resident ${n}`, deepLink = true }) {
  const page = `https://reviews.example.com/${slug}`;
  return {
    id: `ev-${slug}-r${n}`,
    kind: "review",
    source_id: SOURCES.reviews.id,
    source_name: SOURCES.reviews.name,
    title: "",
    content: `[Synthetic] ${text}`,
    published_at: date,
    collected_at: COLLECTED,
    source_url: deepLink ? `${page}#review-${n}` : null,
    source_page_url: page,
    is_derived: false,
    categories,
    rating,
    reviewer,
    age_label: ageLabel(date),
    data: {},
  };
}

function fact(slug, n, { title, content, source = SOURCES.listings, url, kind = "listing_fact", categories = [], derived = false }) {
  return {
    id: `ev-${slug}-f${n}`,
    kind,
    source_id: source.id,
    source_name: source.name,
    title,
    content,
    published_at: null,
    collected_at: COLLECTED,
    source_url: url === undefined ? `https://listings.example.com/${slug}` : url,
    source_page_url: null,
    is_derived: derived,
    categories,
    rating: null,
    reviewer: null,
    age_label: null,
    data: {},
  };
}

function claim(id, text, polarity, theme, evidence, isCurrent = true) {
  return { id, text, polarity, theme, is_current: isCurrent, evidence };
}

function assessment(category, score, confidence, summary, { themeCounts, claims = [], evidenceCount, audit = "passed", details = {} } = {}) {
  return {
    category,
    label: LABELS[category],
    score,
    confidence,
    evidence_count: evidenceCount ?? claims.reduce((sum, c) => sum + c.evidence.length, 0),
    summary,
    details: themeCounts ? { theme_counts: themeCounts, ...details } : details,
    claims,
    audit_status: audit,
  };
}

function insufficient(category, summary) {
  return assessment(category, null, "insufficient", summary ?? `Insufficient evidence to reliably evaluate ${LABELS[category].toLowerCase()}.`, {
    evidenceCount: 0,
  });
}

function overallFrom(assessments, confidence, reasons) {
  const scored = assessments.filter((a) => a.score !== null);
  const totalWeight = scored.reduce((sum, a) => sum + BASE_WEIGHTS[a.category], 0);
  const components = scored.map((a) => ({
    category: a.category,
    label: a.label,
    score: a.score,
    confidence: a.confidence,
    base_weight: BASE_WEIGHTS[a.category],
    effective_weight: Number((BASE_WEIGHTS[a.category] / totalWeight).toFixed(4)),
  }));
  const score = components.length >= 2 ? Number(components.reduce((s, c) => s + c.score * c.effective_weight, 0).toFixed(1)) : null;
  return {
    score,
    confidence: score === null ? "insufficient" : confidence,
    components: score === null ? [] : components,
    excluded_categories: assessments
      .filter((a) => a.score === null)
      .map((a) => ({ category: a.category, label: a.label, reason: "Insufficient evidence — excluded and remaining weights renormalized" })),
    confidence_reasons: reasons,
  };
}

function scoresFrom(assessments) {
  return Object.fromEntries(CATEGORIES.map((c) => {
    const a = assessments.find((x) => x.category === c);
    return [c, { score: a.score, confidence: a.confidence }];
  }));
}

function unit(id, source, fields) {
  return {
    id,
    source_id: source.id,
    source_name: source.name,
    label: null,
    floorplan_name: null,
    kind: "unit",
    beds: 1,
    baths: 1,
    sqft_min: null,
    sqft_max: null,
    base_rent_min: null,
    base_rent_max: null,
    total_monthly: null,
    required_fees_monthly: null,
    lease_term_months: 12,
    available_on: null,
    availability: null,
    is_promotional: false,
    promotion_text: null,
    effective_rent_estimate: null,
    effective_rent_method: null,
    collected_at: COLLECTED,
    source_updated_at: null,
    fresh: true,
    qualifies: true,
    source_url: null,
    ...fields,
  };
}

function fee(source, fields) {
  return {
    fee_type: "other",
    description: "",
    amount_monthly: null,
    amount_text: null,
    mandatory: null,
    recurring: null,
    source_id: source.id,
    source_name: source.name,
    source_url: null,
    evidence_id: null,
    ...fields,
  };
}

function commuteDetail(slug, brief, overrides = {}) {
  return {
    ...brief,
    provider: "OSRM (synthetic)",
    methodology:
      "Driving route from the property's geocoded address to the office using free-flow road speeds. No traffic data is included.",
    confidence: "high",
    computed_at: COLLECTED,
    source_url: `https://router.example.com/route/v1/driving/${slug}`,
    view_url: `https://maps.example.com/directions/${slug}`,
    live_traffic_url: `https://maps.example.com/live-traffic/${slug}`,
    evidence_id: `ev-${slug}-commute`,
    ...overrides,
  };
}

const RUSH_UNAVAILABLE = "Unavailable — traffic-aware routing API required";

function emptyIntel(confidence, summary) {
  return { praised: [], criticized: [], recent_trends: [], outliers: [], quality: { confidence, summary, details: {} }, reviews: [] };
}

function summaryOf(detail) {
  const keys = [
    "id", "name", "city", "region", "street_address", "lat", "lon", "image_url", "image_source_name", "unit_types",
    "rent_min", "rent_max", "est_monthly_total_min", "has_unknown_required_costs", "has_promotion", "sqft_min", "sqft_max",
    "price_status", "last_verified_at", "commute", "review", "overall", "scores", "strongest_positive", "strongest_concern",
    "eligibility_notes", "source_ids",
  ];
  return Object.fromEntries(keys.map((k) => [k, detail[k]]));
}

function propertyA(imageBase) {
  const slug = "sample-property-a";
  const r = [
    review(slug, 1, { rating: 3, date: "2026-08-14T00:00:00Z", text: "Walls are thin — I hear my neighbor's TV most evenings.", categories: ["noise"] }),
    review(slug, 2, { rating: 4, date: "2026-07-02T00:00:00Z", text: "Thin walls but maintenance fixed my sink within a day.", categories: ["noise", "management"] }),
    review(slug, 3, { rating: 5, date: "2026-06-20T00:00:00Z", text: "Office staff are responsive and friendly. Packages are handled well.", categories: ["management"] }),
    review(slug, 4, { rating: 3, date: "2026-05-11T00:00:00Z", text: "Street noise from the expressway is noticeable with windows open.", categories: ["noise"] }),
    review(slug, 5, { rating: 4, date: "2026-04-03T00:00:00Z", text: "Quiet at night on the courtyard side.", categories: ["noise"] }),
    review(slug, 6, { rating: 2, date: "2026-03-18T00:00:00Z", text: "Car was broken into in the open lot; gate was broken for weeks.", categories: ["building_safety"] }),
    review(slug, 7, { rating: 4, date: "2026-02-09T00:00:00Z", text: "Thin walls, footsteps from upstairs are loud.", categories: ["noise"] }),
    review(slug, 8, { rating: 5, date: "2025-12-01T00:00:00Z", text: "Maintenance requests are handled quickly through the portal.", categories: ["management"] }),
    review(slug, 9, { rating: 4, date: "2025-10-22T00:00:00Z", text: "Saw a few ants in the kitchen one summer; treated quickly.", categories: ["pests"] }),
    review(slug, 10, { rating: 3, date: "2025-06-15T00:00:00Z", text: "Nearby construction was loud during the day for months.", categories: ["noise", "other_issues"] }),
    review(slug, 11, { rating: 5, date: "2025-03-08T00:00:00Z", text: "Quiet neighbors and a well-kept courtyard.", categories: ["noise"] }),
    review(slug, 12, { rating: 4, date: "2021-09-30T00:00:00Z", text: "Parking is tight in the evenings; guest spots fill early.", categories: ["other_issues"], deepLink: false }),
  ];
  const facts = [
    fact(slug, 1, { title: "Parking", content: "Covered parking available for $95/month; one space per unit.", categories: ["other_issues"] }),
    fact(slug, 2, { title: "Pets", content: "Cats and dogs up to 50 lb allowed; $50/month pet rent.", source: SOURCES.official, url: "https://www.example.com/sample-property-a/pets" }),
    fact(slug, 3, { title: "Amenities", content: "Pool, fitness center, package lockers, in-unit washer/dryer in 1BR units." }),
    fact(slug, 4, { title: "Utilities", content: "Water, sewer, and trash billed back monthly at a flat $85.", source: SOURCES.official, url: "https://www.example.com/sample-property-a/fees" }),
    fact(slug, 5, { title: "Lease terms", content: "Lease terms from 6 to 15 months; promotional pricing requires 13 months.", source: SOURCES.official, url: "https://www.example.com/sample-property-a/specials" }),
  ];
  const crime = fact(slug, 6, {
    kind: "safety_fact",
    title: "Reported property crime (2025)",
    content: "Sunnyvale reported 21.4 property crimes per 1,000 residents in 2025 versus a 24.9 county reference.",
    source: SOURCES.crime,
    url: "https://data.example.com/crime/sunnyvale-2025",
    categories: ["neighborhood_safety"],
  });
  const commuteEv = fact(slug, 7, {
    kind: "commute_fact",
    title: "Routing result",
    content: "4.1 miles, 11 minutes free-flow driving to the office.",
    source: SOURCES.osrm,
    url: "https://router.example.com/route/v1/driving/sample-property-a",
    categories: ["commute"],
  });
  const assessments = [
    assessment("commute", 9.1, "high", "About 11 minutes and 4.1 miles to the office in free-flow conditions. Rush-hour time is unavailable.", {
      claims: [claim(101, "Free-flow drive is about 11 minutes (4.1 mi).", "positive", "drive_time", [commuteEv])],
    }),
    assessment("noise", 5.8, "medium", "Several recent reviewers report thin walls and street noise, while a smaller number describe the courtyard side as quiet.", {
      themeCounts: { thin_walls: 7, street_noise: 3, quiet: 2, construction: 1 },
      evidenceCount: 13,
      claims: [
        claim(102, "Recent reviews repeatedly mention thin walls between units.", "negative", "thin_walls", [r[0], r[1], r[6]]),
        claim(103, "Expressway noise is noticeable on the street-facing side.", "negative", "street_noise", [r[3]]),
        claim(104, "The courtyard side is described as quiet.", "positive", "quiet", [r[4], r[10]]),
        claim(105, "Nearby construction was loud in 2025.", "negative", "construction", [r[9]], false),
      ],
    }),
    assessment("management", 7.6, "high", "Recent reviews consistently describe responsive maintenance and staff.", {
      themeCounts: { responsive_maintenance: 3, helpful_staff: 2 },
      claims: [
        claim(106, "Maintenance requests are resolved quickly.", "positive", "responsive_maintenance", [r[1], r[7]]),
        claim(107, "Office staff are responsive and handle packages well.", "positive", "helpful_staff", [r[2]]),
      ],
    }),
    assessment("pests", 7.0, "low", "One reviewer mentions an isolated ant issue that was treated. Too little evidence for a confident assessment.", {
      themeCounts: { ants: 1 },
      claims: [claim(108, "Isolated ant sighting, treated quickly.", "neutral", "ants", [r[8]])],
    }),
    assessment("building_safety", 6.0, "low", "One recent report of a car break-in and a broken gate in the open lot.", {
      themeCounts: { car_break_ins: 1, broken_gate: 1 },
      audit: "corrected",
      claims: [claim(109, "A car break-in occurred while the lot gate was broken.", "negative", "car_break_ins", [r[5]])],
    }),
    assessment("neighborhood_safety", 7.4, "medium", "City-level property crime rate is below the county reference. This is city-wide data, not block-level.", {
      claims: [claim(110, "City property crime rate is below the county reference rate.", "positive", "crime_rate", [crime])],
      details: { jurisdiction: "Sunnyvale", data_year: 2025 },
    }),
    assessment("other_issues", 6.2, "medium", "Parking is reported as tight in the evenings; that report is several years old.", {
      themeCounts: { parking: 2, construction: 1 },
      claims: [claim(111, "Evening parking is tight; guest spots fill early.", "negative", "parking", [r[11]], false)],
    }),
  ];
  const detail = {
    id: 1,
    name: "Sample Property A",
    city: "Sunnyvale",
    region: "south_bay",
    street_address: "100 Example Way",
    zip: "94086",
    lat: 37.379,
    lon: -122.03,
    image_url: `${imageBase}/a.svg`,
    image_source_name: "Example Listings (synthetic)",
    unit_types: ["studio", "1br"],
    rent_min: 2650,
    rent_max: 2950,
    est_monthly_total_min: 2835,
    has_unknown_required_costs: false,
    has_promotion: true,
    sqft_min: 480,
    sqft_max: 690,
    price_status: "verified",
    last_verified_at: COLLECTED,
    commute: { distance_miles: 4.1, free_flow_minutes: 11, am_rush_minutes: null, pm_rush_minutes: null, rush_status: RUSH_UNAVAILABLE },
    review: { average: 3.8, count: 12, status: "ok", explanation: "12 reviews from 1 source" },
    strongest_positive: { text: "Fast, responsive maintenance", category: "management", claim_id: 106 },
    strongest_concern: { text: "Thin walls between units", category: "noise", claim_id: 102 },
    eligibility_notes: [],
    source_ids: [SOURCES.listings.id, SOURCES.official.id, SOURCES.reviews.id],
    listings: [
      { source_id: SOURCES.listings.id, source_name: SOURCES.listings.name, url: `https://listings.example.com/${slug}`, name: "Sample Property A Apartments", last_seen_at: COLLECTED },
    ],
    official_website: { url: "https://www.example.com/sample-property-a", source_id: SOURCES.official.id, source_name: SOURCES.official.name, evidence_id: null },
    units: [
      unit(11, SOURCES.official, { label: "214", floorplan_name: "S1", beds: 0, sqft_min: 480, sqft_max: 480, base_rent_min: 2650, base_rent_max: 2650, total_monthly: 2835, required_fees_monthly: 185, lease_term_months: 13, available_on: "2026-10-20", is_promotional: true, promotion_text: "6 weeks free on a 13-month lease", effective_rent_estimate: 2344, effective_rent_method: "Base rent × (13 − 1.5 months free) ÷ 13; ignores fees", source_url: "https://www.example.com/sample-property-a/units/214" }),
      unit(12, SOURCES.listings, { label: "318", floorplan_name: "A2", beds: 1, sqft_min: 690, sqft_max: 690, base_rent_min: 2950, base_rent_max: 2950, total_monthly: null, required_fees_monthly: null, lease_term_months: 12, availability: "Available now", source_url: `https://listings.example.com/${slug}/318` }),
      unit(13, SOURCES.listings, { floorplan_name: "B1", kind: "floorplan", beds: 2, baths: 2, sqft_min: 980, sqft_max: 1010, base_rent_min: 3650, base_rent_max: 3900, qualifies: false, source_url: `https://listings.example.com/${slug}/b1` }),
    ],
    fees: [
      fee(SOURCES.official, { fee_type: "utilities", description: "Water, sewer, trash flat fee", amount_monthly: 85, mandatory: true, recurring: true, source_url: "https://www.example.com/sample-property-a/fees" }),
      fee(SOURCES.official, { fee_type: "amenity", description: "Amenity and package locker fee", amount_monthly: 100, mandatory: true, recurring: true, source_url: "https://www.example.com/sample-property-a/fees" }),
      fee(SOURCES.listings, { fee_type: "parking", description: "Covered parking space", amount_monthly: 95, mandatory: false, recurring: true, source_url: `https://listings.example.com/${slug}` }),
      fee(SOURCES.official, { fee_type: "deposit", description: "Security deposit", amount_text: "$500–$1,000 one-time", mandatory: true, recurring: false, source_url: "https://www.example.com/sample-property-a/fees" }),
    ],
    monthly_cost: { base_rent_min: 2650, confirmed_required_fees: 185, est_total_min: 2835, unknown_required: [], unclear_recurring: [] },
    price_conflicts: [],
    promotions: [{ text: "6 weeks free on select studios with a 13-month lease", source_id: SOURCES.official.id, source_name: SOURCES.official.name, url: "https://www.example.com/sample-property-a/specials" }],
    commute_detail: commuteDetail(slug, { distance_miles: 4.1, free_flow_minutes: 11, am_rush_minutes: null, pm_rush_minutes: null, rush_status: RUSH_UNAVAILABLE }),
    assessments,
    overall_detail: overallFrom(assessments, "medium", [
      "Pests and building safety rest on a single review each (low confidence).",
      "All reviews come from a single source.",
    ]),
    review_intelligence: {
      praised: [
        { theme: "responsive_maintenance", label: "Responsive maintenance", count: 3, recent_count: 2, evidence_ids: [r[1].id, r[7].id, r[2].id] },
        { theme: "quiet", label: "Quiet courtyard side", count: 2, recent_count: 1, evidence_ids: [r[4].id, r[10].id] },
      ],
      criticized: [
        { theme: "thin_walls", label: "Thin walls", count: 7, recent_count: 3, evidence_ids: [r[0].id, r[1].id, r[6].id] },
        { theme: "street_noise", label: "Street noise", count: 3, recent_count: 1, evidence_ids: [r[3].id] },
        { theme: "parking", label: "Parking", count: 2, recent_count: 0, evidence_ids: [r[11].id, "ev-sample-property-a-r99"] },
      ],
      recent_trends: ["Thin-wall complaints continue through 2026.", "Maintenance praise is consistent across 2025–2026."],
      outliers: [{ text: "A single report of a car break-in while the lot gate was broken.", evidence_id: r[5].id }],
      quality: {
        confidence: "medium",
        summary: "12 reviews, 9 from the last 12 months, all from one source. Themes are corroborated by multiple reviewers.",
        details: { total_reviews: 12, recent_reviews: 9, sources: 1, oldest_review_year: 2021 },
      },
      reviews: r,
    },
    rating_summaries: [{ source_id: SOURCES.reviews.id, source_name: SOURCES.reviews.name, average: 3.8, count: 12, source_url: `https://reviews.example.com/${slug}`, observed_at: COLLECTED }],
    rating_filter: { status: "ok", explanation: "3.8/5 across 12 reviews — above the 3.0 exclusion threshold." },
    facts: [...facts, crime],
    audit: [
      { category: "building_safety", check_name: "single_source_confidence", severity: "warning", action: "Confidence lowered from medium to low", detail: "The building-safety assessment relied on one review." },
      { category: null, check_name: "evidence_ids_exist", severity: "info", action: "None", detail: "All referenced evidence IDs exist." },
    ],
    limitations: [SYNTHETIC_MARKER, "Rush-hour commute requires a traffic-aware routing API, which is not configured."],
  };
  detail.scores = scoresFrom(assessments);
  detail.overall = { score: detail.overall_detail.score, confidence: detail.overall_detail.confidence };
  return detail;
}

function propertyB() {
  const slug = "sample-property-b";
  const crime = fact(slug, 1, {
    kind: "safety_fact",
    title: "Reported property crime (2025)",
    content: "Mountain View reported 23.0 property crimes per 1,000 residents in 2025 versus a 24.9 county reference.",
    source: SOURCES.crime,
    url: "https://data.example.com/crime/mountain-view-2025",
    categories: ["neighborhood_safety"],
  });
  const assessments = [
    assessment("commute", 8.4, "high", "About 14 minutes and 6.3 miles in free-flow conditions. Rush-hour time is unavailable.", {
      claims: [claim(201, "Free-flow drive is about 14 minutes (6.3 mi).", "positive", "drive_time", [fact(slug, 2, { kind: "commute_fact", title: "Routing result", content: "6.3 miles, 14 minutes free-flow.", source: SOURCES.osrm, url: null })])],
    }),
    insufficient("noise", "No reviews found — noise can't be assessed."),
    insufficient("management", "No reviews found — management can't be assessed."),
    insufficient("pests", "Pest-related evidence is insufficient to make a reliable assessment."),
    insufficient("building_safety"),
    assessment("neighborhood_safety", 7.0, "medium", "City-level property crime rate is slightly below the county reference.", {
      claims: [claim(202, "City property crime rate is slightly below the county reference.", "positive", "crime_rate", [crime])],
    }),
    insufficient("other_issues"),
  ];
  const detail = {
    id: 2,
    name: "Sample Property B",
    city: "Mountain View",
    region: "peninsula",
    street_address: "250 Placeholder Ave",
    zip: "94041",
    lat: 37.392,
    lon: -122.079,
    image_url: null,
    image_source_name: null,
    unit_types: ["1br"],
    rent_min: 2795,
    rent_max: 2950,
    est_monthly_total_min: 2795,
    has_unknown_required_costs: true,
    has_promotion: false,
    sqft_min: 610,
    sqft_max: 640,
    price_status: "conflict",
    last_verified_at: "2026-10-03T17:50:00Z",
    commute: { distance_miles: 6.3, free_flow_minutes: 14, am_rush_minutes: null, pm_rush_minutes: null, rush_status: RUSH_UNAVAILABLE },
    review: { average: null, count: 0, status: "no_reviews", explanation: "No reviews found" },
    strongest_positive: { text: "Short commute (about 14 min, no traffic)", category: "commute", claim_id: 201 },
    strongest_concern: null,
    eligibility_notes: [],
    source_ids: [SOURCES.listings.id, SOURCES.rentals.id, SOURCES.official.id],
    listings: [
      { source_id: SOURCES.listings.id, source_name: SOURCES.listings.name, url: `https://listings.example.com/${slug}`, name: "Sample Property B", last_seen_at: "2026-10-03T17:50:00Z" },
      { source_id: SOURCES.rentals.id, source_name: SOURCES.rentals.name, url: null, name: "Sample Property B (1BR)", last_seen_at: "2026-10-02T09:12:00Z" },
    ],
    official_website: { url: "https://www.example.com/sample-property-b", source_id: SOURCES.official.id, source_name: SOURCES.official.name, evidence_id: null },
    units: [
      unit(21, SOURCES.listings, { floorplan_name: "Plan A", kind: "floorplan", sqft_min: 610, sqft_max: 640, base_rent_min: 2795, base_rent_max: 2795, source_url: `https://listings.example.com/${slug}` }),
      unit(22, SOURCES.official, { floorplan_name: "Plan A", kind: "floorplan", sqft_min: 610, sqft_max: 640, base_rent_min: 2950, base_rent_max: 2950, source_url: "https://www.example.com/sample-property-b/floorplans" }),
      unit(23, SOURCES.rentals, { floorplan_name: "Plan A", kind: "floorplan", sqft_min: 610, sqft_max: 640, base_rent_min: 2850, base_rent_max: 2850, source_url: null, fresh: false, qualifies: false, collected_at: "2026-09-01T10:00:00Z" }),
    ],
    fees: [
      fee(SOURCES.official, { fee_type: "insurance", description: "Renter's insurance required", amount_text: "Amount not published", mandatory: true, recurring: true, source_url: "https://www.example.com/sample-property-b/faq" }),
      fee(SOURCES.listings, { fee_type: "other", description: "Package locker service", amount_monthly: 15, mandatory: null, recurring: true, source_url: null }),
    ],
    monthly_cost: { base_rent_min: 2795, confirmed_required_fees: 0, est_total_min: 2795, unknown_required: ["Renter's insurance (required, amount not published)"], unclear_recurring: ["Package locker service — $15/mo"] },
    price_conflicts: [
      {
        beds: 1,
        sqft: 610,
        difference: 155,
        sides: [
          { source_id: SOURCES.listings.id, source_name: SOURCES.listings.name, price_min: 2795, price_max: 2795, label: "Plan A", url: `https://listings.example.com/${slug}` },
          { source_id: SOURCES.official.id, source_name: SOURCES.official.name, price_min: 2950, price_max: 2950, label: "Plan A", url: "https://www.example.com/sample-property-b/floorplans" },
        ],
      },
    ],
    promotions: [],
    commute_detail: commuteDetail(slug, { distance_miles: 6.3, free_flow_minutes: 14, am_rush_minutes: null, pm_rush_minutes: null, rush_status: RUSH_UNAVAILABLE }, { source_url: null, live_traffic_url: null }),
    assessments,
    overall_detail: overallFrom(assessments, "low", [
      "No reviews found: noise, management, and pests could not be scored.",
      "Only 2 of 7 categories had enough evidence.",
    ]),
    review_intelligence: emptyIntel("insufficient", "No reviews were found on any source we checked."),
    rating_summaries: [],
    rating_filter: { status: "no_reviews", explanation: "No reviews found, so the low-rating filter does not apply." },
    facts: [
      fact(slug, 3, { title: "Parking", content: "One assigned uncovered space included.", url: null }),
      fact(slug, 4, { title: "Pets", content: "Cats allowed; dogs not allowed.", source: SOURCES.official, url: "https://www.example.com/sample-property-b/faq" }),
      crime,
    ],
    audit: [],
    limitations: [SYNTHETIC_MARKER, "Sample Rentals listing URL could not be retained.", "No reviews found on any checked source."],
  };
  detail.scores = scoresFrom(assessments);
  detail.overall = { score: detail.overall_detail.score, confidence: detail.overall_detail.confidence };
  return detail;
}

function propertyC() {
  const slug = "sample-property-c";
  const onlyReview = review(slug, 1, { rating: 2.7, date: "2025-11-12T00:00:00Z", text: "Leasing office was slow to respond.", categories: ["management"] });
  const assessments = CATEGORIES.map((c) => insufficient(c));
  const detail = {
    id: 3,
    name: "Sample Property C",
    city: "San Jose",
    region: "south_bay",
    street_address: null,
    zip: null,
    lat: null,
    lon: null,
    image_url: "https://images.example.com/sample-property-c/missing-photo.jpg",
    image_source_name: "Sample Rentals (synthetic)",
    unit_types: ["studio"],
    rent_min: 2550,
    rent_max: 2550,
    est_monthly_total_min: null,
    has_unknown_required_costs: false,
    has_promotion: false,
    sqft_min: null,
    sqft_max: null,
    price_status: "stale",
    last_verified_at: STALE_COLLECTED,
    commute: null,
    review: { average: 2.7, count: 1, status: "insufficient", explanation: "Only 1 review — not enough to rate reliably" },
    strongest_positive: null,
    strongest_concern: null,
    eligibility_notes: [],
    source_ids: [SOURCES.rentals.id],
    listings: [{ source_id: SOURCES.rentals.id, source_name: SOURCES.rentals.name, url: `https://rentals.example.com/${slug}`, name: null, last_seen_at: STALE_COLLECTED }],
    official_website: null,
    units: [unit(31, SOURCES.rentals, { beds: 0, base_rent_min: 2550, base_rent_max: 2550, lease_term_months: null, collected_at: STALE_COLLECTED, fresh: false, qualifies: false, source_url: `https://rentals.example.com/${slug}` })],
    fees: [],
    monthly_cost: { base_rent_min: 2550, confirmed_required_fees: null, est_total_min: null, unknown_required: [], unclear_recurring: [] },
    price_conflicts: [],
    promotions: [],
    commute_detail: null,
    assessments,
    overall_detail: overallFrom(assessments, "insufficient", ["No category had enough evidence to score."]),
    review_intelligence: { ...emptyIntel("insufficient", "Only one review was found; no themes can be established."), reviews: [onlyReview] },
    rating_summaries: [{ source_id: SOURCES.rentals.id, source_name: SOURCES.rentals.name, average: 2.7, count: 1, source_url: null, observed_at: STALE_COLLECTED }],
    rating_filter: { status: "insufficient", explanation: "2.7/5 from a single review — below 3 credible reviews, so the property is not excluded." },
    facts: [],
    audit: [{ category: null, check_name: "price_freshness", severity: "warning", action: "Marked price as stale", detail: "Latest price observation is 25 days old." }],
    limitations: [SYNTHETIC_MARKER, "Street address and coordinates could not be verified; commute was not computed.", "Pricing is stale."],
  };
  detail.scores = scoresFrom(assessments);
  detail.overall = { score: detail.overall_detail.score, confidence: detail.overall_detail.confidence };
  return detail;
}

function propertyD(imageBase) {
  const slug = "sample-property-d";
  const r = [
    review(slug, 1, { rating: 2, date: "2019-05-04T00:00:00Z", text: "Management ignored repair requests for weeks.", categories: ["management"], deepLink: false }),
    review(slug, 2, { rating: 1, date: "2018-11-20T00:00:00Z", text: "Deposit dispute with the old management company.", categories: ["management"], deepLink: false }),
    review(slug, 3, { rating: 5, date: "2026-09-02T00:00:00Z", text: "New management since 2024 has been great — quick repairs.", categories: ["management"], deepLink: false }),
    review(slug, 4, { rating: 4, date: "2026-06-17T00:00:00Z", text: "Caltrain horn is audible at night from the east side.", categories: ["noise"], deepLink: false }),
    review(slug, 5, { rating: 4, date: "2026-01-29T00:00:00Z", text: "Saw a mouse in the garage twice this winter.", categories: ["pests"], deepLink: false }),
  ];
  const assessments = [
    assessment("commute", 6.8, "high", "About 18 minutes free-flow; 24–31 minutes at weekday rush hour.", {
      claims: [claim(401, "Rush-hour drive is 24–31 minutes.", "neutral", "drive_time", [fact(slug, 1, { kind: "commute_fact", title: "Traffic-aware routing", content: "AM rush 24 min, PM rush 31 min (typical weekday).", source: { id: "traffic_api", name: "Example Traffic API (synthetic)" }, url: "https://traffic.example.com/route/sample-property-d" })])],
    }),
    assessment("noise", 6.5, "low", "One recent reviewer mentions Caltrain horn noise at night.", {
      themeCounts: { train_noise: 1 },
      claims: [claim(402, "Caltrain horn is audible at night on the east side.", "negative", "train_noise", [r[3]])],
    }),
    assessment("management", 6.9, "medium", "Older reviews (2018–2019) are negative; recent reviews under new management are positive.", {
      themeCounts: { slow_repairs: 1, deposit_disputes: 1, responsive_maintenance: 1 },
      details: { management_change_year: 2024 },
      claims: [
        claim(403, "Recent reviews praise the new management's repair speed.", "positive", "responsive_maintenance", [r[2]]),
        claim(404, "Repair requests were ignored under previous management.", "negative", "slow_repairs", [r[0]], false),
        claim(405, "Deposit dispute with the previous management company.", "negative", "deposit_disputes", [r[1]], false),
      ],
    }),
    assessment("pests", 5.5, "low", "One recent report of mice in the garage.", {
      themeCounts: { rodents: 1 },
      claims: [claim(406, "Mice seen in the garage this winter.", "negative", "rodents", [r[4]])],
    }),
    insufficient("building_safety"),
    insufficient("neighborhood_safety", "No recent public safety data could be retrieved for Redwood City."),
    insufficient("other_issues"),
  ];
  const detail = {
    id: 4,
    name: "Sample Property D",
    city: "Redwood City",
    region: "peninsula",
    street_address: "77 Fixture Blvd",
    zip: "94063",
    lat: 37.486,
    lon: -122.228,
    image_url: `${imageBase}/d.svg`,
    image_source_name: "Official website (synthetic)",
    unit_types: ["studio"],
    rent_min: 2595,
    rent_max: 2695,
    est_monthly_total_min: 2720,
    has_unknown_required_costs: false,
    has_promotion: true,
    sqft_min: 455,
    sqft_max: 470,
    price_status: "verified",
    last_verified_at: "2026-10-03T16:20:00Z",
    commute: { distance_miles: 12.8, free_flow_minutes: 18, am_rush_minutes: 24, pm_rush_minutes: 31, rush_status: "Available — traffic-aware routing (synthetic)" },
    review: { average: 3.1, count: 55, status: "conflict", explanation: "Ratings disagree across sources (2.6 vs 4.2)" },
    strongest_positive: { text: "Recent reviews praise new management", category: "management", claim_id: 403 },
    strongest_concern: { text: "Caltrain horn audible at night", category: "noise", claim_id: 402 },
    eligibility_notes: [],
    source_ids: [SOURCES.official.id, SOURCES.reviews.id, SOURCES.rentals.id],
    listings: [{ source_id: SOURCES.rentals.id, source_name: SOURCES.rentals.name, url: `https://rentals.example.com/${slug}`, name: "Sample Property D Studios", last_seen_at: "2026-10-03T16:20:00Z" }],
    official_website: { url: "https://www.example.com/sample-property-d", source_id: SOURCES.official.id, source_name: SOURCES.official.name, evidence_id: null },
    units: [
      unit(41, SOURCES.official, { label: "105", beds: 0, sqft_min: 455, sqft_max: 455, base_rent_min: 2595, base_rent_max: 2595, total_monthly: 2720, required_fees_monthly: 125, lease_term_months: 12, available_on: "2026-11-01", is_promotional: true, promotion_text: "$500 off first month", effective_rent_estimate: 2553, effective_rent_method: "Base rent − ($500 ÷ 12 months)", source_url: "https://www.example.com/sample-property-d/units/105" }),
      unit(42, SOURCES.rentals, { label: "209", beds: 0, sqft_min: 470, sqft_max: 470, base_rent_min: 2695, base_rent_max: 2695, lease_term_months: 12, availability: "Available Nov 15", source_updated_at: "2026-10-01T12:00:00Z", source_url: `https://rentals.example.com/${slug}/209` }),
    ],
    fees: [fee(SOURCES.official, { fee_type: "trash", description: "Trash and recycling", amount_monthly: 45, mandatory: true, recurring: true, source_url: "https://www.example.com/sample-property-d/fees" }), fee(SOURCES.official, { fee_type: "internet", description: "Bulk internet package", amount_monthly: 80, mandatory: true, recurring: true, source_url: "https://www.example.com/sample-property-d/fees" })],
    monthly_cost: { base_rent_min: 2595, confirmed_required_fees: 125, est_total_min: 2720, unknown_required: [], unclear_recurring: [] },
    price_conflicts: [],
    promotions: [{ text: "$500 off the first month on select studios", source_id: SOURCES.official.id, source_name: SOURCES.official.name, url: null }],
    commute_detail: commuteDetail(slug, { distance_miles: 12.8, free_flow_minutes: 18, am_rush_minutes: 24, pm_rush_minutes: 31, rush_status: "Available — traffic-aware routing (synthetic)" }, { provider: "Example Traffic API (synthetic)", methodology: "Typical weekday departures at 8:30 AM and 5:30 PM using historical traffic." }),
    assessments,
    overall_detail: overallFrom(assessments, "low", ["Review sources disagree substantially (2.6/5 vs 4.2/5).", "Management changed in 2024; most negative reviews predate the change.", "Noise and pests rest on one review each."]),
    review_intelligence: {
      praised: [{ theme: "responsive_maintenance", label: "Responsive maintenance", count: 1, recent_count: 1, evidence_ids: [r[2].id] }],
      criticized: [
        { theme: "slow_repairs", label: "Slow repairs (previous management)", count: 1, recent_count: 0, evidence_ids: [r[0].id] },
        { theme: "train_noise", label: "Caltrain noise", count: 1, recent_count: 1, evidence_ids: [r[3].id] },
      ],
      recent_trends: ["Reviews since the 2024 management change are mostly positive."],
      outliers: [],
      quality: { confidence: "low", summary: "Only 5 review texts collected; summary ratings conflict across sources.", details: { total_reviews: 5, recent_reviews: 3 } },
      reviews: [...r].sort((a, b) => b.published_at.localeCompare(a.published_at)),
    },
    rating_summaries: [
      { source_id: SOURCES.reviews.id, source_name: SOURCES.reviews.name, average: 2.6, count: 40, source_url: `https://reviews.example.com/${slug}`, observed_at: "2026-10-03T16:20:00Z" },
      { source_id: SOURCES.rentals.id, source_name: SOURCES.rentals.name, average: 4.2, count: 15, source_url: `https://rentals.example.com/${slug}/reviews`, observed_at: "2026-10-03T16:20:00Z" },
    ],
    rating_filter: { status: "conflict", explanation: "Example Reviews shows 2.6/5 (40 reviews) while Sample Rentals shows 4.2/5 (15 reviews). Not excluded: the low rating is not reliably established." },
    facts: [fact(slug, 2, { title: "Parking", content: "Garage parking included with one space.", source: SOURCES.official, url: "https://www.example.com/sample-property-d/amenities" })],
    audit: [{ category: "management", check_name: "old_evidence_qualified", severity: "info", action: "Marked 2 claims as older evidence", detail: "Claims based on 2018–2019 reviews were flagged as not current." }],
    limitations: [SYNTHETIC_MARKER, "Individual review deep links are unavailable for Example Reviews; links open the property's review page."],
  };
  detail.scores = scoresFrom(assessments);
  detail.overall = { score: detail.overall_detail.score, confidence: detail.overall_detail.confidence };
  return detail;
}

function simpleProperty({ id, name, city, region, lat, lon, image, rent, total, sqft, commute, scores, review: reviewBrief, unknownCosts = false, eligibility = [] }) {
  const slug = name.toLowerCase().replace(/\s+/g, "-");
  const assessments = CATEGORIES.map((c) =>
    scores[c] === null || scores[c] === undefined
      ? insufficient(c)
      : assessment(c, scores[c][0], scores[c][1], `Synthetic ${LABELS[c].toLowerCase()} summary for layout testing.`, {
          evidenceCount: 4,
        }),
  );
  const detail = {
    id,
    name,
    city,
    region,
    street_address: `${id}00 Sample St`,
    zip: null,
    lat,
    lon,
    image_url: image,
    image_source_name: image ? "Example Listings (synthetic)" : null,
    unit_types: ["1br"],
    rent_min: rent[0],
    rent_max: rent[1],
    est_monthly_total_min: total,
    has_unknown_required_costs: unknownCosts,
    has_promotion: false,
    sqft_min: sqft?.[0] ?? null,
    sqft_max: sqft?.[1] ?? null,
    price_status: "verified",
    last_verified_at: COLLECTED,
    commute,
    review: reviewBrief,
    strongest_positive: null,
    strongest_concern: null,
    eligibility_notes: eligibility,
    source_ids: [SOURCES.listings.id],
    listings: [{ source_id: SOURCES.listings.id, source_name: SOURCES.listings.name, url: `https://listings.example.com/${slug}`, name, last_seen_at: COLLECTED }],
    official_website: null,
    units: [unit(id * 10 + 1, SOURCES.listings, { base_rent_min: rent[0], base_rent_max: rent[1], sqft_min: sqft?.[0] ?? null, sqft_max: sqft?.[1] ?? null, source_url: `https://listings.example.com/${slug}` })],
    fees: [],
    monthly_cost: { base_rent_min: rent[0], confirmed_required_fees: total === null ? null : total - rent[0], est_total_min: total, unknown_required: unknownCosts ? ["Utilities billed separately (amount not published)"] : [], unclear_recurring: [] },
    price_conflicts: [],
    promotions: [],
    commute_detail: commute ? commuteDetail(slug, commute) : null,
    assessments,
    overall_detail: overallFrom(assessments, "medium", []),
    review_intelligence: emptyIntel(reviewBrief.status === "ok" ? "medium" : "insufficient", "Synthetic review-quality summary."),
    rating_summaries: [],
    rating_filter: { status: reviewBrief.status, explanation: "Synthetic rating-filter explanation." },
    facts: [],
    audit: [],
    limitations: [SYNTHETIC_MARKER],
  };
  detail.scores = scoresFrom(assessments);
  detail.overall = { score: detail.overall_detail.score, confidence: detail.overall_detail.confidence };
  return detail;
}

export function buildFixtures(imageBase) {
  const details = [
    propertyA(imageBase),
    propertyB(),
    propertyC(),
    propertyD(imageBase),
    simpleProperty({
      id: 5,
      name: "Sample Property E",
      city: "Fremont",
      region: "east_bay",
      lat: 37.548,
      lon: -121.988,
      image: `${imageBase}/e.svg`,
      rent: [2700, 2700],
      total: 2700,
      sqft: [700, 700],
      unknownCosts: true,
      eligibility: ["Income-restricted housing"],
      commute: { distance_miles: 14.5, free_flow_minutes: 22, am_rush_minutes: null, pm_rush_minutes: null, rush_status: RUSH_UNAVAILABLE },
      scores: { commute: [6.1, "high"], noise: [7.2, "medium"], management: [6.4, "medium"], pests: null, building_safety: [7.0, "low"], neighborhood_safety: [6.8, "medium"], other_issues: [7.1, "low"] },
      review: { average: 3.9, count: 24, status: "ok", explanation: "24 reviews from 2 sources" },
    }),
    simpleProperty({
      id: 6,
      name: "Sample Property F",
      city: "Santa Clara",
      region: "south_bay",
      lat: 37.354,
      lon: -121.955,
      image: `${imageBase}/f.svg`,
      rent: [2890, 2990],
      total: 3140,
      sqft: null,
      commute: { distance_miles: 7.9, free_flow_minutes: 15, am_rush_minutes: null, pm_rush_minutes: null, rush_status: RUSH_UNAVAILABLE },
      scores: { commute: [8.2, "high"], noise: [8.6, "high"], management: [8.9, "high"], pests: [8.0, "medium"], building_safety: [8.3, "medium"], neighborhood_safety: [7.9, "medium"], other_issues: [8.1, "medium"] },
      review: { average: 4.5, count: 88, status: "ok", explanation: "88 reviews from 2 sources" },
    }),
    simpleProperty({
      id: 7,
      name: "Sample Property G",
      city: "Campbell",
      region: "south_bay",
      lat: 37.287,
      lon: -121.95,
      image: null,
      rent: [2525, 2600],
      total: 2600,
      sqft: [540, 560],
      eligibility: ["Senior Housing"],
      commute: { distance_miles: 11.2, free_flow_minutes: 19, am_rush_minutes: null, pm_rush_minutes: null, rush_status: RUSH_UNAVAILABLE },
      scores: { commute: [7.0, "high"], noise: null, management: null, pests: null, building_safety: null, neighborhood_safety: [7.2, "medium"], other_issues: null },
      review: { average: null, count: 0, status: "no_reviews", explanation: "No reviews found" },
    }),
  ];

  const lastRun = {
    id: 7,
    started_at: "2026-10-03T18:00:00Z",
    finished_at: "2026-10-03T18:42:00Z",
    status: "completed_with_limitations",
    stats: { properties_discovered: 31, properties_included: details.length, properties_excluded: 3, reviews_collected: 129 },
    limitations: [
      { source_id: "dev_mock", message: SYNTHETIC_MARKER },
      { source_id: SOURCES.rentals.id, message: "Rate limited after 40 requests; remaining pages skipped." },
    ],
  };

  const excluded = [
    { id: 90, name: "Sample Excluded Property X", city: "Palo Alto", reasons: [{ filter: "price_range", explanation: "Lowest studio/1BR base rent is $3,450 — above the $3,000 limit." }] },
    { id: 91, name: "Sample Excluded Property Y", city: "Campbell", reasons: [{ filter: "low_review_rating", explanation: "2.4/5 across 87 reviews — reliably below 3.0." }] },
    { id: 92, name: "Sample Excluded Property Z", city: null, reasons: [{ filter: "geography", explanation: "Located north of Foster City." }, { filter: "unit_type", explanation: "Only 2BR+ units were listed." }] },
  ];

  const meta = {
    office: { label: "Google Sunnyvale — Humboldt buildings", address: "Synthetic office address for development", lat: 37.4038, lon: -122.0326 },
    search: { min_rent: 2500, max_rent: 3000, unit_types: ["studio", "1br"] },
    sources: Object.values(SOURCES).map((s) => ({ id: s.id, name: s.name, kind: "synthetic", homepage_url: null })),
  };

  const evidence = new Map();
  for (const detail of details) {
    for (const item of [...detail.review_intelligence.reviews, ...detail.facts]) evidence.set(item.id, item);
    for (const a of detail.assessments) for (const c of a.claims) for (const item of c.evidence) evidence.set(item.id, item);
  }
  evidence.set("ev-sample-property-a-r99", review("sample-property-a", 99, { rating: 3, date: "2022-04-11T00:00:00Z", text: "Guest parking is nearly impossible after 7 PM.", categories: ["other_issues"] }));

  return {
    details: new Map(details.map((d) => [d.id, d])),
    summaries: details.map(summaryOf),
    lastRun,
    excluded,
    meta,
    evidence,
  };
}
