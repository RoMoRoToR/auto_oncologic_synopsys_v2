import os
import time
import uuid
import threading
import traceback
from dataclasses import dataclass, asdict
from typing import Callable, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, Future

JOB_TIMEOUT_S = float(os.getenv("JOB_TIMEOUT_S", "900"))
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
    artifacts_ready: bool = False


_TERMINAL = {"done", "error"}
_STAGE_RANK = {
    "queued": 0,
    "draft": 1,
    "extract": 2,
    "discover": 3,
    "export": 4,
    "done": 5,
    "error": 6,
}


def _now() -> float:
    return time.time()


def _stage_rank(stage: str) -> int:
    return _STAGE_RANK.get(stage, -1)


def _deep_merge(a: Optional[dict], b: Optional[dict]) -> Optional[dict]:
    """Deep merge two dicts (b overrides a). Non-dicts are replaced."""
    if b is None:
        return a
    if a is None:
        return b
    if not isinstance(a, dict) or not isinstance(b, dict):
        return b
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _has_artifacts(res: Optional[dict]) -> bool:
    if not isinstance(res, dict):
        return False
    if res.get("docxId"):
        return True
    files = res.get("files")
    return isinstance(files, dict) and any(files.get(k) for k in ("docx", "pdf", "md", "yaml", "json"))


def _set(job_id: str, **patch) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return

        # Prevent a running worker from overwriting a terminal state (e.g., after timeout).
        if job.status in _TERMINAL:
            if "status" in patch and patch["status"] != job.status:
                patch.pop("status", None)
            if "stage" in patch and patch["stage"] != job.stage:
                patch.pop("stage", None)
            # Keep artifacts/result if worker reports them after we already timed out.
            if "result" in patch and patch["result"] is not None:
                job.result = _deep_merge(job.result, patch["result"])
                job.artifacts_ready = job.artifacts_ready or _has_artifacts(job.result)
                patch.pop("result", None)

        # Enforce monotonic stage/progress.
        if "stage" in patch:
            new_stage = str(patch["stage"])
            if _stage_rank(new_stage) < _stage_rank(job.stage):
                patch.pop("stage", None)
        if "progress" in patch:
            try:
                new_p = float(patch["progress"])
                if new_p < float(job.progress):
                    patch["progress"] = float(job.progress)
            except Exception:
                patch.pop("progress", None)

        # Merge partial result instead of replacing; ignore None to avoid wiping result.
        if "result" in patch:
            if patch["result"] is not None:
                job.result = _deep_merge(job.result, patch["result"])
                job.artifacts_ready = job.artifacts_ready or _has_artifacts(job.result)
            patch.pop("result", None)

        for k, v in patch.items():
            setattr(job, k, v)
        job.updated_at = _now()


def update(job_id: str, stage: str, progress: float, message: str, partial_result: Optional[dict] = None) -> None:
    patch = {
        "stage": str(stage),
        "progress": float(progress),
        "message": str(message),
    }
    if partial_result is not None:
        patch["result"] = partial_result
    _set(job_id, **patch)


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
        _set(job_id, status="running", stage="draft", progress=0.02, message="started", started_at=_now())
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
        # Do not discard partial artifacts; _set() preserves/merges result.
        _set(job_id, status="error", stage="error", progress=1.0, message="timeout", error="JOB_TIMEOUT")

    if fut and fut.done() and job.status in ("queued", "running"):
        try:
            fut.result(timeout=0.0)
        except Exception as e:
            _set(job_id, status="error", stage="error", progress=1.0, message="error", error=str(e))

    with _lock:
        job = _jobs.get(job_id)
        return asdict(job) if job else None
