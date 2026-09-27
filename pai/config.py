"""Configuration (variables d'environnement / .env). Aucun secret dans le code."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="")

    app_name: str = "PAI"
    environment: str = "development"          # development | production | test
    base_url: str = "http://localhost:8000"

    # Base de données : PostgreSQL 16 en production, SQLite accepté en local et en test.
    db_url: str = "sqlite:///./data/pai.db"

    # Fournisseur IA : claude | openai | local | null (mode dégradé, sans IA).
    pai_ai_provider: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""
    local_base_url: str = "http://localhost:11434/v1"
    local_model: str = ""
    pai_ai_cache: str = "on"                  # on | off | replay_only (tests hors ligne)

    # Sécurité
    secret_key: str = ""                       # signe les sessions et les URL de fichiers
    session_ttl_hours: int = 12
    file_url_ttl_seconds: int = 300
    login_rate_limit: int = 5                  # tentatives par fenêtre
    login_rate_window_seconds: int = 300
    cookie_secure: bool = True

    # Garde-fous
    cost_cap_eur_per_pack: float = 0.80
    cost_cap_eur_per_day: float = 6.00

    # Rendu PDF (Chromium headless via Playwright)
    chromium_executable: str = ""              # vide = chemin Playwright par défaut

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
