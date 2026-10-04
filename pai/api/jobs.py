"""File de jobs adossée à la base (PENDING / RUNNING / DONE / FAILED), reprenable et idempotente.

PostgreSQL : réservation par `SELECT … FOR UPDATE SKIP LOCKED` (plusieurs workers possibles).
SQLite : réservation transactionnelle simple (un seul worker).
Un job RUNNING dont le verrou a expiré est remis en PENDING au démarrage du worker.
"""

from __future__ import annotations

import logging
import os
import secrets
import socket
import threading
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from .. import obs, paths
from ..config import get_settings
from ..db.models import Job, utcnow
from ..db.session import get_engine, init_db, session_scope

log = logging.getLogger("pai.jobs")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
STALE_AFTER = timedelta(minutes=15)


def enqueue(job_type: str, payload: dict[str, Any], idempotency_key: str | None = None) -> Job:
    with session_scope() as s:
        if idempotency_key:
            existing = s.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
            if existing is not None:
                s.expunge(existing)
                return existing
        rid = obs.request_id_var.get()
        job = Job(id="job_" + secrets.token_hex(8), type=job_type, payload=payload | ({"_rid": rid} if rid else {}),
                  idempotency_key=idempotency_key)
        s.add(job)
        s.flush()
        s.expunge(job)
        return job


def get_job(job_id: str) -> Job | None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is not None:
            s.expunge(job)
        return job


def _claim(s) -> Job | None:
    stmt = select(Job).where(Job.status == "PENDING").order_by(Job.created_at).limit(1)
    if get_engine().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = s.scalar(stmt)
    if job is None:
        return None
    job.status, job.locked_by, job.started_at, job.attempts = "RUNNING", WORKER_ID, utcnow(), job.attempts + 1
    return job


def requeue_stale() -> int:
    with session_scope() as s:
        stale = s.scalars(select(Job).where(Job.status == "RUNNING", Job.started_at < utcnow() - STALE_AFTER)).all()
        for job in stale:
            job.status, job.locked_by = ("PENDING" if job.attempts < job.max_attempts else "FAILED"), None
            if job.status == "FAILED":
                job.error = "Abandonné : trop de tentatives interrompues"
        return len(stale)


def _progress(job_id: str):
    def report(stage: str, detail: str) -> None:
        with session_scope() as s:
            job = s.get(Job, job_id)
            if job is not None:
                job.progress = (job.progress or []) + [{"stage": stage, "detail": detail, "at": utcnow().isoformat()}]
    return report


def process(job: Job) -> dict[str, Any]:
    if job.type == "generate_pack":
        from .v1 import run_pack_job

        return run_pack_job(job.payload, progress=_progress(job.id))
    if job.type == "ai_complete":
        from .v1 import run_ai_complete_job

        return run_ai_complete_job(job.payload)
    if job.type == "benchmark":
        from ..benchmark import run_benchmark

        return run_benchmark(include_legacy=bool(job.payload.get("include_legacy", True)), persist=True)["summary"]
    raise ValueError(f"Type de job inconnu : {job.type}")


def run_once() -> bool:
    with session_scope() as s:
        job = _claim(s)
        if job is None:
            return False
        s.flush()
        s.expunge(job)
    started = time.monotonic()
    with obs.bound(request_id=str((job.payload or {}).get("_rid") or ""), job_id=job.id):
        try:
            result = process(job)
            status, error = "DONE", None
        except Exception as exc:  # noqa: BLE001 — échec propre, rien n'est perdu, relançable
            log.exception("Job %s en échec", job.id)
            result, status, error = None, "FAILED", f"{exc.__class__.__name__}: {exc}"[:2000]
        obs.event("job", job_type=job.type, status=status, success=status == "DONE",
                  duration_ms=int((time.monotonic() - started) * 1000), error=error and error.split(":")[0])
    with session_scope() as s:
        row = s.get(Job, job.id)
        if row is not None:
            row.status, row.result, row.error, row.finished_at, row.locked_by = status, result, error, utcnow(), None
            if row.type == "ai_complete":  # le prompt (extraits du profil) n'est pas conservé une fois l'appel fait
                row.payload = {k: v for k, v in (row.payload or {}).items() if k in ("task", "tier", "json")}
    return True


HEARTBEAT = "worker.heartbeat"


def _beat() -> None:
    try:
        (paths.DATA_DIR / HEARTBEAT).write_text(str(time.time()), encoding="utf-8")
    except OSError:  # stockage indisponible : le contrôle de santé le signalera
        pass


def _heartbeat(stop: threading.Event, every: float = 15.0) -> None:
    """Battement de cœur du worker (contrôle de santé Docker) : écrit même pendant un long pack."""
    while not stop.wait(every):
        _beat()


def run_worker(once: bool = False, poll: float = 1.0, stop: threading.Event | None = None) -> None:
    init_db()
    requeue_stale()
    _beat()
    if not once:
        threading.Thread(target=_heartbeat, args=(stop or threading.Event(),), daemon=True, name="pai-heartbeat").start()
    while True:
        did = run_once()
        if once and not did:
            return
        if stop is not None and stop.is_set():
            return
        if not did:
            time.sleep(poll)


_thread: threading.Thread | None = None
_stop = threading.Event()


def start_inline_worker() -> None:
    """Worker dans le processus de l'API (déploiement mono-conteneur). Désactivable : PAI_INLINE_WORKER=0."""
    global _thread
    if os.environ.get("PAI_INLINE_WORKER", "1") == "0" or get_settings().environment == "test":
        return
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=run_worker, kwargs={"stop": _stop}, daemon=True, name="pai-worker")
        _thread.start()


def stop_inline_worker() -> None:
    _stop.set()
