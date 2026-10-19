import type { RecordSummary } from "../api";
import { markOf, type Mark } from "../format";

/** One Tier-1 bundle: the events a detector run found in one video. */
export interface Recording {
  key: string;
  bundleId: string | null;
  videoId: string | null;
  name: string;
  camera: string | null;
  frameCount: number;
  fps: number | null;
  events: RecordSummary[];
  /** Another recording in the results has the same file name. */
  sharedName: boolean;
}

/** Group results by recording, keeping the order in which recordings first rank. */
export function groupResults(results: RecordSummary[]) {
  const recordings = new Map<string, Recording>();
  const stills: RecordSummary[] = [];
  for (const result of results) {
    if (result.source !== "tier1_bundle") {
      stills.push(result);
      continue;
    }
    // A video uploaded to the app can span several bundles of 100 events.
    const key = result.video_id ?? result.bundle_id ?? result.source_video ?? "unknown";
    let recording = recordings.get(key);
    if (!recording) {
      recording = {
        key,
        bundleId: result.bundle_id,
        videoId: result.video_id,
        name: result.source_video ?? "Unnamed video",
        camera: result.camera_type,
        frameCount: result.frame_count ?? 0,
        fps: result.fps,
        events: [],
        sharedName: false,
      };
      recordings.set(key, recording);
    }
    recording.events.push(result);
    recording.frameCount = Math.max(recording.frameCount, result.trigger_frame ?? 0);
  }
  const list = [...recordings.values()];
  for (const recording of list) {
    recording.events.sort((a, b) => (a.trigger_frame ?? 0) - (b.trigger_frame ?? 0));
    recording.sharedName = list.some((other) => other !== recording && other.name === recording.name);
  }
  return { recordings: list, stills };
}

export function countMarks(events: RecordSummary[]) {
  const counts: Record<Mark, number> = {
    supported: 0, not_supported: 0, insufficient_evidence: 0, pending: 0, failed: 0, skipped: 0, unverified: 0,
  };
  for (const event of events) counts[markOf(event)] += 1;
  return counts;
}

/** Milepost spacing in seconds that gives at most about seven posts along a clip. */
export function milepostStep(seconds: number) {
  const steps = [1, 2, 5, 10, 15, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600];
  return steps.find((step) => seconds / step <= 7) ?? 3600;
}
