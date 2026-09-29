"""API versionnée /v1 (API first). Exemples de requêtes et de réponses : docs/api.md.

Contrat futur JobAgent → PAI : candidate_id, offer_id, offer_url, offer_text, company, role, source,
profile_version, context. PAI → JobAgent : generation_id, strategy, match, recommended_cv, cv_version,
letter_version, questions, application_pack (URL signées), quality_scores, risks, next_action.
PAI ne postule jamais et n'envoie rien : il renvoie des documents à relire.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, text

from .. import ENGINE_VERSION
from ..config import get_settings
from ..db.models import Feedback, Generation, Job, Outcome, StoredFile, StoreDocument, utcnow
from ..db.repo import load_current_profile, persist_pack, record_calls, save_profile_doc, spent_today
from ..db.session import session_scope
from ..ingest import IngestError, UrlIngestError, offer_from_text, offer_from_url
from ..pipeline import Pipeline
from ..profile import import_json, profile_version_tag, validate_profile
from ..providers import get_provider
from ..providers.base import BudgetExceeded, DegradedMode, ProviderError, extract_json
from ..rules import load_rules, prompts_version
from ..schemas import Offer
from . import jobs, settings_ai
from .auth import Principal, require
from .security import sign, unsign

router = APIRouter(prefix="/v1", tags=["v1"])
router.include_router(settings_ai.router)  # /v1/settings/ai, /v1/settings/ai/test


class OfferIn(BaseModel):
    offer_text: str = Field("", max_length=60000)
    offer_url: str = Field("", max_length=2000)
    job_title: str = Field("", alias="role", max_length=300)
    company: str = Field("", max_length=300)
    offer_id: str = ""
    candidate_id: str = ""
    source: str = "api"
    profile_version: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field("STANDARD", pattern="^(QUICK|STANDARD|DEEP)$")
    questions: str = Field("", max_length=20000)

    model_config = {"populate_by_name": True}


def _offer(body: OfferIn) -> Offer:
    try:
        if body.offer_text.strip():
            return offer_from_text(body.offer_text, title=body.job_title, company=body.company, source_url=body.offer_url)
        if body.offer_url:
            return offer_from_url(body.offer_url)
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail="offer_text ou offer_url requis")


def _remaining_budget() -> float:
    with session_scope() as s:
        return max(0.0, get_settings().cost_cap_eur_per_day - spent_today(s))


def _current_profile():
    try:
        with session_scope() as s:
            return load_current_profile(s)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Aucun profil : importez-le (onglet Profil ou python -m pai import-profile).") from exc


def _pipeline(mode: str, progress: Callable[[str, str], None] | None = None) -> Pipeline:
    """Pipeline sur le profil courant. Budget = min(plafond par pack, reste du plafond journalier) :
    plafond atteint → chaque étape bascule proprement sur sa voie déterministe (100 % factuelle)."""
    profile = _current_profile()
    budget = min(get_settings().cost_cap_eur_per_pack, _remaining_budget())
    return Pipeline(profile, get_provider(budget_eur=budget), mode=mode, progress=progress)


def file_url(file_id: str | None) -> str | None:
    if not file_id:
        return None
    return f"{get_settings().base_url.rstrip('/')}/v1/files/{sign({'f': file_id}, 'file')}"


def run_pack_job(payload: dict[str, Any], progress: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    body = OfferIn.model_validate(payload)
    pipe = _pipeline(body.mode, progress)
    pack = pipe.run(_offer(body), questions=body.questions)
    with session_scope() as s:
        ids = persist_pack(s, pack, pipe.files, pipe.provider.calls, profile=pipe.profile)
    return {
        "generation_id": pack.id, "status": pack.status, "mode": pack.mode, "provider": pack.provider,
        "strategy": pack.strategy.best.model_dump(),
        "match": {k: getattr(pack.match, k) for k in ("match", "quality", "risk", "scores")},
        "recommended_cv": {"design_profile": pack.strategy.best.design_profile, "ats_mode": pack.strategy.best.ats_mode},
        "cv_version": pack.versions.cv_v, "letter_version": pack.versions.letter_v,
        "questions": [a.model_dump() for a in pack.answers],
        "application_pack": {"cv_pdf": file_url(ids.get("cv")), "letter_pdf": file_url(ids.get("letter")), "zip": file_url(ids.get("zip")),
                             "expires_in_seconds": get_settings().file_url_ttl_seconds},
        "quality_scores": json.loads(json.dumps(pack.scores, default=str)), "risks": pack.risks, "next_action": pack.next_action,
        "missing_profile_data": pack.missing_profile_data, "versions": pack.versions.model_dump(), "cost_eur": pack.cost_eur,
    }


# ── Offre depuis une URL (l'interface l'appelle quand l'utilisateur colle un lien) ──
class UrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


OFFER_FIELDS = {"id", "text", "title_hint", "company_hint", "source_url", "text_hash", "source_type"}


@router.post("/ingest/url")
def ingest_url(body: UrlIn, _: Principal = require("analyze")) -> dict[str, Any]:
    """Lecture sûre (SSRF) d'une page publique ; rien n'est enregistré. Échec → 422 {code, message} :
    login_walled, bad_url, blocked_address, too_large, timeout, http_error, unreadable."""
    try:
        offer = offer_from_url(body.url.strip())
    except UrlIngestError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    except IngestError as exc:
        raise HTTPException(status_code=422, detail={"code": "unreadable", "message": str(exc)}) from exc
    return {"offer": offer.model_dump(include=OFFER_FIELDS)}


@router.get("/status")
def server_status(_: Principal = require("read")) -> dict[str, Any]:
    """État pour l'interface : version du moteur, mode IA (REMOTE | LOCAL | DEGRADED), fournisseur actif, base."""
    active, mode = settings_ai.ai_status()
    try:
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        db = "ok"
    except Exception:  # noqa: BLE001 — l'état se lit même base en panne
        db = "error"
    return {"engine_v": ENGINE_VERSION, "ai_mode": mode, "active_provider": active, "db": db}


