import type { Outcome, RecordSummary, Verdict, VerificationStatus } from "./api";

const pad = (value: number) => String(value).padStart(2, "0");

/** Seconds from the first decoded frame; frame 1 is at 0 s, as in the report. */
export const frameSeconds = (frame: number, fps: number) => (frame - 1) / fps;

/** HH:MM:SS:FF timecode, the way editing tools label a frame. */
export function timecode(frame: number, fps: number | null) {
  if (!fps) return `F${frame}`;
  const time = frameSeconds(frame, fps);
  const whole = Math.floor(time);
  const frames = Math.floor((time - whole) * fps);
  return `${pad(Math.floor(whole / 3600))}:${pad(Math.floor(whole / 60) % 60)}:${pad(whole % 60)}:${pad(frames)}`;
}

export const fpsLabel = (fps: number) => `${Number(fps.toFixed(2))} fps`;

export function duration(seconds: number) {
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function dateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export const shortHash = (hash: string) => hash.slice(0, 12);

export const VERDICT_LABEL: Record<Verdict, string> = {
  supported: "Supported",
  not_supported: "Not supported",
  insufficient_evidence: "Insufficient evidence",
};

export const STATUS_LABEL: Record<VerificationStatus, string> = {
  queued: "Queued",
  running: "Verifying",
  completed: "Verified",
  failed: "Verification failed",
  skipped: "Skipped",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  candidate_violation: "Candidate violation",
  no_visible_violation: "No visible violation",
  uncertain: "Uncertain",
};

const FINDING_LABEL: Record<string, string> = { no_helmet: "No helmet", triple_riding: "Triple riding" };

export const typeLabel = (type: string) => FINDING_LABEL[type] ?? type;

/** Trigger types the Tier-1 detector emits (detection/detector.py) and image findings (vlm/outputs.py). */
export const KNOWN_TYPES = [
  "Wrong-Way Driving",
  "Multi-Vehicle Collision",
  "Unsafe Following",
  "Red-Light Running",
  "Ego Collision (Pixel Shift Spike)",
  "Ego-Vehicle Collision (Looming)",
  "no_helmet",
  "triple_riding",
];

/** One state per record for markers and signs: the Tier-2 verdict, or why there is none. */
export type Mark = Verdict | "pending" | "failed" | "skipped" | "unverified";

export function markOf(record: Pick<RecordSummary, "verdict" | "verification_status">): Mark {
  if (record.verdict) return record.verdict;
  switch (record.verification_status) {
    case "queued":
    case "running":
      return "pending";
    case "failed":
      return "failed";
    case "skipped":
      return "skipped";
    default:
      return "unverified";
  }
}

export function eventTitle(record: RecordSummary) {
  return record.types.map(typeLabel).join(", ") || "No finding";
}
