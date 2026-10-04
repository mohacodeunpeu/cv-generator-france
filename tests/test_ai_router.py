"""Couche IA locale-first : routeur par tâche, fournisseur Ollama, détection du matériel, registre, passerelle asynchrone.

Aucun appel réseau réel (Ollama simulé) ; le test marqué `real_ollama` n'utilise un vrai Ollama que s'il répond.
"""

from __future__ import annotations

import httpx
import pytest

from pai.ai import registry
from pai.ai.hardware import Hardware, detect
from pai.ai.router import AIRouter, task_level
from pai.config import Settings, reset_settings_cache
from pai.db.models import Job, LlmCall
from pai.db.session import session_scope
from pai.providers import CachedProvider, build_router, get_provider
from pai.providers.base import DegradedMode, ProviderError
from pai.providers.ollama import OllamaProvider, normalize_base_url, resolve_model
from tests.conftest import fake_ollama_state
from tests.fake_provider import FakeProvider
from tests.test_api import api_key, client  # noqa: F401 — fixture partagée (SQLite + PostgreSQL)


class Stub(FakeProvider):
    """Fournisseur factice dont on règle la disponibilité et qui renvoie son nom."""

    def __init__(self, name: str, up: bool = True):
        super().__init__(name=name)
        self.up = up

    @property
    def available(self) -> bool:
        return self.up

    def respond(self, task, prompt):  # noqa: ANN001, ARG002
        return {"by": self.name, "task": task}


# ── Routeur ──────────────────────────────────────────────────────────────────
def test_levels_by_profile_and_deterministic_tasks_never_use_ai():
    assert task_level("factuality_judge", "quality") == "none"          # la factualité reste déterministe
    assert task_level("match", "balanced") == "none" and task_level("match", "quality") == "large"
    assert task_level("letter", "eco") == "large" and task_level("strategy", "eco") == "none"
    assert task_level("extract", "balanced") == "small"
    assert task_level("tache_inconnue", "balanced") == "none"           # prudence : inconnu = sans IA


def test_route_prefers_local_for_small_tasks_and_external_for_large_ones():
    r = AIRouter(small=Stub("petit"), large=Stub("grand"), external=Stub("externe"), active="claude")
    assert r.route("extract")[0] == "small" and r.route("letter")[0] == "external"
    assert r.route("match") == ("none", None) and r.mode() == "REMOTE"
    local_only = AIRouter(small=Stub("petit", up=False), large=Stub("grand"), active="local")
    assert local_only.route("extract")[0] == "large" and local_only.route("letter")[0] == "large" and local_only.mode() == "LOCAL"
    ext_only = AIRouter(small=Stub("petit", up=False), large=Stub("grand", up=False), external=Stub("externe"), active="gemini")
    assert ext_only.route("extract")[0] == "external"
    nothing = AIRouter(small=Stub("petit", up=False), large=Stub("grand", up=False), active="local")
    assert not nothing.available and nothing.mode() == "DEGRADED"
    with pytest.raises(DegradedMode):
        nothing.complete("letter", "x")


def test_router_records_calls_with_tier_and_names_the_active_provider():
    r = AIRouter(small=Stub("petit"), large=Stub("grand"), active="local", profile="balanced")
    assert r.name == "local"
    r.json("extract", "chat", {"candidate_name": "X", "facts_table": "", "offer_context": "", "truth_rules": ""})
    assert [(c.task, c.tier, c.provider) for c in r.calls] == [("extract", "small", "petit")]
    with pytest.raises(DegradedMode):
        r.complete("cv_content", "x")   # balanced : CV déterministe, aucun appel
    assert len(r.calls) == 1


def test_explicit_none_means_no_ai_even_if_ollama_runs(monkeypatch):
    import pai.providers.ollama as ollama

    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state("qwen3:1.7b", "qwen3:4b-instruct-2507-q4_K_M"))
    settings = Settings(_env_file=None, ai_provider="")
    none = build_router("null", settings)
    assert not none.available and none.mode() == "DEGRADED"
    local = build_router("local", settings)
    assert local.mode() == "LOCAL" and local.model_for("extract") == "qwen3:1.7b"
    assert local.model_for("letter") == "qwen3:4b-instruct-2507-q4_K_M"


