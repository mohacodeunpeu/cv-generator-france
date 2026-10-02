"""API /api : contrat simple et stable pour l'interface, JobAgent et les scripts. Exemples : docs/api.md.

Entrées acceptées DIRECTEMENT (sans copier-coller) : texte, URL, fichier PDF / HTML / DOCX / texte, en JSON ou en
multipart/form-data. Erreurs : {"detail": {"code": "...", "message": "..."}} avec un message affichable.
Aucune route n'exige d'IA ni de clé payante : sans IA, les réponses sont produites par les voies déterministes.
PAI ne postule jamais et n'envoie rien : il renvoie des analyses et des documents à relire.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import case, func, select, text
from starlette.concurrency import run_in_threadpool

from .. import ENGINE_VERSION, obs, paths
from ..config import get_settings
from ..db.models import ApplicationPackRow, Generation, Job, LlmCall, OfferRow, StoredFile
from ..db.repo import ats_summary, record_calls
from ..db.session import session_scope
from ..ingest import IngestError, UrlIngestError, offer_from_file, offer_from_text, offer_from_url
from ..schemas import Offer
from ..textnorm import stable_hash
from . import jobs, settings_ai
from .auth import Principal, require

router = APIRouter(prefix="/api", tags=["api"])
MAX_UPLOAD = 8 * 1024 * 1024
OFFER_FIELDS = ("id", "text", "title_hint", "company_hint", "source_url", "source_type", "text_hash")


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


_CLIENTS: dict[str, str] = {}


def seen(principal: Principal) -> None:
    """Dernier appel par clé d'API (en mémoire : aucun contenu, seulement le nom de la clé et l'heure)."""
    if principal.kind == "api_key":
        _CLIENTS[principal.name] = datetime.now(timezone.utc).isoformat(timespec="minutes")


def tracked(*scopes: str):
    """Comme `require`, et note le dernier appel de chaque clé d'API (état du système : JobAgent vu ou non)."""
    base = require(*scopes)

    def dep(principal: Principal = base) -> Principal:
        seen(principal)
        return principal

    return Depends(dep)


# ── Lecture des entrées (JSON ou multipart) ─────────────────────────────────────────────────────
async def read_input(request: Request) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
    """(champs texte, fichiers {nom_du_champ: (nom_de_fichier, octets, type)})."""
    ctype = request.headers.get("content-type", "")
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes, str]] = {}
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        for key, value in form.multi_items():
            if hasattr(value, "read"):
                data = await value.read(MAX_UPLOAD + 1)
                if len(data) > MAX_UPLOAD:
                    raise _err(413, "too_large", "Fichier trop lourd (8 Mo maximum).")
                files[key] = (value.filename or "", data, value.content_type or "")
            else:
                fields[key] = str(value)
        return fields, files
    raw = await request.body()
    if not raw:
        return fields, files
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise _err(422, "bad_json", "Corps JSON invalide.") from exc
    if not isinstance(body, dict):
        raise _err(422, "bad_json", "Un objet JSON est attendu.")
    for key, value in body.items():
        if key.endswith("_b64") and isinstance(value, str):
            try:
                data = base64.b64decode(value, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise _err(422, "bad_file", f"{key} : base64 invalide.") from exc
            if len(data) > MAX_UPLOAD:
                raise _err(413, "too_large", "Fichier trop lourd (8 Mo maximum).")
            stem = key[: -len("_b64")]
            files[stem] = (str(body.get(f"{stem.removesuffix('_file')}_filename") or body.get("filename") or ""), data, "")
        elif isinstance(value, (str, int, float, bool)):
            fields[key] = str(value)
    return fields, files


def offer_from_inputs(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]], *, required: bool = True) -> Offer | None:
    """Type détecté → récupération → extraction → normalisation. Priorité : fichier, texte, URL."""
    title = fields.get("title") or fields.get("role") or fields.get("job_title") or ""
    company = fields.get("company", "")
    f = files.get("offer_file") or files.get("file")
    text_in = fields.get("offer_text") or fields.get("text") or ""
    url = fields.get("offer_url") or fields.get("url") or ""
    try:
        if f:
            return offer_from_file(f[0], f[1], f[2], title=title, company=company)
        if text_in.strip():
            return offer_from_text(text_in, title=title, company=company, source_url=url)
        if url.strip():
            return offer_from_url(url.strip())
    except UrlIngestError as exc:
        raise _err(422, exc.code, exc.message) from exc
    except IngestError as exc:
        raise _err(422, "unreadable", str(exc)) from exc
    if required:
        raise _err(422, "missing_offer", "Offre manquante : texte (offer_text), lien (offer_url) ou fichier (offer_file).")
    return None


