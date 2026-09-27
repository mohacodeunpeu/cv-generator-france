"""Chemins du dépôt (règles, prompts, polices…) et du stockage local."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "config"
RULES_DIR = ROOT / "rules"
COUNTRY_DIR = RULES_DIR / "country"
SECTOR_DIR = ROOT / "sector_profiles"
DESIGN_DIR = ROOT / "design_profiles"
BRAND_DIR = ROOT / "brand"
PROMPTS_DIR = ROOT / "prompts"
PROFILES_DIR = ROOT / "profiles"
FONTS_DIR = ROOT / "fonts"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
LEGACY_DIR = ROOT / "legacy"
BENCHMARK_DIR = ROOT / "benchmark"
WEB_DIR = ROOT / "web"

# Données personnelles et fichiers générés : hors Git (voir .gitignore).
DATA_DIR = Path(os.environ.get("PAI_DATA_DIR", ROOT / "data"))


def ensure_data_dirs() -> Path:
    for sub in ("", "packs", "files", "cache", "backups"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    return DATA_DIR
