import type { VerificationStatus } from "../api";
import { STATUS_LABEL, VERDICT_LABEL, type Mark } from "../format";

const PENDING_LABEL: Partial<Record<VerificationStatus, string>> = { queued: STATUS_LABEL.queued, running: STATUS_LABEL.running };

/** The Tier-2 verdict, or the reason there is none, drawn as a sign. */
export function Sign({ mark, status, large }: { mark: Mark; status?: VerificationStatus | null; large?: boolean }) {
  let label: string;
  if (mark === "supported" || mark === "not_supported" || mark === "insufficient_evidence") label = VERDICT_LABEL[mark];
  else if (mark === "pending") label = (status && PENDING_LABEL[status]) || "Queued";
  else if (mark === "failed") label = STATUS_LABEL.failed;
  else if (mark === "skipped") label = STATUS_LABEL.skipped;
  else label = "Not verified";
  return <span className={`sign sign--${mark}${large ? " sign--large" : ""}`}>{label}</span>;
}
