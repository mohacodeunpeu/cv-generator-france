"""Fournisseurs IA interchangeables et réglages enregistrés côté serveur (clés chiffrées) : résolution, API
/v1/settings/ai, test de connexion, /v1/status. SQLite + PostgreSQL (fixture `client`), aucun appel réseau réel.

Les clés utilisées sont factices (jamais de vraie clé dans les tests).
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from sqlalchemy import text

from pai.api.security import secret_key
from pai.config import Settings, reset_settings_cache
from pai.db.models import AppSetting, AuditLog, LlmCall
from pai.db.session import session_scope
from pai.providers import (
    PROVIDER_IDS,
    ClaudeProvider,
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    active_provider_id,
    ai_mode,
    build_provider,
    get_provider,
    provider_config,
)
from pai.providers.openai_compat import GEMINI_BASE_URL, MISTRAL_BASE_URL
from pai.providers.store import (
    StoredAiSettings,
    StoredProvider,
    decode_settings,
    decrypt_secret,
    encrypt_secret,
    key_hint,
    read_stored_settings,
)
from tests.conftest import TEST_OFFER, fake_ollama_state
from tests.fake_provider import FakeProvider
from tests.test_api import api_key, client, login, session_csrf  # noqa: F401 — fixture partagée (SQLite + PostgreSQL)

GEMINI_KEY = "gm-test-0123456789abcdefWXYZ"
MISTRAL_KEY = "ms-test-9876543210fedcbaQRST"
OPENAI_KEY = "sk-test-openai-aaaabbbbccccDDDD"
CLAUDE_KEY = "sk-ant-test-1111222233334444ABCD"


def chat_response(content: str = "OK", status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 7, "completion_tokens": 1}},
                          request=httpx.Request("POST", "https://fournisseur.test/chat/completions"))


@pytest.fixture()
def fake_chat(monkeypatch):
    """Remplace httpx.post (utilisé par OpenAICompatProvider) : enregistre les appels, répond « OK »."""
    calls: list[dict] = []
    replies: list[httpx.Response] = []

    def post(url, json=None, headers=None, timeout=None):  # noqa: A002
        calls.append({"url": url, "json": json, "headers": headers or {}})
        return replies.pop(0) if replies else chat_response()

    monkeypatch.setattr(httpx, "post", post)
    return calls, replies


def admin() -> dict[str, str]:
    return api_key("admin", "read")


def put(c, body: dict, headers: dict | None = None):
    return c.put("/v1/settings/ai", json=body, headers=headers if headers is not None else admin())


def by_id(payload: dict) -> dict[str, dict]:
    return {p["id"]: p for p in payload["providers"]}


# ── Chiffrement ─────────────────────────────────────────────────────────────
def test_keys_encrypted_with_key_derived_from_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a" * 48)
    reset_settings_cache()
    secret_key.cache_clear()
    try:
        token = encrypt_secret(GEMINI_KEY)
        assert GEMINI_KEY not in token and token.startswith("gAAAA") and decrypt_secret(token) == GEMINI_KEY
        assert encrypt_secret(GEMINI_KEY) != token  # IV aléatoire : jamais deux fois le même chiffré
        stored = {"active": "gemini", "providers": {"gemini": {"key": token}}}
        assert decode_settings(stored).get("gemini").api_key == GEMINI_KEY
        monkeypatch.setenv("SECRET_KEY", "b" * 48)  # SECRET_KEY changée : clé illisible → ignorée, sans erreur
        reset_settings_cache()
        secret_key.cache_clear()
        decoded = decode_settings(stored)
        assert decoded.active == "gemini" and decoded.get("gemini").api_key == ""
    finally:
        secret_key.cache_clear()


def test_key_hint_masks_everything_but_last_four():
    assert key_hint(GEMINI_KEY) == "••••WXYZ" and key_hint("") == "" and key_hint("court-123") == "••••"


# ── Résolution et construction des fournisseurs ─────────────────────────────
def test_every_provider_id_is_buildable():
    settings = Settings(_env_file=None, ai_provider="", anthropic_api_key=CLAUDE_KEY, gemini_api_key=GEMINI_KEY, mistral_api_key=MISTRAL_KEY,
                        openai_api_key=OPENAI_KEY, openai_model="gpt-test", local_model="llama-test",
                        local_base_url="http://localhost:11434/v1")
    built = {pid: build_provider(pid, settings) for pid in PROVIDER_IDS}
    assert isinstance(built["claude"], ClaudeProvider) and isinstance(built["null"], NullProvider)
    assert all(isinstance(built[p], OpenAICompatProvider) for p in ("gemini", "mistral", "openai"))
    local = built["local"]  # Ollama natif ; l'ancienne URL compatible OpenAI (…/v1) est acceptée et normalisée
    assert isinstance(local, OllamaProvider) and local.base_url == "http://localhost:11434" and local.model == "llama-test"
    assert {p: b.name for p, b in built.items()} == {p: p for p in PROVIDER_IDS}
    assert built["gemini"].base_url == GEMINI_BASE_URL and built["gemini"].model == "gemini-2.5-flash"
    assert built["mistral"].base_url == MISTRAL_BASE_URL and built["mistral"].model == "mistral-large-latest"
    assert all(built[p].available for p in ("claude", "gemini", "mistral", "openai")) and not built["null"].available
    assert not local.available  # Ollama injoignable (sonde simulée) : jamais d'erreur, seulement « sans IA »
    assert build_provider("inconnu", settings).name == "null"
    custom = Settings(_env_file=None, gemini_api_key=GEMINI_KEY, gemini_model="gemini-2.5-pro", mistral_model="")
    assert build_provider("gemini", custom).model == "gemini-2.5-pro" and build_provider("mistral", custom).model == "mistral-large-latest"
    assert not build_provider("mistral", custom).available  # pas de clé → indisponible


def test_active_provider_resolution_order():
    env = Settings(_env_file=None, ai_provider="mistral")
    assert active_provider_id(env, StoredAiSettings(active="gemini")) == "gemini"      # 1. base
    assert active_provider_id(env, StoredAiSettings()) == "mistral"                    # 2. environnement (AI_PROVIDER)
    legacy = Settings(_env_file=None, ai_provider="", pai_ai_provider="gemini")
    assert active_provider_id(legacy, StoredAiSettings()) == "gemini"                  # ancien nom PAI_AI_PROVIDER
    default = Settings(_env_file=None, ai_provider="", pai_ai_provider="")
    assert active_provider_id(default, StoredAiSettings()) == "local"                  # 3. models.yaml : gratuit par défaut
    assert active_provider_id(Settings(_env_file=None, ai_provider="inconnu")) == "null"  # identifiant inconnu → null
    for alias, pid in (("none", "null"), ("anthropic", "claude"), ("openai_compatible", "openai"), ("ollama", "local")):
        assert active_provider_id(Settings(_env_file=None, ai_provider=alias), StoredAiSettings()) == pid


def test_provider_config_prefers_db_and_never_sends_env_key_elsewhere():
    env = Settings(_env_file=None, openai_api_key=OPENAI_KEY, openai_model="gpt-env", gemini_api_key="env-gemini-key-000")
    stored = StoredAiSettings(providers={"gemini": StoredProvider(api_key=GEMINI_KEY, model="gemini-2.5-pro"),
                                         "openai": StoredProvider(base_url="https://proxy.example.fr/v1")})
    gemini = provider_config("gemini", env, stored)
    assert (gemini.api_key, gemini.model, gemini.source) == (GEMINI_KEY, "gemini-2.5-pro", "db")
    assert provider_config("gemini", env, StoredAiSettings()).source == "env"
    openai = provider_config("openai", env, stored)
    assert openai.base_url == "https://proxy.example.fr/v1" and openai.api_key == ""  # clé d'env non envoyée au proxy
    assert provider_config("openai", env, StoredAiSettings()).api_key == OPENAI_KEY
    assert provider_config("mistral", env, stored).source == "none" and provider_config("null", env, stored).source == "none"


def test_ai_mode():
    assert [ai_mode(p, True) for p in PROVIDER_IDS] == ["LOCAL"] + ["REMOTE"] * 4 + ["DEGRADED"]
    assert {ai_mode(p, False) for p in PROVIDER_IDS} == {"DEGRADED"}


def test_get_provider_falls_back_to_env_when_db_unavailable(monkeypatch, tmp_path):
    from pai.db.session import reset_engines

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", GEMINI_KEY)
    empty = tmp_path / "vide.db"
    empty.write_bytes(b"")  # base SQLite sans table app_settings (migration non appliquée)
    urls = [f"sqlite:///{tmp_path}/absente.db", f"sqlite:///{empty}", "postgresql+psycopg://pai:x@127.0.0.1:1/injoignable"]
    try:
        for url in urls:
            monkeypatch.setenv("DB_URL", url)
            reset_settings_cache()
            reset_engines()
            assert read_stored_settings() == StoredAiSettings(), url
            provider = get_provider(budget_eur=0.5)  # routeur : l'externe sert les tâches IA, le plafond s'y applique
            assert provider.name == "gemini" and provider.available and provider.external.budget_eur == 0.5
            assert provider.model_for("extract") == "gemini-2.5-flash" and provider.model_for("match") == "none"
        assert not (tmp_path / "absente.db").exists()  # une simple lecture ne crée pas de base vide
    finally:
        reset_engines()


# ── API : lecture ────────────────────────────────────────────────────────────
def test_get_settings_lists_all_providers_without_secrets(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLAUDE_KEY)
    reset_settings_cache()
    r = client.get("/v1/settings/ai", headers=api_key("read"))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["active"] == "null" and data["mode"] == "DEGRADED"  # PAI_AI_PROVIDER=null dans la fixture
    providers = by_id(data)
    assert list(providers) == list(PROVIDER_IDS)
    assert {p: v["label"] for p, v in providers.items()} == {
        "local": "IA locale (Ollama)", "claude": "Claude (Anthropic)", "gemini": "Gemini", "mistral": "Mistral",
        "openai": "OpenAI / compatible", "null": "Sans IA"}
    assert all(set(v) == {"id", "label", "configured", "key_hint", "model", "model_small", "base_url", "source"} for v in providers.values())
    assert data["profile"] == "balanced" and data["plan"]["factuality_judge"] == "none"
    claude = providers["claude"]
    assert claude["configured"] and claude["source"] == "env" and claude["key_hint"] == "••••ABCD" and claude["model"] == "claude-sonnet-5"
    assert not providers["gemini"]["configured"] and providers["gemini"]["source"] == "none"
    assert providers["gemini"]["model"] == "gemini-2.5-flash" and providers["gemini"]["base_url"] == GEMINI_BASE_URL
    assert providers["null"]["configured"] and CLAUDE_KEY not in r.text


# ── API : écriture ───────────────────────────────────────────────────────────
def test_put_stores_key_encrypted_and_returns_only_a_hint(client, caplog):
    caplog.set_level(logging.DEBUG)
    r = put(client, {"active": "gemini", "provider": "gemini", "api_key": f"  {GEMINI_KEY}\n"})
    assert r.status_code == 200, r.text
    assert GEMINI_KEY not in r.text
    data = r.json()
    gemini = by_id(data)["gemini"]
    assert data["active"] == "gemini" and data["mode"] == "REMOTE"
    assert gemini["configured"] and gemini["key_hint"] == "••••WXYZ" and gemini["source"] == "db"
    for extra in ({"provider": "mistral", "api_key": MISTRAL_KEY}, {"provider": "openai", "api_key": OPENAI_KEY, "model": "gpt-test"},
                  {"provider": "claude", "api_key": CLAUDE_KEY}):
        assert put(client, extra).status_code == 200
    with session_scope() as s:
        raw = s.execute(text("SELECT value FROM app_settings WHERE key = 'ai'")).scalar_one()
        audit = [json.dumps(a.detail) + a.target + a.action for a in s.query(AuditLog).filter_by(action="update_ai_settings")]
    raw = raw if isinstance(raw, str) else json.dumps(raw)
    stored = json.loads(raw)
    for secret in (GEMINI_KEY, MISTRAL_KEY, OPENAI_KEY, CLAUDE_KEY):
        assert secret not in raw and all(secret not in line for line in audit) and secret not in caplog.text
    assert decrypt_secret(stored["providers"]["gemini"]["key"]) == GEMINI_KEY
    assert len(audit) == 4 and "api_key" in audit[0]
    listing = client.get("/v1/settings/ai", headers=api_key("read"))
    assert all(secret not in listing.text for secret in (GEMINI_KEY, MISTRAL_KEY, OPENAI_KEY, CLAUDE_KEY))
    assert {p["id"]: p["key_hint"] for p in listing.json()["providers"]} == {
        "claude": "••••ABCD", "gemini": "••••WXYZ", "mistral": "••••QRST", "openai": "••••DDDD", "local": "", "null": ""}


def test_put_model_base_url_clear_key_and_reset(client, monkeypatch):
    import pai.providers.ollama as ollama

    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state("llama3.1:8b", "qwen3:1.7b"))
    assert put(client, {"provider": "claude", "model": "claude-opus-5-5"}).status_code == 200
    assert put(client, {"provider": "local", "model": "llama3.1:8b", "base_url": "http://ollama:11434/v1/"}).status_code == 200
    data = put(client, {"active": "local", "profile": "eco"}).json()
    local = by_id(data)["local"]
    assert data["mode"] == "LOCAL" and local["configured"] and local["base_url"] == "http://ollama:11434" and local["source"] == "db"
    assert local["model_small"] == "qwen3:1.7b" and data["profile"] == "eco" and data["plan"]["strategy"] == "none"
    assert by_id(data)["claude"]["model"] == "claude-opus-5-5"
    assert by_id(put(client, {"provider": "local", "model_small": "llama3.1:8b"}).json())["local"]["model_small"] == "llama3.1:8b"
    assert put(client, {"provider": "gemini", "model_small": "x"}).status_code == 422
    assert put(client, {"profile": "turbo"}).status_code == 422
    assert by_id(put(client, {"provider": "openai", "api_key": OPENAI_KEY, "model": "gpt-test"}).json())["openai"]["configured"]
    moved = by_id(put(client, {"provider": "openai", "base_url": "https://proxy.example.fr/v1"}).json())["openai"]
    assert not moved["configured"] and moved["key_hint"] == ""  # nouvelle URL : la clé enregistrée est effacée
    assert by_id(put(client, {"provider": "openai", "base_url": "", "api_key": OPENAI_KEY}).json())["openai"]["configured"]
    cleared = by_id(put(client, {"provider": "openai", "clear_key": True}).json())["openai"]
    assert not cleared["configured"] and cleared["key_hint"] == ""
    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state())
    reset = by_id(put(client, {"provider": "local", "model": "", "model_small": "", "base_url": ""}).json())["local"]
    assert not reset["configured"] and reset["base_url"] == "http://localhost:11434" and reset["source"] == "auto"
    assert put(client, {"active": "null"}).json()["mode"] == "DEGRADED"


@pytest.mark.parametrize("body", [
    {"active": "gpt"}, {"provider": "inconnu", "api_key": GEMINI_KEY}, {"api_key": GEMINI_KEY}, {"model": "x"},
    {"provider": "gemini", "base_url": "https://ailleurs.example.fr/v1"}, {"provider": "openai", "base_url": "ftp://x.example.fr/v1"},
    {"provider": "local", "base_url": "http://user:pw@ollama:11434/v1"}, {"provider": "openai", "base_url": "https://x.fr/v1?key=1"},
    {"provider": "local", "api_key": GEMINI_KEY}, {"provider": "null", "model": "x"}, {"provider": "gemini", "api_key": "trop court"},
    {"provider": "gemini", "api_key": "cle avec espaces 12345"}, {"provider": "gemini", "api_key": GEMINI_KEY, "clear_key": True},
    {"provider": "gemini", "model": "modèle; rm -rf"}, {"provider": "gemini", "model": "m" * 81}, {"provider": "gemini", "secret": "x"},
    {"provider": "gemini", "api_key": GEMINI_KEY * 40}])
def test_put_validation(client, body):
    r = put(client, body)
    assert r.status_code == 422, (body, r.text)
    assert GEMINI_KEY not in r.text  # une clé refusée n'est jamais recopiée dans la réponse


def test_scopes_and_csrf_are_enforced(client):
    body = {"provider": "gemini", "api_key": GEMINI_KEY}
    read = api_key("read")
    paths = client.get("/openapi.json", headers=read).json()["paths"]
    assert {"get", "put"} <= set(paths["/v1/settings/ai"]) and "post" in paths["/v1/settings/ai/test"] and "get" in paths["/v1/status"]
    assert client.get("/v1/settings/ai").status_code == 401
    assert client.get("/v1/settings/ai", headers=read).status_code == 200
    assert put(client, body, headers=read).status_code == 403
    assert client.post("/v1/settings/ai/test", json={"provider": "gemini"}, headers=read).status_code == 403
    assert put(client, body, headers=api_key("generate", "analyze")).status_code == 403
    login(client)
    csrf = session_csrf(client)
    assert put(client, body, headers={}).status_code == 403                          # session sans jeton CSRF
    assert put(client, body, headers={"X-CSRF-Token": "faux"}).status_code == 403
    assert client.post("/v1/settings/ai/test", json={"provider": "gemini"}).status_code == 403
    r = put(client, body, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and by_id(r.json())["gemini"]["configured"]
    with session_scope() as s:
        assert s.query(AuditLog).filter_by(action="update_ai_settings").one().actor == "camille"


# ── Test de connexion ────────────────────────────────────────────────────────
def test_connection_test_success_bypasses_cache_and_budget_and_is_journaled(client, fake_chat, monkeypatch):
    calls, _ = fake_chat
    put(client, {"provider": "gemini", "api_key": GEMINI_KEY})
    monkeypatch.setenv("COST_CAP_EUR_PER_DAY", "0")  # plafond atteint : /v1/ai/complete refuse, le test passe quand même
    reset_settings_cache()
    for _ in range(2):  # hors cache : deux appels réels
        r = client.post("/v1/settings/ai/test", json={"provider": "gemini"}, headers=admin())
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["ok"] is True and result["error"] is None and result["model"] == "gemini-2.5-flash"
        assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0
    assert len(calls) == 2
    assert calls[0]["url"] == f"{GEMINI_BASE_URL}/chat/completions" and calls[0]["headers"]["Authorization"] == f"Bearer {GEMINI_KEY}"
    assert calls[0]["json"]["model"] == "gemini-2.5-flash" and "OK" in calls[0]["json"]["messages"][0]["content"]
    with session_scope() as s:
        journal = s.query(LlmCall).all()
        assert [(c.provider, c.task, c.prompt_tag, c.ok, c.cached) for c in journal] == [("gemini", "extract", "settings:test", True, False)] * 2
    assert client.post("/v1/ai/complete", json={"prompt": "x"}, headers=api_key("generate")).status_code == 429


def test_connection_test_failure_returns_ok_false_without_secret(client, fake_chat):
    _, replies = fake_chat
    put(client, {"provider": "gemini", "api_key": GEMINI_KEY})
    replies.append(chat_response(status=401))
    r = client.post("/v1/settings/ai/test", json={"provider": "gemini"}, headers=admin())
    assert r.status_code == 200
    result = r.json()
    assert result["ok"] is False and "HTTP 401" in result["error"] and "clé refusée" in result["error"]
    assert GEMINI_KEY not in r.text
    with session_scope() as s:
        call = s.query(LlmCall).one()
        assert call.ok is False and call.provider == "gemini" and GEMINI_KEY not in call.error


def test_connection_test_never_500_and_handles_unconfigured(client, monkeypatch):
    class Broken(FakeProvider):
        def _complete(self, task, prompt_text, images=None):  # noqa: ANN001, ARG002
            raise RuntimeError(f"panne interne {CLAUDE_KEY}")

    put(client, {"provider": "claude", "api_key": CLAUDE_KEY})
    with monkeypatch.context() as m:
        m.setattr("pai.api.settings_ai.build_from_config", lambda cfg: Broken(name=cfg.id))
        r = client.post("/v1/settings/ai/test", json={"provider": "claude"}, headers=admin())
    assert r.status_code == 200 and r.json()["ok"] is False and CLAUDE_KEY not in r.text and "RuntimeError" in r.json()["error"]
    with session_scope() as s:
        assert CLAUDE_KEY not in s.query(LlmCall).one().error  # même le journal ne garde pas la clé
    for pid, words in (("mistral", "Clé d'API manquante"), ("local", "Ollama injoignable"), ("null", "désactivé")):
        result = client.post("/v1/settings/ai/test", json={"provider": pid}, headers=admin()).json()
        assert result["ok"] is False and words in result["error"] and result["latency_ms"] == 0
    assert client.post("/v1/settings/ai/test", json={"provider": "gpt"}, headers=admin()).status_code == 422


def test_connection_test_with_fake_provider_success(client, monkeypatch):
    class Echo(FakeProvider):
        def respond(self, task, prompt):  # noqa: ANN001, ARG002
            return {"ok": True}

    monkeypatch.setattr("pai.api.settings_ai.build_from_config", lambda cfg: Echo(name=cfg.id))
    result = client.post("/v1/settings/ai/test", json={"provider": "mistral"}, headers=admin()).json()
    assert result == {"ok": True, "latency_ms": result["latency_ms"], "model": "fake-extract", "error": None}


# ── Fournisseur effectif : /v1/status, passerelle IA et pipeline ─────────────
def test_status_modes(client, monkeypatch):
    base = client.get("/v1/status", headers=api_key("read"))
    assert base.status_code == 200
    assert base.json() == {"engine_v": base.json()["engine_v"], "ai_mode": "DEGRADED", "active_provider": "null", "db": "ok"}
    put(client, {"active": "gemini", "provider": "gemini", "api_key": GEMINI_KEY})
    assert client.get("/v1/status", headers=api_key("read")).json()["ai_mode"] == "REMOTE"
    put(client, {"active": "local"})
    assert client.get("/v1/status", headers=api_key("read")).json() | {"engine_v": ""} == {
        "engine_v": "", "ai_mode": "DEGRADED", "active_provider": "local", "db": "ok"}  # modèle local absent
    put(client, {"provider": "local", "model": "llama3.1:8b"})
    assert client.get("/v1/status", headers=api_key("read")).json()["ai_mode"] == "DEGRADED"  # Ollama injoignable
    import pai.providers.ollama as ollama

    monkeypatch.setattr(ollama, "probe", lambda base_url, ttl=30.0, timeout=2.0: fake_ollama_state("llama3.1:8b"))
    assert client.get("/v1/status", headers=api_key("read")).json()["ai_mode"] == "LOCAL"
    assert client.get("/v1/status").status_code == 401


def test_db_settings_override_env_for_gateway_and_pipeline(client, fake_chat):
    calls, replies = fake_chat
    assert client.post("/v1/ai/complete", json={"prompt": "Bonjour"}, headers=api_key("generate")).status_code == 503  # env : null
    put(client, {"active": "mistral", "provider": "mistral", "api_key": MISTRAL_KEY})
    replies.append(chat_response("Bonjour !"))
    r = client.post("/v1/ai/complete", json={"prompt": "Bonjour"}, headers=api_key("generate"))
    assert r.status_code == 200 and r.json() | {"tier": "", "cached": False} == {"text": "Bonjour !", "model": "mistral-large-latest",
                                                                             "truncated": False, "tier": "", "cached": False}
    assert r.json()["tier"] == "external"
    assert calls[-1]["url"] == f"{MISTRAL_BASE_URL}/chat/completions" and calls[-1]["headers"]["Authorization"] == f"Bearer {MISTRAL_KEY}"
    replies.extend([chat_response("{}"), chat_response("{}")])
    analysis = client.post("/v1/analyze-job", json={"offer_text": TEST_OFFER}, headers=api_key("analyze"))
    assert analysis.status_code == 200 and analysis.json()["provider"] == "mistral"
    with session_scope() as s:
        assert {c.provider for c in s.query(LlmCall)} == {"mistral"}
        assert s.get(AppSetting, "ai").value["active"] == "mistral"
