const TIME_ZONE = "America/Los_Angeles";

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  month: "long",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  month: "long",
  day: "numeric",
  year: "numeric",
});

const calendarDateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "long",
  day: "numeric",
  year: "numeric",
});

export function formatMoney(amount: number): string {
  return moneyFormatter.format(amount);
}

export function formatMoneyRange(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min === null || max === null || min === max) return formatMoney((min ?? max) as number);
  return `${formatMoney(min)}–${formatMoney(max)}`;
}

export function formatSqftRange(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  const fmt = (n: number) => Math.round(n).toLocaleString("en-US");
  if (min === null || max === null || min === max) return `${fmt((min ?? max) as number)} sq ft`;
  return `${fmt(min)}–${fmt(max)} sq ft`;
}

function parseIso(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

// Assembled from parts so server and browser ICU versions produce identical text (avoids hydration drift).
export function formatDateTime(iso: string): string {
  const date = parseIso(iso);
  if (!date) return iso;
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    dateTimeFormatter.formatToParts(date).find((p) => p.type === type)?.value ?? "";
  return `${part("month")} ${part("day")}, ${part("year")} at ${part("hour")}:${part("minute")} ${part("dayPeriod")}`;
}

// Date-only values (e.g. review dates) arrive as midnight UTC; converting them to Pacific time would
// show the previous day, so they are formatted as calendar dates instead.
const MIDNIGHT_UTC = /^\d{4}-\d{2}-\d{2}$|T00:00(:00(\.0+)?)?(Z|\+00:00)$/;

export function formatDate(iso: string): string {
  const date = parseIso(iso);
  if (!date) return iso;
  return MIDNIGHT_UTC.test(iso) ? calendarDateFormatter.format(date) : dateFormatter.format(date);
}

export function formatCalendarDate(ymd: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd);
  if (!match) return ymd;
  const [, y, m, d] = match;
  return calendarDateFormatter.format(new Date(Date.UTC(Number(y), Number(m) - 1, Number(d))));
}

export function formatScore(score: number): string {
  return score.toFixed(1);
}

export function formatRating(rating: number): string {
  return rating.toFixed(1);
}

export function formatMinutes(minutes: number): string {
  return `${Math.round(minutes)} min`;
}

export function formatMiles(miles: number): string {
  return `${miles.toFixed(1)} mi`;
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

export function humanize(slug: string): string {
  const text = slug.replace(/[_-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count.toLocaleString("en-US")} ${count === 1 ? singular : plural}`;
}

export function bedsLabel(beds: number | null): string {
  if (beds === null) return "Beds unknown";
  return beds === 0 ? "Studio" : `${beds} BR`;
}

export function formatDetailValue(value: unknown): string | null {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return null;
}