# ── Analyse, stratégie, CV, lettre ───────────────────────────────────────────
@router.post("/analyze-job")
def analyze_job(body: OfferIn, _: Principal = require("analyze")) -> dict[str, Any]:
    pipe = _pipeline("QUICK")
    offer = _offer(body)
    analysis = pipe.analyze(offer)
    match = pipe.match(analysis)
    with session_scope() as s:
        record_calls(s, pipe.provider.calls)
    return {"offer_id": offer.id, "analysis": analysis.model_dump(), "match": match.model_dump(), "provider": pipe.provider.name}


@router.post("/generate-strategy")
def generate_strategy(body: OfferIn, _: Principal = require("analyze")) -> dict[str, Any]:
    pipe = _pipeline("QUICK")
    offer = _offer(body)
    analysis = pipe.analyze(offer)
    match = pipe.match(analysis)
    strategy = pipe.strategy(analysis, match)
    with session_scope() as s:
        record_calls(s, pipe.provider.calls)
    return {"offer_id": offer.id, "strategy": strategy.model_dump(), "match": {"match": match.match, "quality": match.quality, "risk": match.risk}}


def _sync_pack(body: OfferIn) -> dict[str, Any]:
    _offer(body)
    payload = body.model_dump(by_alias=True)
    if payload["mode"] == "QUICK":
        payload["mode"] = "STANDARD"  # un document exige au moins le mode STANDARD
    return run_pack_job(payload)


@router.post("/generate-cv")
def generate_cv(body: OfferIn, _: Principal = require("generate")) -> dict[str, Any]:
    """Synchrone. Une génération produit toujours CV + lettre (même version) ; seule la réponse diffère."""
    r = _sync_pack(body)
    return {k: r[k] for k in ("generation_id", "status", "cv_version", "quality_scores", "risks", "next_action")} | {
        "cv_pdf": r["application_pack"]["cv_pdf"]}


@router.post("/generate-letter")
def generate_letter(body: OfferIn, _: Principal = require("generate")) -> dict[str, Any]:
    r = _sync_pack(body)
    return {k: r[k] for k in ("generation_id", "status", "letter_version", "risks", "next_action")} | {
        "letter_pdf": r["application_pack"]["letter_pdf"]}