def test_cache_key_changes_with_model_parameters(tmp_path, monkeypatch):
    p = CachedProvider(inner=OllamaProvider(model="m"), cache_dir=tmp_path)
    k1 = p.key("letter", "prompt")
    monkeypatch.setattr(registry, "task_params", lambda task: {"num_ctx": 1234, "temperature": 0.9, "max_tokens": 5})
    assert p.key("letter", "prompt") != k1                      # paramètres changés → nouvel appel
    assert p.key("letter", "prompt") == p.key("letter", "prompt")  # même entrée → même clé → cache


# ── Fournisseur Ollama ─────────────────────────────────────────────────────────
def test_ollama_base_url_normalization_and_model_resolution():
    assert normalize_base_url("http://ollama:11434/v1/") == "http://ollama:11434" and normalize_base_url("") == "http://localhost:11434"
    state = fake_ollama_state("gemma3:1b", "qwen3:4b-instruct-2507-q4_K_M", "embeddinggemma:latest")
    assert resolve_model("small", "", state) == "gemma3:1b"                     # meilleur petit modèle installé
    assert resolve_model("large", "", state) == "qwen3:4b-instruct-2507-q4_K_M"
    assert resolve_model("embed", "", state) == "embeddinggemma"
    assert resolve_model("large", "absent:7b", state) == ""                     # choix explicite non installé → sans IA
    assert resolve_model("large", "", fake_ollama_state()) == ""


def test_ollama_native_call_json_think_and_errors(monkeypatch):
    import pai.providers.ollama as ollama

    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state("qwen3:1.7b"))
    sent = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002
        sent.append((url, json))
        body = {"message": {"content": '<think>brouillon</think>{"ok": true}'}, "prompt_eval_count": 12, "eval_count": 5}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    p = OllamaProvider(base_url="http://ollama:11434/v1", tier="small")
    r = p.complete("extract", "Réponds par le JSON demandé.")
    url, payload = sent[-1]
    assert url == "http://ollama:11434/api/chat" and payload["format"] == "json" and payload["think"] is False
    assert payload["model"] == "qwen3:1.7b" and payload["options"]["num_predict"] == 400 and payload["stream"] is False
    assert r.text == '{"ok": true}' and (r.tokens_in, r.tokens_out) == (12, 5) and r.cost_eur == 0.0
    p.complete("chat", "Dis bonjour.")
    assert "format" not in sent[-1][1]                        # texte libre : pas de contrainte JSON

    def down(url, json=None, timeout=None):  # noqa: A002
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", down)
    with pytest.raises(ProviderError, match="injoignable"):
        p.complete("extract", "JSON")


