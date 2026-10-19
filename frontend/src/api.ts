// Typed access to the local Python server. Shapes mirror traffic_poc's
// record store (records/store.py, records/search.py, records/report.py).

export type Verdict = "supported" | "not_supported" | "insufficient_evidence";
export type VerificationStatus = "queued" | "running" | "completed" | "failed" | "skipped";
export type Decision = "approved" | "rejected";
export type Outcome = "candidate_violation" | "no_visible_violation" | "uncertain";

export interface RecordSummary {
  id: string;
  created_at: string;
  status: string;
  source: "tier1_bundle" | "manual_upload" | null;
  types: string[];
  bundle_id: string | null;
  source_video: string | null;
  camera_type: "CCTV" | "DASHCAM" | null;
  frame_count: number | null;
  fps: number | null;
  trigger_frame: number | null;
  target_id: string | null;
  outcome: Outcome | null;
  verification_status: VerificationStatus | null;
  verdict: Verdict | null;
  decision: Decision | null;
  snippet: string | null;
}

export interface Frame {
  frame_index: number;
  role: "trigger" | "context";
  sha256: string;
  width: number;
  height: number;
  media_type: string;
}

export interface Tier1Event {
  bundle_id: string;
  event_id: string;
  source_video: string;
  camera_type: "CCTV" | "DASHCAM";
  frame_count: number;
  fps: number | null;
  evidence_origin: "raw_frame" | "annotated_preview";
  trigger_type: string;
  trigger_frame: number;
  target_id: string;
  heuristic_value: number | null;
  heuristic_value_kind: string;
  frames: Frame[];
}

export interface Observation {
  frame_index: number;
  description: string;
}

export interface Provenance {
  model_id?: string;
  resolved_revision?: string;
  inference_seconds?: number;
  input_tokens?: number;
  peak_allocated_mib?: number;
  generation_limit_reached?: boolean;
  [key: string]: unknown;
}

export interface Verification {
  status: VerificationStatus;
  prompt_version: string;
  prompt_sha256: string;
  queued_at?: string;
  started_at?: string;
  finished_at?: string;
  total_seconds?: number;
  result: {
    observations: Observation[];
    verdict: Verdict;
    summary: string;
    limitations: string[];
  } | null;
  raw_response: string | null;
  provenance: Provenance | null;
  error: string | null;
}

export interface Finding {
  violation_type: string;
  subject: string;
  evidence: string;
  plate: string | null;
  confidence: number | null;
}

export interface Analysis {
  outcome: Outcome;
  findings: Finding[];
  summary: string;
  limitations: string[];
}

export interface Review {
  review_id: number;
  created_at: string;
  decision: Decision;
  reviewer: string;
  notes: string;
  corrected_analysis: Analysis | null;
}

export interface RecordDetail {
  id: string;
  created_at: string;
  status: string;
  source: "tier1_bundle" | "manual_upload";
  filename: string;
  location: string | null;
  captured_at: string | null;
  prompt_version: string | null;
  prompt_sha256: string | null;
  evidence: { width: number; height: number; model_width?: number; model_height?: number };
  tier1_manifest_sha256?: string;
  tier1_event?: Tier1Event;
  verification?: Verification | null;
  analysis: Analysis | null;
  raw_response: string | null;
  provenance: Provenance | null;
  error: string | null;
  started_at?: string;
  finished_at?: string;
  total_seconds?: number;
  reviews: Review[];
}

export interface CustodyEntry {
  at: string;
  action: string;
  actor: string;
  detail: string | null;
}

export interface Report {
  report_version: string;
  custody_log: CustodyEntry[];
}

export interface Health {
  model_id: string;
  model_state: "not_loaded" | "loading" | "ready" | "load_failed" | "external";
  offline: boolean;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("The local server is not responding. Start it with python -m traffic_poc serve.", 0);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(body?.error ?? `Request failed with status ${response.status}`, response.status);
  return body as T;
}

const postJSON = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const SEARCH_KEYS = [
  "q", "type", "camera_type", "verdict", "verification_status", "decision", "source", "source_video",
  "imported_from", "imported_to",
] as const;

export const api = {
  health: () => request<Health>("/api/health"),
  search: (params: URLSearchParams) => {
    const query = new URLSearchParams();
    for (const key of SEARCH_KEYS) {
      const value = params.get(key);
      if (value) query.set(key, value);
    }
    return request<RecordSummary[]>(`/api/records${query.size ? `?${query}` : ""}`);
  },
  record: (id: string) => request<RecordDetail>(`/api/records/${id}`),
  report: (id: string) => request<Report>(`/api/records/${id}/report`),
  review: (id: string, body: { decision: Decision; reviewer: string; notes: string; corrected_analysis: Analysis | null }) =>
    postJSON<RecordDetail>(`/api/records/${id}/review`, body),
  verify: (id: string) => postJSON<RecordDetail>(`/api/records/${id}/verify`, {}),
  submitImage: (body: { image_base64: string; filename: string; location: string | null; captured_at: string | null }) =>
    postJSON<{ id: string }>("/api/records", body),
  importBundle: (file: File) =>
    request<{ record_ids: string[] }>("/api/bundles", { method: "POST", headers: { "Content-Type": "application/zip" }, body: file }),
};

export const files = {
  frame: (id: string, frame: number) => `/api/records/${id}/frames/${frame}`,
  image: (id: string) => `/api/records/${id}/image`,
  original: (id: string) => `/api/records/${id}/original`,
  record: (id: string) => `/api/records/${id}/export`,
  report: (id: string) => `/api/records/${id}/report`,
};

export const MAX_IMAGE_BYTES = 12 * 1024 * 1024;
export const MAX_BUNDLE_BYTES = 256 * 1024 * 1024;

export function isPending(record: { status: string; verification_status?: string | null; verification?: Verification | null }) {
  const verification = record.verification_status ?? record.verification?.status;
  return ["queued", "running"].includes(record.status) || ["queued", "running"].includes(verification ?? "");
}
