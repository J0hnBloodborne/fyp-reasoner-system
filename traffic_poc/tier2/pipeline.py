"""Bounded job orchestration independent of the web transport and model implementation."""

import hashlib
import logging
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from traffic_poc.config import Settings
from traffic_poc.records.evidence import ingest_image
from traffic_poc.records.schemas import (
    Submission,
    parse_analysis,
    parse_verification,
)
from traffic_poc.records.storage import Repository, now
from traffic_poc.tier2.inference import Reasoner
from traffic_poc.tier2.lease import RuntimeLease
from traffic_poc.tier2.prompts import (
    PROMPT_VERSION,
    VERIFY_PROMPT_VERSION,
    prompt_hash,
    verify_prompt_hash,
)

logger = logging.getLogger(__name__)


class PipelineBusy(Exception):
    """The bounded job capacity is exhausted."""


class Pipeline:
    def __init__(self, settings: Settings, reasoner: Reasoner, repository: Repository):
        self.settings = settings
        self.reasoner = reasoner
        self.repository = repository
        self.lease = RuntimeLease(settings.data_dir)
        self.capacity = threading.BoundedSemaphore(settings.max_pending)
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="inference"
        )
        self.lifecycle_lock = threading.Lock()
        self.closed = False
        self.verifying: set[str] = set()
        try:
            self.repository.recover_interrupted()
            for record_id in self.repository.unverified_tier1():
                self.verify(record_id)
        except Exception:
            self.lease.close()
            self.executor.shutdown(wait=True)
            raise

    def submit(self, submission: Submission) -> str:
        """Validate evidence before persisting a bounded asynchronous inference job."""
        with self.lifecycle_lock:
            if self.closed:
                raise PipelineBusy("Application is shutting down")
            return self._submit(submission)

    def _submit(self, submission: Submission) -> str:
        if not self.capacity.acquire(blocking=False):
            raise PipelineBusy("Inference queue is full; wait for a job to finish")
        record_id = uuid.uuid4().hex
        try:
            evidence = ingest_image(submission.image_base64, record_id, self.settings)
            self.repository.create(
                {
                    "schema_version": "1.0",
                    "id": record_id,
                    "created_at": now(),
                    "status": "queued",
                    "source": "manual_upload",
                    "filename": submission.filename,
                    "location": submission.location,
                    "captured_at": submission.captured_at,
                    "prompt_version": PROMPT_VERSION,
                    "prompt_sha256": prompt_hash(),
                    "evidence": evidence.metadata(),
                    "analysis": None,
                    "raw_response": None,
                    "provenance": None,
                    "error": None,
                    "confidence_calibrated": False,
                    "notice_issued": False,
                }
            )
            self.executor.submit(self._run, record_id, evidence)
            return record_id
        except Exception:
            self.capacity.release()
            raise

    def _run(self, record_id, evidence) -> None:
        """Persist raw output before validation so malformed responses remain inspectable."""
        started = time.perf_counter()
        try:
            self.repository.update(record_id, status="running", started_at=now())
            response = self.reasoner.analyze(evidence)
            self.repository.update(
                record_id, raw_response=response.raw, provenance=response.provenance
            )
            analysis = parse_analysis(response.raw)
            if response.provenance.get("generation_limit_reached"):
                raise ValueError(
                    "Model reached the generation limit; inspect raw output"
                )
            self.repository.update(
                record_id,
                status="completed",
                analysis=analysis.model_dump(),
                finished_at=now(),
                total_seconds=round(time.perf_counter() - started, 3),
            )
        except Exception as exc:
            logger.exception("Inference job %s failed", record_id)
            self.repository.update(
                record_id,
                status="failed",
                finished_at=now(),
                error=f"{type(exc).__name__}: {exc}",
                total_seconds=round(time.perf_counter() - started, 3),
            )
        finally:
            self.capacity.release()

    def verify(self, record_id: str) -> None:
        """Queue Tier-2 verification of an imported Tier-1 event.

        Verification jobs share the single GPU worker but not the upload
        capacity, because one bundle can hold up to 100 events.
        """
        with self.lifecycle_lock:
            if self.closed:
                raise PipelineBusy("Application is shutting down")
            record = self.repository.get(record_id)
            if record.get("source") != "tier1_bundle":
                raise ValueError("Only imported Tier-1 events can be verified")
            if record_id in self.verifying:
                return
            verification = {
                "status": "queued",
                "prompt_version": VERIFY_PROMPT_VERSION,
                "prompt_sha256": verify_prompt_hash(),
                "queued_at": now(),
                "result": None,
                "raw_response": None,
                "provenance": None,
                "error": None,
            }
            if record["tier1_event"]["evidence_origin"] != "raw_frame":
                verification.update(
                    status="skipped",
                    error="Annotated previews are not valid VLM evidence",
                )
                self.repository.update(record_id, verification=verification)
                return
            self.repository.update(record_id, verification=verification)
            self.verifying.add(record_id)
            self.executor.submit(self._verify, record_id)

    def _verify(self, record_id: str) -> None:
        try:
            if not self.closed:  # Otherwise left queued; the next start resumes it.
                self._run_verification(record_id)
        finally:
            with self.lifecycle_lock:
                self.verifying.discard(record_id)

    def _run_verification(self, record_id: str) -> None:
        """Persist raw output before validation, as for uploaded images."""
        started = time.perf_counter()
        record = self.repository.get(record_id)
        verification = record["verification"]
        try:
            verification.update(status="running", started_at=now())
            self.repository.update(record_id, verification=verification)
            event = record["tier1_event"]
            frames = []
            for frame in sorted(event["frames"], key=lambda item: item["frame_index"]):
                path = self.settings.data_dir / "evidence" / frame["file"]
                if hashlib.sha256(path.read_bytes()).hexdigest() != frame["sha256"]:
                    raise ValueError(f"Evidence frame changed: {frame['file']}")
                frames.append((frame["frame_index"], frame["role"], path))
            response = self.reasoner.verify(event["trigger_type"], frames)
            verification.update(
                raw_response=response.raw, provenance=response.provenance
            )
            self.repository.update(record_id, verification=verification)
            result = parse_verification(response.raw, {index for index, _, _ in frames})
            if response.provenance.get("generation_limit_reached"):
                raise ValueError(
                    "Model reached the generation limit; inspect raw output"
                )
            verification.update(status="completed", result=result.model_dump())
        except Exception as exc:
            logger.exception("Verification of %s failed", record_id)
            verification.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        verification.update(
            finished_at=now(), total_seconds=round(time.perf_counter() - started, 3)
        )
        self.repository.update(record_id, verification=verification)

    def close(self) -> None:
        """Drain already accepted jobs on a normal shutdown."""
        with self.lifecycle_lock:
            self.closed = True
        self.executor.shutdown(wait=True)
        self.lease.close()

    def wait(self, record_id: str, timeout: float = 30) -> dict:
        """Allow tests and scripts to await a terminal record without GPU-specific code."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.repository.get(record_id)
            if record["status"] in {"completed", "failed"}:
                return record
            threading.Event().wait(0.05)
        raise queue.Empty("Record did not finish before the timeout")
