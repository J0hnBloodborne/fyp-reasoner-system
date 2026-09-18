"""Bounded job orchestration independent of the web transport and model implementation."""

import logging
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from traffic_poc.config import Settings
from traffic_poc.evidence import ingest_image
from traffic_poc.inference import Reasoner
from traffic_poc.prompts import PROMPT_VERSION
from traffic_poc.schemas import Submission, parse_analysis
from traffic_poc.storage import Repository, now

logger = logging.getLogger(__name__)


class PipelineBusy(Exception):
    """The bounded job capacity is exhausted."""


class Pipeline:
    def __init__(self, settings: Settings, reasoner: Reasoner, repository: Repository):
        self.settings = settings
        self.reasoner = reasoner
        self.repository = repository
        self.capacity = threading.BoundedSemaphore(settings.max_pending)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self.repository.recover_interrupted()

    def submit(self, submission: Submission) -> str:
        """Validate evidence before persisting a bounded asynchronous inference job."""
        if not self.capacity.acquire(blocking=False):
            raise PipelineBusy("Inference queue is full; wait for a job to finish")
        record_id = uuid.uuid4().hex
        try:
            evidence = ingest_image(submission.image_base64, record_id, self.settings)
            self.repository.create({
                "schema_version": "1.0", "id": record_id, "created_at": now(),
                "status": "queued", "source": "manual_upload",
                "filename": submission.filename,
                "location": submission.location, "captured_at": submission.captured_at,
                "prompt_version": PROMPT_VERSION, "evidence": evidence.metadata(),
                "analysis": None, "raw_response": None, "provenance": None,
                "error": None, "confidence_calibrated": False,
                "notice_issued": False,
            })
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
            self.repository.update(record_id, raw_response=response.raw,
                                   provenance=response.provenance)
            analysis = parse_analysis(response.raw)
            if response.provenance.get("generation_limit_reached"):
                raise ValueError("Model reached the generation limit; inspect raw output")
            self.repository.update(record_id, status="completed",
                                   analysis=analysis.model_dump(), finished_at=now(),
                                   total_seconds=round(time.perf_counter() - started, 3))
        except Exception as exc:
            logger.exception("Inference job %s failed", record_id)
            self.repository.update(record_id, status="failed", finished_at=now(),
                                   error=f"{type(exc).__name__}: {exc}",
                                   total_seconds=round(time.perf_counter() - started, 3))
        finally:
            self.capacity.release()

    def close(self) -> None:
        """Drain already accepted jobs on a normal shutdown."""
        self.executor.shutdown(wait=True)

    def wait(self, record_id: str, timeout: float = 30) -> dict:
        """Allow tests and scripts to await a terminal record without GPU-specific code."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.repository.get(record_id)
            if record["status"] in {"completed", "failed"}:
                return record
            threading.Event().wait(0.05)
        raise queue.Empty("Record did not finish before the timeout")
