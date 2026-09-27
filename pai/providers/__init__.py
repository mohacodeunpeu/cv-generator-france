"""Sélection du fournisseur IA (PAI_AI_PROVIDER, sinon config/models.yaml, sinon mode dégradé)."""

from __future__ import annotations

from pathlib import Path

from .. import paths
from ..config import Settings, get_settings
from ..rules import load_rules
from .base import AIProvider, BudgetExceeded, DegradedMode, ProviderError, extract_json
from .cache import CachedProvider
from .claude import ClaudeProvider
from .null import NullProvider
from .openai_compat import OpenAICompatProvider, local_provider, openai_provider

__all__ = ["AIProvider", "BudgetExceeded", "CachedProvider", "ClaudeProvider", "DegradedMode", "NullProvider",
           "OpenAICompatProvider", "ProviderError", "extract_json", "get_provider"]


def build_provider(name: str, settings: Settings) -> AIProvider:
    name = (name or "").lower()
    if name == "claude":
        return ClaudeProvider(api_key=settings.anthropic_api_key)
    if name == "openai":
        return openai_provider(settings.openai_api_key, settings.openai_model, settings.openai_base_url)
    if name == "local":
        return local_provider(settings.local_model, settings.local_base_url)
    return NullProvider()


def get_provider(name: str | None = None, *, budget_eur: float | None = None, cache_dir: Path | None = None) -> AIProvider:
    settings = get_settings()
    chosen = name or settings.pai_ai_provider or load_rules().models.get("default_provider", "null")
    inner = build_provider(chosen, settings)
    if not inner.available and settings.pai_ai_cache != "replay_only":
        return NullProvider()
    if settings.pai_ai_cache == "off":
        inner.budget_eur = budget_eur
        return inner
    provider = CachedProvider(inner=inner, cache_dir=cache_dir or paths.DATA_DIR / "cache", mode=settings.pai_ai_cache)
    provider.budget_eur = budget_eur
    return provider