def _offer_view(offer: Offer) -> dict[str, Any]:
    return offer.model_dump(include=set(OFFER_FIELDS)) | {"chars": len(offer.text)}


def _profile_or_none():
    from ..db.repo import load_current_profile

    try:
        with session_scope() as s:
            return load_current_profile(s)
    except FileNotFoundError:
        return None


# ── Cache de résultats (analyse d'offre) ────────────────────────────────────────────────────────
def _cache_path(namespace: str, key: str) -> Path:
    return paths.DATA_DIR / "cache" / "results" / f"{namespace}-{key}.json"


def cache_get(namespace: str, key: str) -> Any | None:
    try:
        p = _cache_path(namespace, key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None  # cache indisponible ou illisible : on recalcule


def cache_put(namespace: str, key: str, value: Any) -> None:
    try:
        p = _cache_path(namespace, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
    except OSError:
        pass


# ── Santé ───────────────────────────────────────────────────────────────────────────────────────
@router.get("/health")
def health() -> dict[str, Any]:
    """Vivant (sans authentification, sans détail interne)."""
    return {"status": "ok", "engine_v": ENGINE_VERSION, "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _migration_state() -> dict[str, Any]:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        head = ScriptDirectory.from_config(Config(str(paths.ROOT / "alembic.ini"))).get_current_head()
    except Exception:  # noqa: BLE001 — image sans alembic.ini : on n'invente pas d'état
        return {"status": "WARNING", "detail": "migrations non vérifiables"}
    try:
        with session_scope() as s:
            current = s.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 — base créée sans Alembic (développement, tests)
        current = None
    if current is None:
        return {"status": "WARNING", "detail": f"schéma créé sans Alembic (tête attendue {head})"}
    return {"status": "OK" if current == head else "ERROR", "detail": f"révision {current} / tête {head}"}


def readiness() -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    try:
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        checks["database"] = {"status": "OK", "detail": "requête de test réussie"}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"status": "ERROR", "detail": exc.__class__.__name__}
    checks["migrations"] = _migration_state() if checks["database"]["status"] == "OK" else {"status": "ERROR", "detail": "base injoignable"}
    try:
        probe = paths.DATA_DIR / "cache" / ".ready"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(str(time.time()), encoding="utf-8")
        checks["storage"] = {"status": "OK", "detail": "écriture possible dans le dossier de données"}
    except OSError as exc:
        checks["storage"] = {"status": "ERROR", "detail": exc.__class__.__name__}
    active, mode = settings_ai.ai_status()
    checks["ai"] = {"status": "OK" if mode != "DEGRADED" or active == "null" else "WARNING",
                    "detail": {"REMOTE": "IA externe", "LOCAL": "IA locale", "DEGRADED": "sans IA (voies déterministes)"}[mode],
                    "provider": active, "mode": mode}
    cfg = get_settings()
    prod = cfg.environment == "production"
    ok_secret = bool(cfg.secret_key) or not prod
    checks["config"] = {"status": "OK" if ok_secret else "ERROR",
                        "detail": "configuration complète" if ok_secret else "SECRET_KEY manquante en production"}
    ready = all(checks[k]["status"] != "ERROR" for k in ("database", "migrations", "storage", "config"))
    return {"ready": ready, "checks": checks}


@router.get("/ready")
def ready() -> JSONResponse:
    """Prêt à servir : base, migrations, stockage, configuration (l'IA n'est jamais bloquante)."""
    r = readiness()
    return JSONResponse(r, status_code=200 if r["ready"] else 503)


# ── Offres ──────────────────────────────────────────────────────────────────────────────────────
@router.post("/jobs/ingest")
async def jobs_ingest(request: Request, _: Principal = tracked("analyze")) -> dict[str, Any]:
    """Lit une offre (texte, URL, PDF, HTML, DOCX) côté serveur. Rien n'est enregistré."""
    fields, files = await read_input(request)
    offer = await run_in_threadpool(offer_from_inputs, fields, files)
    return {"offer": _offer_view(offer)}


def _analysis_key(offer: Offer, profile_tag: str, ai_mode: str) -> str:
    from ..rules import load_rules

    return stable_hash([offer.text_hash, offer.title_hint, offer.company_hint, profile_tag, load_rules().version, ENGINE_VERSION,
                        ai_mode], 20)


def analyze_offer_sync(offer: Offer, use_ai: bool) -> dict[str, Any]:
    from ..analyzer import deterministic_analysis
    from ..ats import requirements as rq
    from ..pipeline import Pipeline
    from ..profile import profile_version_tag
    from ..providers import get_provider
    from ..providers.null import NullProvider

    profile = _profile_or_none()
    provider = get_provider() if use_ai else NullProvider()
    ai_mode = provider.mode() if hasattr(provider, "mode") else ("DEGRADED" if not provider.available else "AI")
    key = _analysis_key(offer, profile_version_tag(profile) if profile else "-", f"{ai_mode}:{provider.name}")
    cached = cache_get("analysis", key)
    if cached is not None:
        obs.event("cache", stage="analysis", cache_hit=True)
        return cached | {"cache": "hit"}
    obs.event("cache", stage="analysis", cache_hit=False)
    if profile is None:
        analysis = deterministic_analysis(offer)
        reqs = rq.extract(analysis, offer.text)
        out = {"offer": _offer_view(offer), "analysis": analysis.model_dump(), "report": None,
               "requirements": [r.as_dict() for r in reqs], "provider": "null",
               "note": "Aucun profil : exigences classées, preuves non évaluées (importez un profil ou analysez un CV)."}
    else:
        pipe = Pipeline(profile, provider, mode="QUICK", render_pdf=False)
        analysis = pipe.analyze(offer)
        match = pipe.match(analysis)
        report = pipe.ats_report(offer, analysis, match)
        with session_scope() as s:
            record_calls(s, provider.calls)
        out = {"offer": _offer_view(offer), "analysis": analysis.model_dump(), "report": report, "provider": provider.name}
    cache_put("analysis", key, out)
    return out | {"cache": "miss"}


@router.post("/jobs/analyze")
async def jobs_analyze(request: Request, _: Principal = tracked("analyze")) -> dict[str, Any]:
    """Analyse d'offre + (si un profil existe) exigences prouvées et Score PAI provisoire. `ai=none` : jamais d'IA.
    Même offre + même profil + mêmes règles et modèle → résultat en cache (« cache »: « hit »)."""
    fields, files = await read_input(request)
    offer = await run_in_threadpool(offer_from_inputs, fields, files)
    return await run_in_threadpool(analyze_offer_sync, offer, fields.get("ai", "auto") != "none")


# ── CV ──────────────────────────────────────────────────────────────────────────────────────────
def _cv_input(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[str, bytes | None]:
    from ..ats.cvimport import CvImportError, cv_text_from_file

    f = files.get("cv_file") or files.get("cv")
    if f:
        try:
            return cv_text_from_file(f[0], f[1], f[2])
        except CvImportError as exc:
            raise _err(422, exc.code, exc.message) from exc
    t = fields.get("cv_text", "")
    if len(t.strip()) >= 80:
        return t, None
    raise _err(422, "missing_cv", "CV manquant : fichier (cv_file : PDF, DOCX, texte) ou texte (cv_text, 80 caractères minimum).")


def cv_analyze_sync(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> dict[str, Any]:
    from ..analyzer import deterministic_analysis
    from ..ats import cv_report, match_report
    from ..ats.cvimport import profile_from_cv
    from ..ats.parser import parse_cv_text
    from ..ats.scanner import scan_pdf
    from ..matching import compute_match

    text, pdf = _cv_input(fields, files)
    offer = offer_from_inputs(fields, {k: v for k, v in files.items() if k in ("offer_file",)}, required=False)
    if offer is None:
        return {"mode": "cv_only", "report": cv_report(text=None if pdf else text, pdf=pdf)}
    parsed = parse_cv_text(text)
    profile = profile_from_cv(parsed)
    analysis = deterministic_analysis(offer)
    match = compute_match(profile, analysis)
    scan = scan_pdf(pdf) if pdf else None
    report = match_report(profile, analysis, match, offer.text, cv_text=text, scan=scan)
    report["source"] = "Preuves tirées du CV fourni (aucun profil PAI utilisé)."
    return {"mode": "cv_offer", "offer": _offer_view(offer), "report": report}


@router.post("/cv/analyze")
async def cv_analyze(request: Request, _: Principal = tracked("analyze")) -> dict[str, Any]:
    """Mode A (CV seul) ou mode B (CV + offre). Le CV peut être un PDF, un DOCX ou du texte."""
    fields, files = await read_input(request)
    return await run_in_threadpool(cv_analyze_sync, fields, files)


def cv_validate_sync(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> dict[str, Any]:
    from ..ats.scanner import scan_pdf

    f = files.get("cv_file") or files.get("file")
    if not f or f[1][:5] != b"%PDF-":
        raise _err(422, "missing_pdf", "PDF manquant (cv_file).")
    source = [ln.strip() for ln in fields.get("source_text", "").splitlines() if ln.strip()]
    report = scan_pdf(f[1], max_pages=int(fields.get("max_pages", 2) or 2), source_lines=source or None)
    report["parsed"] = {k: report["parsed"][k] for k in ("order", "dates") if k in report["parsed"]} | {
        "experiences": len(report["parsed"].get("experiences", [])), "email_found": bool(report["parsed"].get("email")),
        "phone_found": bool(report["parsed"].get("phone"))}
    return {"report": report}


@router.post("/cv/validate")
async def cv_validate(request: Request, _: Principal = tracked("analyze")) -> dict[str, Any]:
    """Scanner ATS d'un PDF : OK / WARNING / ERROR par contrôle ; avec `source_text`, relecture « rien de perdu »."""
    fields, files = await read_input(request)
    return await run_in_threadpool(cv_validate_sync, fields, files)


def cv_optimize_sync(offer: Offer, use_ai: bool) -> dict[str, Any]:
    from ..pipeline import Pipeline
    from ..providers import get_provider
    from ..providers.null import NullProvider

    profile = _profile_or_none()
    if profile is None:
        raise _err(409, "no_profile", "Aucun profil : importez-le (onglet Profil) pour optimiser un CV.")
    provider = get_provider() if use_ai else NullProvider()
    pipe = Pipeline(profile, provider, mode="STANDARD", render_pdf=False)
    analysis = pipe.analyze(offer)
    match = pipe.match(analysis)
    strategy = pipe.strategy(analysis, match)
    cv, validation, _extra = pipe.build_cv(offer, analysis, match, strategy)
    report = pipe.ats_report(offer, analysis, match, cv=cv, validation=validation)
    with session_scope() as s:
        record_calls(s, provider.calls)
    return {"offer": _offer_view(offer), "strategy": strategy.best.model_dump(), "cv": cv.model_dump(include={"name", "lines", "experiences", "section_titles", "design_profile"}),
            "validation": {"factuality": validation.factuality, "traced": validation.traced, "total": validation.total},
            "changes": report.pop("changes", {}), "report": report, "provider": provider.name}


@router.post("/cv/optimize")
async def cv_optimize(request: Request, _: Principal = tracked("analyze")) -> dict[str, Any]:
    """CV ciblé (lignes tracées vers les faits), changements AVANT / APRÈS / RAISON / PREUVE, Score PAI (sans PDF)."""
    fields, files = await read_input(request)
    offer = await run_in_threadpool(offer_from_inputs, fields, files)
    return await run_in_threadpool(cv_optimize_sync, offer, fields.get("ai", "auto") != "none")


# ── Génération synchrone et pack ───────────────────────────────────────────────────────────────
def _pack_payload(fields: dict[str, str], offer: Offer) -> dict[str, Any]:
    return {"offer_text": offer.text, "offer_url": offer.source_url, "role": offer.title_hint, "company": offer.company_hint,
            "mode": fields.get("mode", "STANDARD") if fields.get("mode") in ("STANDARD", "DEEP") else "STANDARD",
            "questions": fields.get("questions", "")[:20000], "source": fields.get("source", "api")[:40],
            "candidate_id": fields.get("candidate_id", "")[:80], "offer_id": fields.get("offer_id", "")[:80]}


def pack_result(r: dict[str, Any]) -> dict[str, Any]:
    """Réponse commune (CV, lettre, pack) : identifiants de version, Score PAI, fichiers signés."""
    return {"application_id": r["versions"].get("application_id", ""), "version_id": r["generation_id"]} | r


def _generate_sync(fields: dict[str, str], offer: Offer) -> dict[str, Any]:
    from .v1 import run_pack_job

    return pack_result(run_pack_job(_pack_payload(fields, offer)))


@router.post("/cv/generate")
async def cv_generate(request: Request, _: Principal = tracked("generate")) -> dict[str, Any]:
    """Synchrone : CV + lettre (même version), PDF relus par le scanner ATS, Score PAI complet."""
    fields, files = await read_input(request)
    offer = await run_in_threadpool(offer_from_inputs, fields, files)
    r = await run_in_threadpool(_generate_sync, fields, offer)
    return {k: r[k] for k in ("application_id", "version_id", "generation_id", "status", "cv_version", "pai_score", "ats",
                              "risks", "next_action", "versions")} | {"cv_pdf": r["application_pack"]["cv_pdf"]}


@router.post("/letter/generate")
async def letter_generate(request: Request, _: Principal = tracked("generate")) -> dict[str, Any]:
    fields, files = await read_input(request)
    offer = await run_in_threadpool(offer_from_inputs, fields, files)
    r = await run_in_threadpool(_generate_sync, fields, offer)
    return {k: r[k] for k in ("application_id", "version_id", "generation_id", "status", "letter_version", "risks",
                              "next_action", "versions")} | {"letter_pdf": r["application_pack"]["letter_pdf"]}


@router.post("/application/prepare")
async def application_prepare(request: Request, _: Principal = tracked("generate")) -> Any:
    """Pack complet. Par défaut asynchrone (202 + job_id, à suivre sur /api/jobs/{job_id}) ; `wait=true` : synchrone.
    En-tête Idempotency-Key : même clé → même job, jamais de doublon."""
    fields, files = await read_input(request)
    offer = await run_in_threadpool(offer_from_inputs, fields, files)
    payload = _pack_payload(fields, offer)
    if (request.query_params.get("wait") or fields.get("wait", "")).lower() in ("1", "true", "yes"):
        return await run_in_threadpool(_generate_sync, fields, offer)
    job = jobs.enqueue("generate_pack", payload, request.headers.get("idempotency-key"))
    return JSONResponse({"job_id": job.id, "status": job.status, "poll": f"/api/jobs/{job.id}"}, status_code=202)


@router.get("/jobs/{job_id}")
def job_status(job_id: str, _: Principal = tracked("read")) -> dict[str, Any]:
    job = jobs.get_job(job_id)
    if job is None:
        raise _err(404, "not_found", "Job inconnu.")
    result = pack_result(job.result) if job.type == "generate_pack" and job.result else job.result
    return {"job_id": job.id, "type": job.type, "status": job.status, "progress": job.progress, "result": result,
            "error": (job.error or "").split("\n")[0][:300] or None}


@router.get("/application/{app_or_version_id}")
def application(app_or_version_id: str, _: Principal = tracked("read")) -> dict[str, Any]:
    """Une version (pack_…) ou une candidature (app_… : toutes ses versions, la plus récente d'abord)."""
    from .v1 import file_url

    with session_scope() as s:
        if app_or_version_id.startswith("app_"):
            gens = [g for g in s.scalars(select(Generation).where(Generation.deleted_at.is_(None)).order_by(Generation.created_at.desc()))
                    if (g.versions or {}).get("application_id") == app_or_version_id]
        else:
            g = s.get(Generation, app_or_version_id)
            gens = [g] if g is not None and g.deleted_at is None else []
        if not gens:
            raise _err(404, "not_found", "Candidature ou version inconnue.")
        out = []
        for g in gens:
            apk = s.scalar(select(ApplicationPackRow).where(ApplicationPackRow.generation_id == g.id))
            files = {name: file_url(fid) for fid, name in s.execute(select(StoredFile.id, StoredFile.name)
                                                                   .where(StoredFile.generation_id == g.id))}
            offer = s.get(OfferRow, g.offer_id)
            out.append({"version_id": g.id, "application_id": (g.versions or {}).get("application_id", ""), "status": g.status,
                        "created_at": g.created_at.isoformat(), "mode": g.mode, "provider": g.provider, "versions": g.versions,
                        "pai_score": (g.scores or {}).get("pai_score"), "ats": (apk.manifest or {}).get("ats", {}) if apk else {},
                        "risks": g.risks, "next_action": g.next_action, "files": files,
                        "zip": file_url(apk.zip_file_id) if apk else None,
                        "offer": {"title": offer.title_hint, "company": offer.company_hint, "source_url": offer.source_url} if offer else {}})
    return {"application_id": out[0]["application_id"], "latest": out[0], "versions": out}


# ── Corpus, état du système, usage de l'IA ─────────────────────────────────────────────────────
@router.get("/corpus")
def corpus_view(_: Principal = tracked("read")) -> dict[str, Any]:
    from ..ats.corpus import from_db

    return from_db()


def system_status() -> dict[str, Any]:
    """PAI, ATS, API, base, IA, modèle local, cache, Cloudflare, JobAgent → OK / WARNING / ERROR, avec une phrase."""
    from ..ai.hardware import detect
    from ..providers import active_provider_id, build_router
    from ..providers.ollama import load_selection, probe
    from ..providers.store import read_stored_settings

    items: list[dict[str, Any]] = []

    def add(key: str, label: str, status: str, detail: str) -> None:
        items.append({"id": key, "label": label, "status": status, "detail": detail})

    add("pai", "PAI", "OK", f"moteur {ENGINE_VERSION}")
    try:
        from ..ats import classify_requirement

        ok = classify_requirement("Anglais courant requis") == "MUST"
        add("ats", "Moteur ATS", "OK" if ok else "ERROR", "règles chargées, contrôle de cohérence réussi" if ok else "contrôle échoué")
    except Exception as exc:  # noqa: BLE001
        add("ats", "Moteur ATS", "ERROR", exc.__class__.__name__)
    add("api", "API", "OK", "répond (cette page en vient)")
    r = readiness()
    db = r["checks"]["database"]
    add("database", "Base de données", db["status"], f"{'PostgreSQL' if get_settings().db_url.startswith('postgres') else 'SQLite'} — "
        f"{db['detail']} ; migrations : {r['checks']['migrations']['detail']}")
    settings, stored = get_settings(), read_stored_settings()
    active = active_provider_id(settings, stored)
    rt = build_router(active, settings, stored)
    mode = rt.mode()
    add("ai", "IA", "OK" if mode != "DEGRADED" or active == "null" else "WARNING",
        {"REMOTE": f"IA externe ({active}) — optionnelle", "LOCAL": "IA locale (gratuite)",
         "DEGRADED": "sans IA : tout fonctionne par les voies déterministes"}[mode])
    base = settings.ollama_base_url or settings.local_base_url
    from ..providers.ollama import normalize_base_url

    state = probe(normalize_base_url(base))
    sel = load_selection()
    if state.get("reachable"):
        names = [m["name"] for m in state.get("models", [])]
        add("local_model", "Modèle local", "OK" if names else "WARNING",
            f"Ollama {state.get('version', '')} : {len(names)} modèle(s)" + (f" · choix mesuré : {sel.get('large', '?')} / {sel.get('small', '?')}" if sel else "")
            if names else "Ollama répond mais aucun modèle n'est installé (python -m pai ai setup --pull)")
    else:
        add("local_model", "Modèle local", "WARNING", "Ollama injoignable : PAI reste utilisable sans IA")
    try:
        cache_dir = paths.DATA_DIR / "cache"
        n = sum(1 for _ in cache_dir.glob("*.json")) + sum(1 for _ in (cache_dir / "results").glob("*.json")) if cache_dir.exists() else 0
        add("cache", "Cache", "OK", f"{n} réponse(s) en cache")
    except OSError:
        add("cache", "Cache", "WARNING", "cache illisible : PAI continue sans cache")
    base_url = settings.base_url
    https = base_url.startswith("https://") and "localhost" not in base_url
    via = {"cloudflare": "via Cloudflare Tunnel", "caddy": "via Caddy", "tailscale": "via Tailscale"}.get(settings.pai_access, "")
    add("cloudflare", "Accès public (Cloudflare)", "OK" if https else "WARNING",
        f"{base_url} {via}".strip() if https else "pas d'adresse publique HTTPS (BASE_URL) : accès local uniquement")
    jobagent = _jobagent_seen()
    add("jobagent", "JobAgent", "OK" if jobagent else "WARNING",
        f"dernier appel de JobAgent : {jobagent}" if jobagent else "aucun appel de JobAgent pour l'instant (PAI reste utilisable seul)")
    hw = detect()
    worst = "ERROR" if any(i["status"] == "ERROR" for i in items) else "WARNING" if any(i["status"] == "WARNING" for i in items) else "OK"
    return {"status": worst, "items": items, "machine": {"arch": hw.arch, "cpus": hw.cpus, "ram_gb": hw.ram_total_gb,
                                                        "gpu": bool(hw.gpus)}}


def _jobagent_seen() -> str:
    for name, at in _CLIENTS.items():
        if "jobagent" in name.lower():
            return at
    with session_scope() as s:
        for job in s.scalars(select(Job).order_by(Job.created_at.desc()).limit(200)):
            if str((job.payload or {}).get("source", "")).lower() == "jobagent":
                return job.created_at.isoformat(timespec="minutes")
    return ""


@router.get("/system/status")
def system_status_view(_: Principal = tracked("read")) -> dict[str, Any]:
    return system_status()


@router.get("/ai/usage")
def ai_usage(days: int = 30, _: Principal = tracked("read")) -> dict[str, Any]:
    """Qui consomme quoi : appels par fournisseur / modèle / niveau, cache (hit / miss), jetons, temps, coût."""
    since = datetime.now(timezone.utc).timestamp() - max(1, min(days, 365)) * 86400
    since_dt = datetime.fromtimestamp(since, tz=timezone.utc)
    with session_scope() as s:
        rows = s.execute(select(LlmCall.provider, LlmCall.model, LlmCall.tier, LlmCall.task, LlmCall.cached,
                                func.count(), func.sum(LlmCall.tokens_in), func.sum(LlmCall.tokens_out),
                                func.sum(LlmCall.latency_ms), func.sum(LlmCall.cost_eur),
                                func.sum(case((LlmCall.ok.is_(False), 1), else_=0)))
                         .where(LlmCall.created_at >= since_dt)
                         .group_by(LlmCall.provider, LlmCall.model, LlmCall.tier, LlmCall.task, LlmCall.cached)).all()
    by: dict[tuple[str, str, str], dict[str, Any]] = {}
    tasks: dict[str, dict[str, int]] = {}
    for provider, model, tier, task, cached, n, tin, tout, lat, cost, errors in rows:
        k = (provider, model, tier or "")
        e = by.setdefault(k, {"provider": provider, "model": model, "tier": tier or "", "requests": 0, "cache_hit": 0,
                               "cache_miss": 0, "tokens_in": 0, "tokens_out": 0, "time_ms": 0, "cost_eur": 0.0, "errors": 0})
        e["requests"] += n
        e["cache_hit" if cached else "cache_miss"] += n
        e["tokens_in"] += int(tin or 0)
        e["tokens_out"] += int(tout or 0)
        e["time_ms"] += int(lat or 0)
        e["cost_eur"] = round(e["cost_eur"] + float(cost or 0), 4)
        e["errors"] += int(errors or 0)
        t = tasks.setdefault(task, {"requests": 0, "cache_hit": 0})
        t["requests"] += n
        t["cache_hit"] += n if cached else 0
    total = sum(e["requests"] for e in by.values())
    hits = sum(e["cache_hit"] for e in by.values())
    return {"days": days, "total_requests": total, "cache_hit": hits, "cache_miss": total - hits,
            "cache_hit_rate": round(100 * hits / total) if total else None,
            "cost_eur": round(sum(e["cost_eur"] for e in by.values()), 4),
            "by_model": sorted(by.values(), key=lambda e: -e["requests"]), "by_task": tasks,
            "note": "Les tâches déterministes (matching, factualité, score, PDF) n'appellent jamais l'IA : elles n'apparaissent pas ici."}