@router.post("/generate-application-pack", status_code=202)
def generate_application_pack(body: OfferIn, idempotency_key: str | None = Header(None, max_length=200),
                              _: Principal = require("generate")) -> dict[str, Any]:
    """Asynchrone (file de jobs). Même Idempotency-Key → même job, jamais de doublon."""
    _offer(body)  # validation immédiate de l'entrée
    job = jobs.enqueue("generate_pack", body.model_dump(by_alias=True), idempotency_key)
    return {"job_id": job.id, "status": job.status, "poll": f"/v1/jobs/{job.id}"}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, _: Principal = require("read")) -> dict[str, Any]:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return {"job_id": job.id, "type": job.type, "status": job.status, "attempts": job.attempts, "progress": job.progress,
            "result": job.result, "error": job.error}


@router.get("/jobs")
def list_jobs(_: Principal = require("read")) -> dict[str, Any]:
    with session_scope() as s:
        rows = s.scalars(select(Job).order_by(Job.created_at.desc()).limit(50)).all()
        return {"jobs": [{"job_id": j.id, "type": j.type, "status": j.status, "created_at": j.created_at.isoformat()} for j in rows]}


# ── Profil, versions, retours, résultats ─────────────────────────────────────
@router.get("/profile")
def get_profile(_: Principal = require("read")) -> dict[str, Any]:
    profile = _current_profile()
    return json.loads(profile.model_dump_json(by_alias=True)) | {"tag": profile_version_tag(profile)}


@router.post("/profile/import")
async def import_profile(request: Request, _: Principal = require("admin")) -> dict[str, Any]:
    try:
        profile = import_json(await request.body())
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Profil invalide : {str(exc)[:300]}") from exc
    with session_scope() as s:
        save_profile_doc(s, profile)
    return {"imported": len(profile.facts), "tag": profile_version_tag(profile), "validated": profile.validated}


@router.post("/profile/validate")
def validate(_: Principal = require("admin")) -> dict[str, Any]:
    with session_scope() as s:
        try:
            profile = validate_profile(load_current_profile(s))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        save_profile_doc(s, profile)
    return {"validated": True, "version": profile.version, "tag": profile_version_tag(profile)}


@router.get("/versions")
def versions(_: Principal = require("read")) -> dict[str, Any]:
    profile = _current_profile()
    with session_scope() as s:
        gens = s.scalars(select(Generation).where(Generation.deleted_at.is_(None)).order_by(Generation.created_at.desc()).limit(20)).all()
        recent = [{"generation_id": g.id, "created_at": g.created_at.isoformat(), "status": g.status, **g.versions} for g in gens]
    return {"engine_v": ENGINE_VERSION, "prompt_v": prompts_version(), "rules_v": load_rules().version,
            "profile_v": profile_version_tag(profile), "recent_generations": recent}


