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
os.environ["AI_PROVIDER"] = os.environ.get("PAI_TEST_AI_PROVIDER", "none")  # jamais celui du shell du développeur
os.environ.setdefault("ENVIRONMENT", "test")

from pai.config import reset_settings_cache  # noqa: E402
from pai.schemas import MasterProfile  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "real_ollama: test qui utilise un vrai serveur Ollama (ignoré s'il est absent)")


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


@pytest.fixture(autouse=True)
def no_local_ollama(request, monkeypatch):
    """Un Ollama peut tourner sur la machine de test : les tests ne le voient jamais, sauf marqueur `real_ollama`.
    Résultats identiques en CI (sans Ollama) et en local."""
    import pai.providers.ollama as ollama

    ollama.reset_probe_cache()
    if request.node.get_closest_marker("real_ollama") is None:
        monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: {
            "reachable": False, "version": "", "models": [], "error": "Ollama injoignable (test)"})
    yield
    ollama.reset_probe_cache()


def fake_ollama_state(*names: str) -> dict:
    """État d'un Ollama simulé avec les modèles `names` installés."""
    return {"reachable": True, "version": "test", "models": [{"name": n, "size_gb": 1.0, "family": "", "quantization": ""} for n in names], "error": ""}
