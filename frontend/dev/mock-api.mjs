// Dev-only mock of the backend API contract (docs/api-contract.md) serving SYNTHETIC fixtures.
// Not used by `npm run dev`, `npm run build`, or `npm start`. See frontend/README.md.
import { createServer } from "node:http";
import { buildFixtures, SYNTHETIC_MARKER } from "./fixtures.mjs";

const PORT = Number(process.env.MOCK_API_PORT ?? 8010);
const SCENARIO = process.env.MOCK_SCENARIO ?? "default";
const RUN_DURATION_MS = 8000;

const fixtures = buildFixtures(`http://localhost:${PORT}/dev-images`);
let latestRun = SCENARIO === "empty" ? null : fixtures.lastRun;

function placeholderSvg(letter) {
  const hue = (letter.charCodeAt(0) * 47) % 360;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="750" viewBox="0 0 1200 750">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="hsl(${hue} 45% 62%)"/><stop offset="1" stop-color="hsl(${(hue + 40) % 360} 40% 38%)"/>
  </linearGradient></defs>
  <rect width="1200" height="750" fill="url(#g)"/>
  <g fill="rgba(255,255,255,0.18)">
    <rect x="380" y="220" width="440" height="430" rx="12"/>
    ${Array.from({ length: 12 }, (_, i) => `<rect x="${420 + (i % 4) * 100}" y="${260 + Math.floor(i / 4) * 110}" width="60" height="70" rx="6" fill="rgba(255,255,255,0.35)"/>`).join("")}
  </g>
  <text x="600" y="130" text-anchor="middle" font-family="system-ui, sans-serif" font-size="44" font-weight="700" fill="white">SYNTHETIC DEV IMAGE ${letter.toUpperCase()}</text>
</svg>`;
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "Content-Type": "application/json", "X-Synthetic-Data": "true", ...headers });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

function propertyList() {
  const items = SCENARIO === "empty" ? [] : fixtures.summaries;
  return {
    items,
    total: items.length,
    cities: [...new Set(items.map((p) => p.city))].sort(),
    last_run: latestRun,
  };
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const path = url.pathname.replace(/\/+$/, "");
  const segments = path.split("/").filter(Boolean);
  console.log(`${req.method} ${url.pathname}`);

  if (req.method === "GET" && segments[0] === "dev-images" && segments[1]) {
    res.writeHead(200, { "Content-Type": "image/svg+xml", "Cache-Control": "no-store" });
    res.end(placeholderSvg(segments[1].charAt(0)));
    return;
  }

  if (segments[0] !== "api") return send(res, 404, { detail: "Not found" });

  if (req.method === "POST" && path === "/api/runs") {
    if (latestRun?.status === "running") return send(res, 409, { detail: "A run is already in progress" });
    const run = {
      id: (latestRun?.id ?? 0) + 1,
      started_at: new Date().toISOString(),
      finished_at: null,
      status: "running",
      stats: {},
      limitations: [],
    };
    latestRun = run;
    setTimeout(() => {
      latestRun = {
        ...run,
        finished_at: new Date().toISOString(),
        status: "completed_with_limitations",
        stats: fixtures.lastRun.stats,
        limitations: fixtures.lastRun.limitations,
      };
    }, RUN_DURATION_MS);
    return send(res, 202, { run_id: run.id });
  }

  if (req.method !== "GET") return send(res, 405, { detail: "Method not allowed" });

  if (path === "/api/properties") return send(res, 200, propertyList());
  if (segments[1] === "properties" && segments[2]) {
    const detail = SCENARIO === "empty" ? undefined : fixtures.details.get(Number(segments[2]));
    return detail ? send(res, 200, detail) : send(res, 404, { detail: "Property not found" });
  }
  if (segments[1] === "evidence" && segments[2]) {
    const item = fixtures.evidence.get(decodeURIComponent(segments[2]));
    return item ? send(res, 200, item) : send(res, 404, { detail: "Evidence not found" });
  }
  if (path === "/api/excluded") return send(res, 200, fixtures.excluded);
  if (path === "/api/runs/latest") return send(res, 200, latestRun);
  if (path === "/api/meta") return send(res, 200, fixtures.meta);

  return send(res, 404, { detail: "Not found" });
});

server.listen(PORT, () => {
  console.log(`\n  ${SYNTHETIC_MARKER}`);
  console.log(`  Mock API (scenario: ${SCENARIO}) listening on http://localhost:${PORT}`);
  console.log(`  Point the frontend at it with: npm run dev:mock\n`);
});
