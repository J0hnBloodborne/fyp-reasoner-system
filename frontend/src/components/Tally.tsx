import type { VerificationStatus } from "../api";
import { STATUS_LABEL, VERDICT_LABEL, type Mark } from "../format";

/** The Tier-2 verdict, or the reason there is none, as a tally light. */
export function Tally({ mark, status, large }: { mark: Mark; status?: VerificationStatus | null; large?: boolean }) {
  let label: string;
  if (mark === "supported" || mark === "not_supported" || mark === "insufficient_evidence") label = VERDICT_LABEL[mark];
  else if (mark === "pending") label = status === "running" ? STATUS_LABEL.running : STATUS_LABEL.queued;
  else if (mark === "failed") label = STATUS_LABEL.failed;
  else if (mark === "skipped") label = STATUS_LABEL.skipped;
  else label = "Not verified";
  return <span className={`tally tally--${mark}${large ? " tally--large" : ""}`}>{label}</span>;
}
