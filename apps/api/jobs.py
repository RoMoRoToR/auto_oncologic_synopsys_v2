import os
import time
import uuid
import threading
import traceback
from dataclasses import dataclass, asdict
from typing import Callable, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, Future

JOB_TIMEOUT_S = float(os.getenv("JOB_TIMEOUT_S", "50"))
JOBS_WORKERS = int(os.getenv("JOBS_WORKERS", "4"))

_executor = ThreadPoolExecutor(max_workers=JOBS_WORKERS)
_lock = threading.Lock()
_jobs: Dict[str, "Job"] = {}
_futures: Dict[str, Future] = {}


@dataclass
class Job:
    id: str
    kind: str
    status: str          # queued|running|done|error
    stage: str           # queued|draft|discover|extract|export|done|error
    progress: float
    message: str
    created_at: float
    started_at: Optional[float]
    updated_at: float
    result: Optional[dict]
    error: Optional[str]


def _now() -> float:
    return time.time()


def _set(job_id: str, **patch) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for k, v in patch.items():
            setattr(job, k, v)
        job.updated_at = _now()


def update(job_id: str, stage: str, progress: float, message: str, partial_result: Optional[dict] = None) -> None:
    if partial_result is None:
        _set(job_id, stage=stage, progress=float(progress), message=message)
    else:
        _set(job_id, stage=stage, progress=float(progress), message=message, result=partial_result)


def create_job(kind: str, fn: Callable[[Callable[..., None]], dict]) -> Job:
    job_id = uuid.uuid4().hex
    job = Job(
        id=job_id,
        kind=kind,
        status="queued",
        stage="queued",
        progress=0.0,
        message="queued",
        created_at=_now(),
        started_at=None,
        updated_at=_now(),
        result=None,
        error=None,
    )
    with _lock:
        _jobs[job_id] = job

    def _runner():
        _set(job_id, status="running", stage="running", progress=0.02, message="started", started_at=_now())
        start = _now()

        def _u(stage: str, progress: float, message: str, partial_result: Optional[dict] = None):
            update(job_id, stage, progress, message, partial_result)

        try:
            res = fn(_u)
            _set(job_id, status="done", stage="done", progress=1.0, message=f"done in {_now()-start:.1f}s", result=res)
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=8)}"
            _set(job_id, status="error", stage="error", progress=1.0, message="error", error=err)

    fut = _executor.submit(_runner)
    with _lock:
        _futures[job_id] = fut
    return job


def get_job(job_id: str) -> Optional[dict]:
    with _lock:
        job = _jobs.get(job_id)
        fut = _futures.get(job_id)

    if not job:
        return None

    if job.status in ("queued", "running") and job.started_at and (_now() - job.started_at) > JOB_TIMEOUT_S:
        _set(job_id, status="error", stage="error", progress=1.0, message="timeout", error="JOB_TIMEOUT")

    if fut and fut.done() and job.status in ("queued", "running"):
        try:
            fut.result(timeout=0.0)
        except Exception as e:
            _set(job_id, status="error", stage="error", progress=1.0, message="error", error=str(e))

    with _lock:
        job = _jobs.get(job_id)
        return asdict(job) if job else None
