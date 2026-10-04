"""Journal structuré : une ligne JSON par événement (logger « pai.events »).

Champs : event, request_id, job_id, stage, duration_ms, provider, model, tier, task, cache_hit, success, error…
JAMAIS : contenu de CV, de lettre ou d'offre, données personnelles, prompt, jeton, clé, cookie. Seules les clés de
ALLOWED passent ; les erreurs sont raccourcies et expurgées (e-mails, numéros, jetons).
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger("pai.events")
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("pai_request_id", default="")
job_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("pai_job_id", default="")
tier_var: contextvars.ContextVar[str] = contextvars.ContextVar("pai_ai_tier", default="")

ALLOWED = {"stage", "duration_ms", "provider", "model", "tier", "task", "cache_hit", "success", "error", "status",
           "method", "path", "job_type", "generation_id", "offer_id", "mode", "score", "pages", "count", "code"}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SECRETISH = re.compile(r"(sk-[\w-]{6,}|sk-ant-[\w-]{6,}|[A-Za-z0-9_-]{32,}|Bearer\s+\S+)")
_DIGITS = re.compile(r"\+?\d[\d\s.-]{7,}\d")


def new_request_id(candidate: str | None = None) -> str:
    """Identifiant fourni par l'appelant (en-tête X-Request-ID) s'il est sûr, sinon un nouveau."""
    if candidate and _REQUEST_ID.match(candidate):
        return candidate
    return uuid.uuid4().hex[:16]


def scrub(text: str, limit: int = 160) -> str:
    t = _EMAIL.sub("[e-mail]", str(text))
    t = _SECRETISH.sub("[masqué]", t)
    return _DIGITS.sub("[numéro]", t)[:limit]


def event(name: str, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"event": name, "ts": round(time.time(), 3)}
    if request_id_var.get():
        payload["request_id"] = request_id_var.get()
    if job_id_var.get():
        payload["job_id"] = job_id_var.get()
    for k, v in fields.items():
        if k in ALLOWED and v is not None and v != "":
            payload[k] = scrub(v) if k == "error" else v
    try:
        log.info(json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001 — journaliser ne doit jamais casser un traitement
        pass
    return payload


@contextmanager
def bound(request_id: str | None = None, job_id: str | None = None) -> Iterator[None]:
    """Associe request_id / job_id au contexte courant (requête HTTP, job du worker)."""
    tokens = []
    if request_id is not None:
        tokens.append((request_id_var, request_id_var.set(request_id)))
    if job_id is not None:
        tokens.append((job_id_var, job_id_var.set(job_id)))
    try:
        yield
    finally:
        for var, tok in reversed(tokens):
            var.reset(tok)
