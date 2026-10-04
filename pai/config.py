"""Configuration (variables d'environnement / .env). Aucun secret dans le code."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Modèles par défaut des fournisseurs compatibles OpenAI qui en ont un (surchargeables : env ou Réglages → IA).
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
MISTRAL_DEFAULT_MODEL = "mistral-large-latest"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="")

    app_name: str = "PAI"
    environment: str = "development"          # development | production | test
    base_url: str = "http://localhost:8000"

    # Base de données : PostgreSQL 16 en production, SQLite accepté en local et en test.
    db_url: str = "sqlite:///./data/pai.db"

    # Fournisseur IA : local (Ollama, gratuit) | none (sans IA) | anthropic | openai_compatible | gemini | mistral.
    # AI_PROVIDER est le nom documenté ; PAI_AI_PROVIDER (ancien nom) reste accepté. Défaut : config/models.yaml
    # (local, qui retombe sur « sans IA » si Ollama n'a aucun modèle). Les réglages enregistrés depuis l'interface
    # (Réglages → IA, clés chiffrées en base) priment sur ces variables.
    ai_provider: str = ""
    ai_model: str = ""                         # modèle du fournisseur actif (grand modèle pour local)
    ai_model_small: str = ""                   # petit modèle local (extraction, classement)
    pai_access: str = ""                       # cloudflare | caddy | tailscale (affiché dans « État du système »)
    compose_profiles: str = ""                 # profils Docker actifs (COMPOSE_PROFILES), ex. cloudflare,ai-local
    cloudflared_metrics_url: str = ""          # ex. http://pai_cloudflared:2000 (profil cloudflare) : état du tunnel
    ai_base_url: str = ""                      # URL du fournisseur actif (Ollama, serveur compatible OpenAI)
    ai_api_key: str = ""                       # clé du fournisseur actif (jamais obligatoire)
    ai_profile: str = ""                       # eco | balanced | quality (routeur de tâches)
    ollama_base_url: str = ""                  # ex. http://pai_ollama:11434 (Docker) ; défaut http://localhost:11434
    pai_ai_provider: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = GEMINI_DEFAULT_MODEL
    mistral_api_key: str = ""
    mistral_model: str = MISTRAL_DEFAULT_MODEL
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

    @property
    def access(self) -> str:
        """Accès public : PAI_ACCESS, sinon déduit des profils Docker (cloudflare ou caddy, jamais les deux ensemble)."""
        if self.pai_access:
            return self.pai_access.strip().lower()
        profiles = {p.strip().lower() for p in self.compose_profiles.split(",") if p.strip()}
        if "cloudflare" in profiles and "caddy" not in profiles:
            return "cloudflare"
        if "caddy" in profiles and "cloudflare" not in profiles:
            return "caddy"
        return ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
