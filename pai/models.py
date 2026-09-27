from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PAI"
    environment: str = "development"
    anthropic_api_key: str = ""
    db_url: str = "sqlite:///./pai.db"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