class FeedbackIn(BaseModel):
    generation_id: str | None = None
    doc_type: str = Field("cv", pattern="^(cv|letter|answers|pack)$")
    element: str = Field(max_length=40)
    rating: int = Field(ge=-1, le=1)
    comment: str = Field("", max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


@router.post("/feedback", status_code=201)
def feedback(body: FeedbackIn, _: Principal = require("feedback")) -> dict[str, Any]:
    with session_scope() as s:
        if body.generation_id and s.get(Generation, body.generation_id) is None:
            raise HTTPException(status_code=404, detail="Génération inconnue")
        row = Feedback(**body.model_dump())
        s.add(row)
        s.flush()
        return {"id": row.id}


class OutcomeIn(BaseModel):
    generation_id: str | None = None
    offer_ref: str = Field("", max_length=200)
    stage: str = Field(pattern="^(applied|viewed|answered|response|interview|offer|rejected|no_response|withdrawn)$")
    occurred_at: datetime | None = None
    notes: str = Field("", max_length=4000)
    source: str = Field("jobagent", max_length=40)


@router.post("/outcomes", status_code=201)
def outcomes(body: OutcomeIn, _: Principal = require("outcomes")) -> dict[str, Any]:
    """Résultats réels de candidature (JobAgent ou saisie manuelle). Aucune statistique sous 5 cas (A5)."""
    with session_scope() as s:
        if body.generation_id and s.get(Generation, body.generation_id) is None:
            raise HTTPException(status_code=404, detail="Génération inconnue")
        row = Outcome(**body.model_dump())
        s.add(row)
        s.flush()
        return {"id": row.id}


@router.post("/benchmark/run", status_code=202)
def benchmark_run(idempotency_key: str | None = Header(None, max_length=200), _: Principal = require("benchmark")) -> dict[str, Any]:
    job = jobs.enqueue("benchmark", {"include_legacy": True}, idempotency_key)
    return {"job_id": job.id, "status": job.status, "poll": f"/v1/jobs/{job.id}"}


# ── Fichiers (URL signées de courte durée, aucune donnée personnelle dans l'URL) ──
@router.get("/files/{token}")
def download(token: str) -> Response:
    data = unsign(token, "file", get_settings().file_url_ttl_seconds)
    if not data:
        raise HTTPException(status_code=403, detail="Lien expiré ou invalide")
    with session_scope() as s:
        row = s.get(StoredFile, data.get("f"))
        if row is None:
            raise HTTPException(status_code=404, detail="Fichier introuvable")
        return Response(content=row.data, media_type=row.content_type,
                        headers={"Content-Disposition": f'attachment; filename="{row.name}"', "Cache-Control": "no-store"})


# ── Pont pour l'interface PAI Studio en mode serveur ─────────────────────────
class CompleteIn(BaseModel):
    prompt: str = ""
    turns: list[dict[str, str]] = Field(default_factory=list, max_length=40)
    tier: str = Field("default", pattern="^(quick|default|complex)$")
    task: str = Field("", max_length=40, pattern=r"^[a-z_]{0,40}$")   # tâche PAI Studio (le routeur choisit l'IA)
    json_mode: bool = Field(False, alias="json")
    images: list[str] = Field(default_factory=list, max_length=4)
    run_async: bool = Field(False, alias="async")                     # job + interrogation (IA locale lente, Cloudflare 100 s)

    model_config = {"populate_by_name": True}


TIER_TASK = {"quick": "studio_quick", "default": "studio_default", "complex": "studio_complex"}


class AiGatewayError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def ai_complete_core(task: str, prompt: str, json_mode: bool, images_b64: list[str]) -> dict[str, Any]:
    """Appel IA de la passerelle (synchrone ou dans un job). Lève AiGatewayError (code stable pour l'interface)."""
    remaining = _remaining_budget()
    if remaining <= 0:
        raise AiGatewayError(429, "rate_limited", "Plafond de coût IA journalier atteint")
    provider = get_provider(budget_eur=remaining)
    if not provider.available:
        raise AiGatewayError(503, "not_granted", "Aucune IA disponible : mode sans IA (voies déterministes)")
    try:
        images = [base64.b64decode(i, validate=True) for i in images_b64]
    except (binascii.Error, ValueError) as exc:
        raise AiGatewayError(400, "invalid_argument", "Image invalide") from exc
    try:
        result = provider.complete(task, prompt, prompt_tag=f"studio:{task}", images=images or None)
    except BudgetExceeded as exc:
        raise AiGatewayError(429, "rate_limited", str(exc)) from exc
    except DegradedMode as exc:
        raise AiGatewayError(503, "not_granted", str(exc)) from exc
    except ProviderError as exc:
        raise AiGatewayError(502, "upstream_error", str(exc)) from exc
    finally:
        with session_scope() as s:
            record_calls(s, provider.calls)
    route = getattr(provider, "last_route", {}) or {}
    meta = {"model": result.model, "tier": route.get("tier", ""), "cached": bool(result.cached)}
    if json_mode:
        try:
            return {"json": extract_json(result.text)} | meta
        except ValueError as exc:
            raise AiGatewayError(422, "invalid_json", "Réponse sans JSON valide") from exc
    return {"text": result.text, "truncated": False} | meta


def run_ai_complete_job(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return ai_complete_core(payload["task"], payload["prompt"], bool(payload.get("json")), payload.get("images") or [])
    except AiGatewayError as exc:
        raise RuntimeError(f"{exc.code}: {exc.message}") from exc


@router.post("/ai/complete")
def ai_complete(body: CompleteIn, _: Principal = require("generate")) -> Any:
    """Passerelle IA de PAI Studio. Le routeur décide : une tâche prévue sans IA répond tout de suite 503 not_granted
    (l'interface garde sa voie déterministe) ; `async` met l'appel dans la file de jobs (202 + job_id)."""
    task = body.task or TIER_TASK[body.tier]
    prompt = body.prompt or "\n\n".join(f"{t.get('role', 'user').upper()}: {t.get('content', '')}" for t in body.turns)
    if not prompt.strip():
        raise HTTPException(status_code=400, detail={"code": "invalid_argument", "message": "Entrée vide"})
    if len(prompt.encode("utf-8")) > 65536:
        raise HTTPException(status_code=413, detail={"code": "prompt_too_large", "message": "Entrée > 64 Kio"})
    if body.run_async:
        provider = get_provider()
        level, chosen = provider.route(task) if hasattr(provider, "route") else ("large", provider)
        if chosen is None:
            raise HTTPException(status_code=503, detail={"code": "not_granted", "message": f"{task} : traité sans IA (voie déterministe)"})
        job = jobs.enqueue("ai_complete", {"task": task, "prompt": prompt, "json": body.json_mode, "images": body.images, "tier": level})
        return JSONResponse(status_code=202, content={"job_id": job.id, "task": task, "tier": level})
    try:
        return ai_complete_core(task, prompt, body.json_mode, body.images)
    except AiGatewayError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


# Magasin de documents de l'interface (équivalent serveur du `db` des artefacts claude.ai).
_PATH = re.compile(r"^[A-Za-z0-9_.\-]{1,120}(/[A-Za-z0-9_.\-]{1,120}){1,7}$")
_COLLECTION = re.compile(r"^[A-Za-z0-9_.\-]{1,120}(/[A-Za-z0-9_.\-]{1,120}){0,6}$")


def _doc_path(path: str) -> str:
    if not _PATH.match(path) or len(path.split("/")) % 2:
        raise HTTPException(status_code=400, detail={"code": "invalid_argument", "message": "Chemin de document invalide"})
    return path


class StoreIn(BaseModel):
    data: dict[str, Any]


@router.get("/store/doc")
def store_get(path: str, _: Principal = require("read")) -> dict[str, Any]:
    with session_scope() as s:
        doc = s.get(StoreDocument, _doc_path(path))
        return {"exists": doc is not None, "data": doc.data if doc else None, "version": doc.version if doc else 0}


@router.put("/store/doc")
def store_put(path: str, body: StoreIn, _: Principal = require("admin")) -> dict[str, Any]:
    _doc_path(path)
    if len(json.dumps(body.data, ensure_ascii=False).encode("utf-8")) > 256 * 1024:
        raise HTTPException(status_code=413, detail={"code": "invalid_argument", "message": "Document > 256 Kio"})
    with session_scope() as s:
        doc = s.get(StoreDocument, path)
        if doc is None:
            s.add(StoreDocument(path=path, collection=path.rsplit("/", 1)[0], data=body.data))
            return {"version": 1}
        doc.data, doc.version, doc.updated_at = body.data, doc.version + 1, utcnow()
        return {"version": doc.version}


@router.delete("/store/doc")
def store_delete(path: str, _: Principal = require("admin")) -> dict[str, Any]:
    with session_scope() as s:
        doc = s.get(StoreDocument, _doc_path(path))
        if doc is not None:
            s.delete(doc)
    return {"deleted": True}


@router.get("/store/query")
def store_query(collection: str, order_by: str = "", direction: str = "asc", limit: int = 200,
                _: Principal = require("read")) -> dict[str, Any]:
    if not _COLLECTION.match(collection) or len(collection.split("/")) % 2 == 0:
        raise HTTPException(status_code=400, detail={"code": "invalid_argument", "message": "Collection invalide"})
    with session_scope() as s:
        docs = s.scalars(select(StoreDocument).where(StoreDocument.collection == collection)).all()
        items = [{"id": d.path.rsplit("/", 1)[-1], "data": d.data} for d in docs]
    if order_by:
        present = [d for d in items if d["data"].get(order_by) is not None]
        absent = [d for d in items if d["data"].get(order_by) is None]
        present.sort(key=lambda d: (str(type(d["data"][order_by])), d["data"][order_by]), reverse=direction == "desc")
        items = present + absent
    return {"docs": items[: max(1, min(limit, 1000))]}
