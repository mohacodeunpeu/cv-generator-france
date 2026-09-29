"""Sélection du fournisseur IA, interchangeable : local (Ollama) | claude | gemini | mistral | openai | null (sans IA).

Ordre de résolution : réglages enregistrés (Réglages → IA : fournisseur actif, clé chiffrée, modèle, URL) →
environnement (AI_PROVIDER, ou l'ancien PAI_AI_PROVIDER ; AI_MODEL, AI_BASE_URL, AI_API_KEY) → config/models.yaml
(`default_provider: local`) → null. Valeurs acceptées aussi : none (= null), anthropic (= claude),
openai_compatible (= openai avec AI_BASE_URL), ollama (= local). Base indisponible → environnement, sans erreur.
Aucun module métier n'importe de SDK de fournisseur ; le routeur (pai.ai.router) choisit, tâche par tâche,
entre aucune IA, petit modèle local, grand modèle local et fournisseur externe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from ..config import Settings, get_settings
from ..rules import load_rules
from .base import AIProvider, BudgetExceeded, DegradedMode, ProviderError, extract_json
from .cache import CachedProvider
from .claude import ClaudeProvider
from .null import NullProvider
from .ollama import OllamaProvider, normalize_base_url, probe
from .openai_compat import (GEMINI_BASE_URL, MISTRAL_BASE_URL, OpenAICompatProvider, gemini_provider, mistral_provider,
                            openai_provider)
from .store import StoredAiSettings, read_stored_settings

__all__ = ["AIProvider", "BudgetExceeded", "CachedProvider", "ClaudeProvider", "DegradedMode", "LABELS", "NullProvider",
           "OllamaProvider", "OpenAICompatProvider", "PROVIDER_IDS", "ProviderConfig", "ProviderError", "active_profile",
           "active_provider_id", "ai_mode", "build_from_config", "build_provider", "build_router", "extract_json",
           "get_provider", "normalize_provider_id", "provider_config"]

PROVIDER_IDS = ("local", "claude", "gemini", "mistral", "openai", "null")
LABELS = {"local": "IA locale (Ollama)", "claude": "Claude (Anthropic)", "gemini": "Gemini", "mistral": "Mistral",
          "openai": "OpenAI / compatible", "null": "Sans IA"}
REMOTE_IDS = frozenset({"claude", "gemini", "mistral", "openai"})
ALIASES = {"none": "null", "off": "null", "sans_ia": "null", "anthropic": "claude", "openai_compatible": "openai",
           "openai-compatible": "openai", "ollama": "local"}


def normalize_provider_id(value: str) -> str:
    """Identifiant canonique ('' si vide, 'null' si inconnu)."""
    v = (value or "").strip().lower()
    if not v:
        return ""
    v = ALIASES.get(v, v)
    return v if v in PROVIDER_IDS else "null"


@dataclass
class ProviderConfig:
    """Réglages effectifs d'un fournisseur ; `source` = origine (db | env | none). Clé en mémoire uniquement."""

    id: str
    api_key: str = field(default="", repr=False)
    model: str = ""
    base_url: str = ""
    source: str = "none"
    model_small: str = ""      # local : petit modèle (vide = choix automatique)


def _env_active(settings: Settings) -> str:
    return normalize_provider_id(settings.ai_provider) or normalize_provider_id(settings.pai_ai_provider)


def _env(pid: str, settings: Settings) -> tuple[str, str, str]:
    """(clé, modèle, URL de base) venant de l'environnement. AI_API_KEY / AI_MODEL / AI_BASE_URL s'appliquent au
    fournisseur désigné par AI_PROVIDER et priment sur les variables propres à ce fournisseur."""
    key, model, base = {
        "claude": (settings.anthropic_api_key, "", ""),
        "gemini": (settings.gemini_api_key, settings.gemini_model, GEMINI_BASE_URL),
        "mistral": (settings.mistral_api_key, settings.mistral_model, MISTRAL_BASE_URL),
        "openai": (settings.openai_api_key, settings.openai_model, settings.openai_base_url),
        "local": ("", settings.local_model, settings.ollama_base_url or settings.local_base_url),
    }.get(pid, ("", "", ""))
    if pid and pid == normalize_provider_id(settings.ai_provider):
        key = settings.ai_api_key.strip() or key
        model = settings.ai_model.strip() or model
        base = settings.ai_base_url.strip() or base
    if pid == "local":
        base = normalize_base_url(base)
    return key, model, base


def provider_config(pid: str, settings: Settings | None = None, stored: StoredAiSettings | None = None) -> ProviderConfig:
    """Réglages en base d'abord, puis environnement. La clé de l'environnement n'est jamais envoyée à une URL de base
    changée depuis l'interface (sinon changer l'URL suffirait à exfiltrer la clé)."""
    settings = settings or get_settings()
    if pid not in PROVIDER_IDS or pid == "null":
        return ProviderConfig(id="null")
    db = stored.get(pid) if stored is not None else StoredAiSettings().get(pid)
    env_key, env_model, env_base = _env(pid, settings)
    base_url = db.base_url or env_base
    api_key = db.api_key or (env_key.strip() if base_url == env_base else "")
    if db.api_key or db.model or db.base_url:
        source = "db"
    else:
        source = "env" if env_key.strip() or (pid == "local" and env_model) else ("auto" if pid == "local" else "none")
    small = (getattr(db, "model_small", "") or settings.ai_model_small.strip()) if pid == "local" else ""
    if pid == "local":
        base_url = normalize_base_url(base_url)
    return ProviderConfig(id=pid, api_key=api_key, model=db.model or env_model, base_url=base_url, source=source,
                          model_small=small)


