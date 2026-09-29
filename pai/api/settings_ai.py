"""Réglages IA depuis l'interface : fournisseur actif, clés chiffrées au repos, modèle, URL, test de connexion.

GET /v1/settings/ai (read) · PUT /v1/settings/ai (admin) · POST /v1/settings/ai/test (admin). Routeur inclus
dans celui de /v1 (mêmes dépendances d'authentification, CSRF pour les sessions). Aucune clé n'est jamais renvoyée
ni journalisée : seulement un indice (••••a1b2) ; chaque modification est tracée dans audit_log, sans secret.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db.models import AuditLog
from ..db.repo import record_calls
from ..db.session import session_scope
from ..providers import LABELS, PROVIDER_IDS, active_provider_id, ai_mode, build_from_config, provider_config
from ..providers.base import ProviderError
from ..providers.store import (StoredAiSettings, decode_settings, encrypt_secret, key_hint, load_settings_value,
                               read_stored_settings, save_settings_value)
from .auth import Principal, require

router = APIRouter(tags=["v1"])
KEYED_IDS = frozenset({"claude", "gemini", "mistral", "openai"})
BASE_URL_IDS = frozenset({"openai", "local"})
TEST_PROMPT = "Réponds uniquement par OK."
MISSING = {"openai": "Clé ou modèle manquant (OPENAI_API_KEY / OPENAI_MODEL, ou Réglages → IA).",
           "local": "Modèle local manquant (LOCAL_MODEL, ou Réglages → IA)."}
_API_KEY = re.compile(r"^[\x21-\x7e]{8,400}$")               # ASCII imprimable, sans espace ni caractère de contrôle
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,79}$")  # 80 caractères max (colonne llm_calls.model)


def _invalid(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": "invalid_argument", "message": message})


def _provider_id(value: str, name: str) -> str:
    pid = value.strip().lower()
    if pid not in PROVIDER_IDS:
        raise _invalid(f"« {name} » inconnu : valeurs possibles {', '.join(PROVIDER_IDS)}.")
    return pid


def _base_url(value: str) -> str:
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL as exc:
        raise _invalid("« base_url » invalide.") from exc
    if url.scheme not in ("http", "https") or not url.host or url.userinfo or url.query or url.fragment:
        raise _invalid("« base_url » doit être une URL http(s) sans identifiants ni paramètres (ex. http://ollama:11434/v1).")
    return str(url).rstrip("/")


def _entry_set(entry: dict[str, Any], key: str, value: str) -> None:
    if value:
        entry[key] = value
    else:
        entry.pop(key, None)  # vide = retour à l'environnement / au défaut


def _configured(pid: str, provider: Any) -> bool:
    return pid == "null" or bool(provider.available)


def describe(stored: StoredAiSettings | None = None) -> dict[str, Any]:
    """État des réglages IA pour l'interface, sans aucun secret (indice de clé seulement)."""
    settings = get_settings()
    stored = read_stored_settings() if stored is None else stored
    active = active_provider_id(settings, stored)
    providers = []
    for pid in PROVIDER_IDS:
        cfg = provider_config(pid, settings, stored)
        built = build_from_config(cfg)
        providers.append({"id": pid, "label": LABELS[pid], "configured": _configured(pid, built),
                          "key_hint": key_hint(cfg.api_key), "model": "" if pid == "null" else built.model_for("cv_content"),
                          "base_url": cfg.base_url, "source": cfg.source})
    configured = next(p["configured"] for p in providers if p["id"] == active)
    return {"active": active, "mode": ai_mode(active, configured), "providers": providers}


def ai_status() -> tuple[str, str]:
    """(fournisseur actif, mode IA : REMOTE | LOCAL | DEGRADED)."""
    settings, stored = get_settings(), read_stored_settings()
    active = active_provider_id(settings, stored)
    return active, ai_mode(active, _configured(active, build_from_config(provider_config(active, settings, stored))))


@router.get("/settings/ai")
def get_ai_settings(_: Principal = require("read")) -> dict[str, Any]:
    return describe()


class AiSettingsIn(BaseModel):
    """Champs absents = inchangés. `model` / `base_url` vides = retour à l'environnement. `api_key` vide = inchangée."""

    active: str | None = Field(None, max_length=20)
    provider: str | None = Field(None, max_length=20)
    api_key: str | None = None  # longueur contrôlée par _API_KEY : une erreur de validation FastAPI recopierait la clé
    model: str | None = Field(None, max_length=200)
    base_url: str | None = Field(None, max_length=500)
    clear_key: bool = False

    model_config = {"extra": "forbid"}


