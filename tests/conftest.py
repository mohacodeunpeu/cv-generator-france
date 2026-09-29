"""Fixtures communes. Les tests n'utilisent QUE le profil fictif « Camille Test » (aucune donnée personnelle)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PAI_AI_PROVIDER", "null")
os.environ.setdefault("ENVIRONMENT", "test")

from pai.config import reset_settings_cache  # noqa: E402
from pai.schemas import MasterProfile  # noqa: E402

TEST_OFFER = ("Business Developer Junior (H/F) — CDI — Paris\nAcme SaaS édite un logiciel pour les PME françaises depuis 2015.\n\n"
              "Vos missions\n- Prospecter de nouveaux clients PME par téléphone et LinkedIn.\n- Suivre votre pipeline dans HubSpot.\n\n"
              "Votre profil\n- Anglais courant requis.\n- Maîtrise d'un CRM indispensable.")


@pytest.fixture()
def profile() -> MasterProfile:
    return MasterProfile.model_validate(json.loads((ROOT / "tests" / "fixtures" / "profile_test.json").read_text(encoding="utf-8")))


@pytest.fixture()
def golden() -> dict:
    return json.loads((ROOT / "tests" / "golden" / "validator_cases.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("PAI_DATA_DIR", str(tmp_path / "data"))
    import pai.paths as paths

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture(scope="session", autouse=True)
def shutdown_renderer():
    yield
    from pai.render import PdfRenderer

    PdfRenderer.shutdown()