def build_from_config(cfg: ProviderConfig) -> AIProvider:
    if cfg.id == "claude":
        return ClaudeProvider(api_key=cfg.api_key, model=cfg.model)
    if cfg.id == "gemini":
        return gemini_provider(cfg.api_key, cfg.model, cfg.base_url)
    if cfg.id == "mistral":
        return mistral_provider(cfg.api_key, cfg.model, cfg.base_url)
    if cfg.id == "openai":
        return openai_provider(cfg.api_key, cfg.model, cfg.base_url)
    if cfg.id == "local":
        return OllamaProvider(base_url=cfg.base_url, model=cfg.model, tier="large")
    return NullProvider()


def build_provider(name: str, settings: Settings, stored: StoredAiSettings | None = None) -> AIProvider:
    return build_from_config(provider_config((name or "").strip().lower(), settings, stored))


def active_provider_id(settings: Settings | None = None, stored: StoredAiSettings | None = None) -> str:
    """Fournisseur choisi : base → AI_PROVIDER (ou PAI_AI_PROVIDER) → default_provider de config/models.yaml
    (local) → null. Le premier choix renseigné l'emporte ; un identifiant inconnu vaut null."""
    settings = settings or get_settings()
    for candidate in (stored.active if stored is not None else "", _env_active(settings),
                      str(load_rules().models.get("default_provider") or "")):
        chosen = normalize_provider_id(candidate)
        if chosen:
            return chosen
    return "null"


def active_profile(settings: Settings | None = None, stored: StoredAiSettings | None = None) -> str:
    """Profil du routeur : réglage enregistré → AI_PROFILE → config/models.yaml → balanced."""
    from ..ai.router import PROFILES, router_config

    settings = settings or get_settings()
    for candidate in (getattr(stored, "profile", "") if stored is not None else "", settings.ai_profile,
                      str(router_config().get("profile") or "")):
        chosen = (candidate or "").strip().lower()
        if chosen in PROFILES:
            return chosen
    return "balanced"


def ai_mode(pid: str, configured: bool) -> str:
    """REMOTE (fournisseur distant configuré), LOCAL (modèle local configuré), sinon DEGRADED (voies déterministes)."""
    if not configured:
        return "DEGRADED"
    return "REMOTE" if pid in REMOTE_IDS else "LOCAL" if pid == "local" else "DEGRADED"


def _wrap(inner: AIProvider, settings: Settings, cache_dir: Path | None, budget_eur: float | None) -> AIProvider:
    if settings.pai_ai_cache == "off":
        inner.budget_eur = budget_eur
        return inner
    provider = CachedProvider(inner=inner, cache_dir=cache_dir or paths.DATA_DIR / "cache", mode=settings.pai_ai_cache)
    provider.budget_eur = budget_eur
    return provider


def build_router(active: str, settings: Settings, stored: StoredAiSettings | None = None, *, budget_eur: float | None = None,
                 cache_dir: Path | None = None) -> AIProvider:
    """Routeur par tâche. `null` : aucune IA, même si Ollama tourne (choix explicite de l'utilisateur).
    `local` : petit et grand modèles locaux. Fournisseur externe : l'externe pour les tâches exigeantes et, si un
    modèle local est installé, le local pour les petites tâches (moins de jetons payants)."""
    from ..ai.router import AIRouter, router_config

    profile = active_profile(settings, stored)
    if active == "null":
        return AIRouter(active="null", profile=profile)
    local_cfg = provider_config("local", settings, stored)
    use_local = active == "local" or bool(router_config().get("local_first", True))
    small = large = external = None
    if use_local:
        small = _wrap(OllamaProvider(base_url=local_cfg.base_url, model=local_cfg.model_small, tier="small"), settings, cache_dir, None)
        large = _wrap(OllamaProvider(base_url=local_cfg.base_url, model=local_cfg.model, tier="large"), settings, cache_dir, None)
    if active in REMOTE_IDS:
        ext = build_provider(active, settings, stored)
        if ext.available or settings.pai_ai_cache == "replay_only":
            external = _wrap(ext, settings, cache_dir, budget_eur)
    return AIRouter(small=small, large=large, external=external, active=active, profile=profile)


def get_provider(name: str | None = None, *, budget_eur: float | None = None, cache_dir: Path | None = None) -> AIProvider:
    """Fournisseur à utiliser par le pipeline et l'API : toujours le routeur (qui peut ne servir aucune IA)."""
    settings = get_settings()
    stored = read_stored_settings()
    active = normalize_provider_id(name or "") or active_provider_id(settings, stored)
    return build_router(active, settings, stored, budget_eur=budget_eur, cache_dir=cache_dir)