def test_rejected_answers_never_come_back_from_the_cache(tmp_path, monkeypatch):
    """Une réponse rejetée (JSON invalide) est oubliée : ni l'essai suivant ni le pack suivant ne la relisent."""
    import pai.providers.ollama as ollama

    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state("qwen3:1.7b"))
    answers = iter(['{"incomplet": ', '{"incomplet": ', '{"ok": true}'])
    calls = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002
        calls.append(json)
        return httpx.Response(200, json={"message": {"content": next(answers)}, "done_reason": "stop"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    p = CachedProvider(inner=OllamaProvider(tier="small"), cache_dir=tmp_path)
    assert p.json("analyze_company", "analyze_company", {"company": "Acme", "offer_text": "Vendeur chez Acme, JSON", "sources": "annonce"}) == {"ok": True}
    assert len(calls) == 3                                         # 3 vrais appels : aucun rejet resservi
    assert len(list(tmp_path.glob("*.json"))) == 2                 # la réponse valide, sous sa clé et celle de la demande
    assert p.json("analyze_company", "analyze_company", {"company": "Acme", "offer_text": "Vendeur chez Acme, JSON", "sources": "annonce"}) is not None and len(calls) == 3  # rejeu : cache


def test_ollama_truncated_answer_and_timeout_from_measured_speed(tmp_path, monkeypatch):
    import pai.providers.ollama as ollama
    from pai.ai.selfeval import recommend_profile
    from pai.providers.ollama import call_timeout

    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state("qwen3:1.7b"))
    monkeypatch.setattr(httpx, "post", lambda url, json=None, timeout=None: httpx.Response(  # noqa: A002
        200, json={"message": {"content": '{"lines": [{"text": "Madame'}, "done_reason": "length"},
        request=httpx.Request("POST", url)))
    p = CachedProvider(inner=OllamaProvider(tier="small"), cache_dir=tmp_path)
    with pytest.raises(ProviderError, match="tronquée"):
        p.complete("letter", "Réponds par le JSON demandé.")
    assert not list(tmp_path.glob("*.json"))                       # rien de tronqué en cache
    # délai : jamais en dessous de la configuration ; allongé selon la vitesse mesurée ; plafonné
    assert call_timeout(600, "x" * 9000, 1600, 0) == 600
    assert 700 < call_timeout(600, "x" * 9000, 1600, 3.3) < 750              # 64 s de lecture + 630 s de génération
    assert call_timeout(600, "x" * 9000, 1600, 0.5) == 900
    # profil conseillé : eco si le grand modèle est lent sur cette machine
    report = {"results": [{"model": "lent", "tokens_per_s": 4.4}, {"model": "rapide", "tokens_per_s": 20.0}]}
    assert recommend_profile({"large": "lent"}, report) == "eco"
    assert recommend_profile({"large": "rapide"}, report) == "balanced"


def test_measured_profile_applies_to_local_ai_only(tmp_path, monkeypatch):
    import json as _json

    from pai import paths
    from pai.providers import active_profile

    (tmp_path / "ai").mkdir()
    (tmp_path / "ai" / "local_selection.json").write_text(_json.dumps({"selection": {"large": "lent"},
                                                                       "recommended_profile": "eco"}), encoding="utf-8")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    settings = Settings(ai_profile="")
    assert active_profile(settings, None, "local") == "eco"
    assert active_profile(settings, None, "claude") == "balanced"           # fournisseur externe : pas concerné
    assert active_profile(Settings(ai_profile="quality"), None, "local") == "quality"   # choix explicite d'abord


def test_ollama_embeddings(monkeypatch):
    import pai.providers.ollama as ollama

    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state("embeddinggemma:latest"))
    monkeypatch.setattr(httpx, "post", lambda url, json=None, timeout=None: httpx.Response(  # noqa: A002
        200, json={"embeddings": [[0.1, 0.2]] * len(json["input"])}, request=httpx.Request("POST", url)))
    assert OllamaProvider().embed(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]


# ── Matériel et registre ───────────────────────────────────────────────────────
def test_hardware_detection_reads_the_real_machine():
    hw = detect()
    assert hw.arch in ("x86_64", "arm64") and hw.cpus > 0 and hw.ram_total_gb > 0
    assert set(hw.as_dict()) >= {"arch", "cpus", "ram_total_gb", "gpus", "vram_gb", "disk_free_gb"}


def test_hardware_of_a_separate_ollama_container(monkeypatch):
    """Profil Docker ai-local : la détection lit les ressources du conteneur Ollama, bornées par la machine."""
    import os

    from pai.ai import hardware

    machine_ram = hardware._meminfo_gb("MemTotal")
    monkeypatch.setenv("PAI_AI_HOST_CPUS", "2")
    monkeypatch.setenv("PAI_AI_HOST_RAM_GB", "6")
    hw = detect()
    assert hw.cpus == min(2.0, float(os.cpu_count()))
    assert hw.ram_total_gb == round(min(6.0, machine_ram), 1)
    assert any("serveur Ollama" in n for n in hw.notes)
    monkeypatch.setenv("PAI_AI_HOST_RAM_GB", "100000")                        # jamais plus que la machine
    assert detect().ram_total_gb == round(machine_ram, 1)