@router.put("/settings/ai")
def put_ai_settings(body: AiSettingsIn, principal: Principal = require("admin")) -> dict[str, Any]:
    """Change le fournisseur actif et/ou les réglages d'un fournisseur. Changer `base_url` efface la clé enregistrée
    de ce fournisseur (à ressaisir dans la même requête) : une clé ne part jamais vers une URL qu'elle ne visait pas."""
    active = _provider_id(body.active, "active") if body.active is not None else None
    pid = _provider_id(body.provider, "provider") if body.provider is not None else None
    api_key = (body.api_key or "").strip()
    model = body.model.strip() if body.model is not None else None
    base_url = body.base_url.strip() if body.base_url is not None else None
    touches = bool(api_key) or body.clear_key or model is not None or base_url is not None
    if touches and pid is None:
        raise _invalid("Précisez « provider » pour modifier une clé, un modèle ou une URL.")
    if touches and pid == "null":
        raise _invalid("« null » (Désactivé) n'a aucun réglage.")
    if (api_key or body.clear_key) and pid not in KEYED_IDS:
        raise _invalid("Ce fournisseur n'utilise pas de clé d'API.")
    if api_key and body.clear_key:
        raise _invalid("« api_key » et « clear_key » sont incompatibles.")
    if api_key and not _API_KEY.match(api_key):
        raise _invalid("Clé d'API invalide (8 à 400 caractères imprimables, sans espace).")
    if model and not _MODEL.match(model):
        raise _invalid("Nom de modèle invalide (80 caractères max : lettres, chiffres, . _ : / @ + -).")
    if base_url is not None:
        if pid not in BASE_URL_IDS:
            raise _invalid("« base_url » n'est réglable que pour openai et local.")
        base_url = _base_url(base_url) if base_url else ""
    changed: list[str] = []
    with session_scope() as s:
        value = load_settings_value(s, lock=True)
        if active is not None and value.get("active") != active:
            value["active"] = active
            changed.append("active")
        if pid is not None and touches:
            providers = value.setdefault("providers", {})
            entry = providers.setdefault(pid, {})
            if base_url is not None and base_url != entry.get("base_url", ""):
                _entry_set(entry, "base_url", base_url)
                changed.append("base_url")
                if entry.pop("key", None) and not api_key:
                    changed.append("key_cleared")
            if model is not None and model != entry.get("model", ""):
                _entry_set(entry, "model", model)
                changed.append("model")
            if body.clear_key and entry.pop("key", None):
                changed.append("key_cleared")
            if api_key:
                entry["key"] = encrypt_secret(api_key)
                changed.append("api_key")
            if not entry:
                providers.pop(pid)
        if changed:
            save_settings_value(s, value)
            s.add(AuditLog(actor=principal.name, action="update_ai_settings", target=pid or active or "",
                           detail={"active": value.get("active", ""), "provider": pid or "", "changed": changed}))
        stored = decode_settings(value)
    return describe(stored)


class AiTestIn(BaseModel):
    provider: str = Field(max_length=20)

    model_config = {"extra": "forbid"}


def _redact(text: str, secret: str) -> str:
    return (text.replace(secret, "••••") if secret else text)[:200]


@router.post("/settings/ai/test")
def test_ai_settings(body: AiTestIn, _: Principal = require("admin")) -> dict[str, Any]:
    """Petit appel réel (tâche extract) avec les réglages enregistrés, hors cache et hors plafond de coût, journalisé
    comme les autres appels IA. Une erreur du fournisseur donne ok=false, jamais une erreur 500."""
    pid = _provider_id(body.provider, "provider")
    if pid == "null":
        return {"ok": False, "latency_ms": 0, "model": "", "error": "Fournisseur désactivé : aucun appel IA."}
    cfg = provider_config(pid, get_settings(), read_stored_settings())
    provider = build_from_config(cfg)
    model = provider.model_for("extract")
    if not provider.available:
        return {"ok": False, "latency_ms": 0, "model": model,
                "error": MISSING.get(pid, "Clé d'API manquante : saisissez-la dans Réglages → IA.")}
    start = time.monotonic()
    error: str | None = None
    try:
        model = provider.complete("extract", TEST_PROMPT, prompt_tag="settings:test").model or model
    except ProviderError as exc:
        error = _redact(str(exc), cfg.api_key) or "Échec de l'appel IA."
    except Exception as exc:  # noqa: BLE001 — un test de connexion ne renvoie jamais d'erreur 500
        error = f"Erreur inattendue ({exc.__class__.__name__})."
    latency_ms = int((time.monotonic() - start) * 1000)
    for call in provider.calls:
        call.error = _redact(call.error, cfg.api_key)
    with session_scope() as s:
        record_calls(s, provider.calls)
    return {"ok": error is None, "latency_ms": latency_ms, "model": model, "error": error}
