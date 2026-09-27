"""Sélection du fournisseur IA, interchangeable : claude | gemini | mistral | openai | local | null.

Ordre de résolution : réglages enregistrés (Réglages → IA : fournisseur actif, clé chiffrée, modèle, URL) →
environnement (PAI_AI_PROVIDER, clés) → config/models.yaml → null (mode dégradé). Base indisponible → environnement,
sans erreur. Aucun module métier n'importe de SDK de fournisseur.
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
from .openai_compat import (GEMINI_BASE_URL, MISTRAL_BASE_URL, OpenAICompatProvider, gemini_provider, local_provider,
                            mistral_provider, openai_provider)
from .store import StoredAiSettings, read_stored_settings

__all__ = ["AIProvider", "BudgetExceeded", "CachedProvider", "ClaudeProvider", "DegradedMode", "LABELS", "NullProvider",
           "OpenAICompatProvider", "PROVIDER_IDS", "ProviderConfig", "ProviderError", "active_provider_id", "ai_mode",
           "build_from_config", "build_provider", "extract_json", "get_provider", "provider_config"]

PROVIDER_IDS = ("claude", "gemini", "mistral", "openai", "local", "null")
LABELS = {"claude": "Claude", "gemini": "Gemini", "mistral": "Mistral", "openai": "OpenAI", "local": "Local (Ollama)",
          "null": "Désactivé"}
REMOTE_IDS = frozenset({"claude", "gemini", "mistral", "openai"})


@dataclass
class ProviderConfig:
    """Réglages effectifs d'un fournisseur ; `source` = origine (db | env | none). Clé en mémoire uniquement."""

    id: str
    api_key: str = field(default="", repr=False)
    model: str = ""
    base_url: str = ""
    source: str = "none"


def _env(pid: str, settings: Settings) -> tuple[str, str, str]:
    """(clé, modèle, URL de base) venant de l'environnement."""
    return {
        "claude": (settings.anthropic_api_key, "", ""),
        "gemini": (settings.gemini_api_key, settings.gemini_model, GEMINI_BASE_URL),
        "mistral": (settings.mistral_api_key, settings.mistral_model, MISTRAL_BASE_URL),
        "openai": (settings.openai_api_key, settings.openai_model, settings.openai_base_url),
        "local": ("", settings.local_model, settings.local_base_url),
    }.get(pid, ("", "", ""))


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
        source = "env" if env_key.strip() or (pid == "local" and env_model) else "none"
    return ProviderConfig(id=pid, api_key=api_key, model=db.model or env_model, base_url=base_url, source=source)


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
        return local_provider(cfg.model, cfg.base_url)
    return NullProvider()


def build_provider(name: str, settings: Settings, stored: StoredAiSettings | None = None) -> AIProvider:
    return build_from_config(provider_config((name or "").strip().lower(), settings, stored))


def active_provider_id(settings: Settings | None = None, stored: StoredAiSettings | None = None) -> str:
    """Fournisseur choisi : base → PAI_AI_PROVIDER → default_provider de config/models.yaml → null.
    Le premier choix renseigné l'emporte ; un identifiant inconnu vaut null."""
    settings = settings or get_settings()
    for candidate in (stored.active if stored is not None else "", settings.pai_ai_provider,
                      str(load_rules().models.get("default_provider") or "")):
        chosen = (candidate or "").strip().lower()
        if chosen:
            return chosen if chosen in PROVIDER_IDS else "null"
    return "null"


def ai_mode(pid: str, configured: bool) -> str:
    """REMOTE (fournisseur distant configuré), LOCAL (modèle local configuré), sinon DEGRADED (voies déterministes)."""
    if not configured:
        return "DEGRADED"
    return "REMOTE" if pid in REMOTE_IDS else "LOCAL" if pid == "local" else "DEGRADED"


def get_provider(name: str | None = None, *, budget_eur: float | None = None, cache_dir: Path | None = None) -> AIProvider:
    settings = get_settings()
    stored = read_stored_settings()
    inner = build_provider(name or active_provider_id(settings, stored), settings, stored)
    if not inner.available and settings.pai_ai_cache != "replay_only":
        return NullProvider()
    if settings.pai_ai_cache == "off":
        inner.budget_eur = budget_eur
        return inner
    provider = CachedProvider(inner=inner, cache_dir=cache_dir or paths.DATA_DIR / "cache", mode=settings.pai_ai_cache)
    provider.budget_eur = budget_eur
    return provider
