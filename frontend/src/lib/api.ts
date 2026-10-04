import { backendUrl } from "./backend-url";
import type {
  EvidenceItem,
  ExcludedProperty,
  Meta,
  PropertyDetail,
  PropertyListResponse,
  RunInfo,
} from "./types";

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null, options?: ErrorOptions) {
    super(message, options);
    this.name = "ApiError";
    this.status = status;
  }

  get isUnreachable(): boolean {
    return this.status === null;
  }
}

// Server components call the backend directly; the browser goes through the Next.js /api rewrite.
function apiBase(): string {
  return typeof window === "undefined" ? backendUrl() : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}/api${path}`, {
      cache: "no-store",
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (cause) {
    throw new ApiError("The apartment data API is unreachable.", null, { cause });
  }
  if (!response.ok) {
    throw new ApiError(`The API responded with status ${response.status}.`, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  listProperties: () => request<PropertyListResponse>("/properties"),
  getProperty: (id: number | string) => request<PropertyDetail>(`/properties/${encodeURIComponent(id)}`),
  getEvidence: (id: string) => request<EvidenceItem>(`/evidence/${encodeURIComponent(id)}`),
  listExcluded: () => request<ExcludedProperty[]>("/excluded"),
  getLatestRun: () => request<RunInfo | null>("/runs/latest"),
  startRun: () => request<{ run_id: number }>("/runs", { method: "POST" }),
  getMeta: () => request<Meta>("/meta"),
};