def test_registry_keeps_only_models_that_fit():
    small_box = Hardware(arch="arm64", cpus=4, ram_total_gb=7, ram_available_gb=6)  # 4 Go pour un modèle
    rec = registry.recommend(small_box)
    fits = {c["id"]: c["fits"] for c in rec["large"]}
    assert fits["qwen3-8b"] is False and fits["qwen3-4b-instruct"] is False and fits["qwen2.5-3b"] is True
    big_box = Hardware(arch="arm64", cpus=4, ram_total_gb=24, ram_available_gb=22)
    rec = registry.recommend(big_box)
    assert rec["large"][0]["id"] == "qwen3-4b-instruct"                        # 8B écarté sans GPU sur 4 cœurs
    gpu_box = Hardware(arch="x86_64", cpus=8, ram_total_gb=32, gpus=[{"name": "RTX", "vram_gb": 12}])
    assert registry.recommend(gpu_box)["large"][0]["id"] == "qwen3-8b"


# ── Passerelle PAI Studio asynchrone ─────────────────────────────────────────────
def test_gateway_async_job_and_deterministic_tasks(client, monkeypatch):  # noqa: F811
    from pai.api import jobs

    def fake_get_provider(name=None, *, budget_eur=None, cache_dir=None):  # noqa: ANN001
        return AIRouter(small=Stub("petit"), large=Stub("grand"), active="local")

    monkeypatch.setattr("pai.api.v1.get_provider", fake_get_provider)
    reset_settings_cache()
    h = api_key("generate", "read")
    det = client.post("/v1/ai/complete", json={"prompt": "x", "task": "cv_content", "json": True, "async": True}, headers=h)
    assert det.status_code == 503 and det.json()["detail"]["code"] == "not_granted"   # aucune IA, aucun job
    r = client.post("/v1/ai/complete", json={"prompt": "Offre + profil utiles", "task": "letter", "json": True, "async": True}, headers=h)
    assert r.status_code == 202 and r.json()["tier"] == "large"
    job_id = r.json()["job_id"]
    assert client.get(f"/v1/jobs/{job_id}", headers=h).json()["status"] == "PENDING"
    assert jobs.run_once()
    done = client.get(f"/v1/jobs/{job_id}", headers=h).json()
    assert done["status"] == "DONE" and done["result"]["json"] == {"by": "grand", "task": "letter"} and done["result"]["tier"] == "large"
    with session_scope() as s:
        assert "prompt" not in s.get(Job, job_id).payload                  # le prompt n'est pas conservé
        assert [(c.task, c.provider) for c in s.query(LlmCall)] == [("letter", "grand")]


def test_default_provider_is_free_and_falls_back_to_no_ai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "")
    monkeypatch.setenv("PAI_AI_PROVIDER", "")
    reset_settings_cache()
    p = get_provider()
    assert p.name == "local" and p.mode() == "DEGRADED"      # défaut gratuit ; sans Ollama → sans IA, sans erreur


@pytest.mark.real_ollama
def test_real_ollama_json_extraction():
    """Seulement si un vrai Ollama répond (machine de développement, serveur) : jamais en CI."""
    from pai.providers.ollama import probe, reset_probe_cache

    reset_probe_cache()
    state = probe("http://127.0.0.1:11434")
    small = resolve_model("small", "", state)
    if not state.get("reachable") or not small:
        pytest.skip("Ollama absent")
    p = OllamaProvider(base_url="http://127.0.0.1:11434", tier="small")
    data = p.json("extract", "chat", {"candidate_name": "Camille Test", "facts_table": "", "truth_rules": "",
                                      "offer_context": "Réponds en JSON {\"ok\": true}"})
    assert isinstance(data, dict)
