"""Serveur PAI : connexion, sessions, CSRF, limitation, clés d'API, jobs idempotents, URL signées, en-têtes, routes historiques.

Tourne sur SQLite, et sur PostgreSQL si PAI_TEST_PG_URL est défini (ex. postgresql+psycopg://pai:***@127.0.0.1:5432/pai_test).
Profil fictif « Camille Test » uniquement.
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from pai.api import auth, jobs
from pai.api.app import STUDIO_SERVER, create_app
from pai.api.security import secret_key, sign
from pai.config import reset_settings_cache
from pai.db.models import Base, Claim, Generation, LlmCall, ProfileVersion, StoredFile
from pai.db.repo import save_profile_doc
from pai.db.session import get_engine, reset_engines, session_scope
from tests.conftest import TEST_OFFER

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(params=["sqlite", "postgresql"])
def client(request, tmp_path, monkeypatch, profile):
    if request.param == "postgresql":
        url = os.environ.get("PAI_TEST_PG_URL", "")
        if not url:
            pytest.skip("PAI_TEST_PG_URL non défini")
    else:
        url = f"sqlite:///{tmp_path}/pai.db"
    for key, value in {"DB_URL": url, "SECRET_KEY": "k" * 48, "ENVIRONMENT": "test", "BASE_URL": "https://testserver",
                       "PAI_AI_PROVIDER": "null", "COOKIE_SECURE": "true", "LOGIN_RATE_LIMIT": "5"}.items():
        monkeypatch.setenv(key, value)
    reset_settings_cache()
    secret_key.cache_clear()
    auth.reset_login_limiter()
    reset_engines()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with session_scope() as s:
        save_profile_doc(s, profile)
    auth.create_user("camille", PASSWORD)
    if not STUDIO_SERVER.exists():
        import sys

        from pai import paths

        sys.path.insert(0, str(paths.WEB_DIR))
        from build_studio import build  # type: ignore[import-not-found]

        build(server=True)
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c
    Base.metadata.drop_all(engine)
    reset_engines()
    secret_key.cache_clear()


def login(c: TestClient, username: str = "camille", password: str = PASSWORD):
    page = c.get("/login")
    token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    return c.post("/login", data={"username": username, "password": password, "csrf": token}, follow_redirects=False)


def session_csrf(c: TestClient) -> str:
    page = c.get("/")
    assert page.status_code == 200, page.text[:200]
    return re.search(r'name="pai-csrf" content="([^"]+)"', page.text).group(1)


def api_key(*scopes: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_api_key('test', scopes)}"}


def path_of(url: str) -> str:
    return urlparse(url).path


# ── En-têtes et connexion ────────────────────────────────────────────────────
def test_health_and_security_headers(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer" and "noindex" in h["X-Robots-Tag"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"] and "unsafe-eval" not in h["Content-Security-Policy"]


def test_ui_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/v1/profile").status_code == 401
    assert client.get("/openapi.json").status_code == 401


def test_login_sets_hardened_cookie_and_serves_studio_with_nonce(client):
    assert login(client, password="mauvais-mot-de-passe").status_code == 401
    r = login(client)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "pai_session=" in cookie and "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    page = client.get("/")
    nonce = re.search(r"'nonce-([^']+)'", page.headers["Content-Security-Policy"]).group(1)
    inline = re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>", page.text)
    assert inline and all(f'nonce="{nonce}"' in attrs for attrs in inline)
    assert 'name="pai-csrf"' in page.text and "window.claude = { use:" in page.text
    assert page.headers["Cache-Control"] == "no-store"


def test_login_form_requires_its_csrf_token(client):
    client.get("/login")
    r = client.post("/login", data={"username": "camille", "password": PASSWORD, "csrf": "forge"}, follow_redirects=False)
    assert r.status_code == 403


def test_login_rate_limit(client):
    for _ in range(5):
        assert login(client, password="faux-mot-de-passe-12").status_code == 401
    r = login(client)  # même le bon mot de passe est refusé pendant la fenêtre
    assert r.status_code == 429


def test_session_writes_require_csrf_header(client):
    login(client)
    csrf = session_csrf(client)
    body = {"element": "titre", "rating": 1}
    assert client.post("/v1/feedback", json=body).status_code == 403
    assert client.post("/v1/feedback", json=body, headers={"X-CSRF-Token": "faux"}).status_code == 403
    assert client.post("/v1/feedback", json=body, headers={"X-CSRF-Token": csrf}).status_code == 201


def test_logout_revokes_session_server_side(client):
    login(client)
    csrf = session_csrf(client)
    stolen = client.cookies.get("pai_session")
    r = client.post("/logout", headers={"X-CSRF-Token": csrf}, follow_redirects=False)
    assert r.status_code == 303
    client.cookies.clear()
    client.cookies.set("pai_session", stolen, domain="testserver")  # rejouer l'ancien cookie
    assert client.get("/v1/profile").status_code == 401
    assert client.get("/", follow_redirects=False).status_code == 303


def test_first_login_forces_password_change_and_revokes_old_sessions(client):
    auth.create_user("camille", PASSWORD, must_change=True)
    r = login(client)
    assert r.headers["location"] == "/change-password"
    assert client.get("/", follow_redirects=False).headers["location"] == "/change-password"
    page = client.get("/change-password")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    old_cookie = client.cookies.get("pai_session")
    assert client.post("/change-password", data={"old": PASSWORD, "new": "court", "csrf": csrf}).status_code == 400
    r = client.post("/change-password", data={"old": PASSWORD, "new": "un-nouveau-mot-de-passe-solide", "csrf": csrf},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert client.get("/").status_code == 200
    client.cookies.clear()
    client.cookies.set("pai_session", old_cookie, domain="testserver")  # rejouer la session d'avant le changement
    assert client.get("/v1/profile").status_code == 401
    client.cookies.clear()
    assert login(client, password="un-nouveau-mot-de-passe-solide").status_code == 303


# ── Clés d'API ──────────────────────────────────────────────────────────────
def test_api_key_scopes(client):
    read = api_key("read")
    assert client.get("/v1/profile", headers=read).status_code == 200
    assert client.post("/v1/analyze-job", json={"offer_text": TEST_OFFER}, headers=read).status_code == 403
    assert client.get("/v1/profile", headers={"Authorization": "Bearer pai_inconnue"}).status_code == 401
    assert client.get("/openapi.json", headers=read).json()["paths"]["/v1/generate-application-pack"]


def test_analyze_job_and_strategy(client):
    headers = api_key("analyze")
    r = client.post("/v1/analyze-job", json={"offer_text": TEST_OFFER}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["analysis"]["sector_id"] == "business_development" and data["analysis"]["contract"] == "CDI"
    assert 0 <= data["match"]["match"] <= 100 and data["provider"] == "null"
    s = client.post("/v1/generate-strategy", json={"offer_text": TEST_OFFER}, headers=headers).json()
    assert s["strategy"]["best"]["title"]
    assert client.post("/v1/analyze-job", json={"offer_text": "trop court"}, headers=headers).status_code == 422


# ── Génération asynchrone, idempotence, fichiers signés ─────────────────────
def test_async_pack_is_idempotent_persisted_and_downloadable(client):
    headers = api_key("generate", "read") | {"Idempotency-Key": "offre-acme-1"}
    first = client.post("/v1/generate-application-pack", json={"offer_text": TEST_OFFER, "questions": "Pourquoi nous ?"}, headers=headers)
    second = client.post("/v1/generate-application-pack", json={"offer_text": TEST_OFFER}, headers=headers)
    assert first.status_code == 202 and first.json()["job_id"] == second.json()["job_id"]
    job_id = first.json()["job_id"]
    assert client.get(f"/v1/jobs/{job_id}", headers=headers).json()["status"] == "PENDING"
    assert jobs.run_once() is True and jobs.run_once() is False  # un seul job, aucun doublon
    job = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "DONE", job["error"]
    result = job["result"]
    assert result["status"] == "DRAFT"  # profil non validé → jamais FINAL (A3)
    assert result["quality_scores"]["factuality_cv"] == 100 and result["quality_scores"]["factuality_letter"] == 100
    assert [s["stage"] for s in job["progress"]][-1] == "pack"
    pack = result["application_pack"]
    assert "Camille" not in pack["cv_pdf"] and "Test" not in pack["cv_pdf"]  # aucune donnée personnelle dans l'URL
    cv = client.get(path_of(pack["cv_pdf"]))  # l'URL signée suffit (pas de session)
    assert cv.status_code == 200 and cv.content.startswith(b"%PDF") and cv.headers["content-type"] == "application/pdf"
    assert client.get(path_of(pack["zip"])).content.startswith(b"PK")
    tampered = path_of(pack["cv_pdf"])[:-3] + "xyz"
    assert client.get(tampered).status_code == 403
    with session_scope() as s:
        gen = s.get(Generation, result["generation_id"])
        assert gen is not None and gen.status == "DRAFT" and gen.versions["engine_v"]
        assert s.query(Claim).filter_by(generation_id=gen.id).count() > 5
        assert s.query(ProfileVersion).count() == 1
        assert s.query(StoredFile).filter_by(generation_id=gen.id).count() == 3
    versions = client.get("/v1/versions", headers=headers).json()
    assert versions["recent_generations"][0]["generation_id"] == result["generation_id"]


def test_two_generations_of_same_offer_are_distinct_and_immutable(client):
    headers = api_key("generate")
    a = client.post("/v1/generate-cv", json={"offer_text": TEST_OFFER}, headers=headers).json()
    b = client.post("/v1/generate-cv", json={"offer_text": TEST_OFFER}, headers=headers).json()
    assert a["generation_id"] != b["generation_id"] and a["cv_version"] == b["cv_version"]


def test_signed_file_url_expires(client, monkeypatch):
    with session_scope() as s:
        s.add(StoredFile(id="fil_test", name="x.pdf", content_type="application/pdf", data=b"%PDF-1.7"))
    token = sign({"f": "fil_test"}, "file")
    assert client.get(f"/v1/files/{token}").status_code == 200
    monkeypatch.setenv("FILE_URL_TTL_SECONDS", "1")
    reset_settings_cache()
    time.sleep(2.2)
    assert client.get(f"/v1/files/{token}").status_code == 403
    assert client.get(f"/v1/files/{sign({'f': 'fil_test'}, 'session')}").status_code == 403  # mauvais usage du jeton


# ── Magasin de documents de l'interface ──────────────────────────────────────
def test_store_roundtrip_and_limits(client):
    login(client)
    h = {"X-CSRF-Token": session_csrf(client)}
    assert client.put("/v1/store/doc?path=packs/p1", json={"data": {"n": 2, "title": "B"}}, headers=h).json()["version"] == 1
    assert client.put("/v1/store/doc?path=packs/p2", json={"data": {"n": 1, "title": "A"}}, headers=h).status_code == 200
    assert client.put("/v1/store/doc?path=packs/p1", json={"data": {"n": 3, "title": "B"}}, headers=h).json()["version"] == 2
    assert client.get("/v1/store/doc?path=packs/p1").json()["data"]["n"] == 3
    docs = client.get("/v1/store/query?collection=packs&order_by=n&direction=desc").json()["docs"]
    assert [d["id"] for d in docs] == ["p1", "p2"]
    assert client.put("/v1/store/doc?path=packs", json={"data": {}}, headers=h).status_code == 400
    assert client.put("/v1/store/doc?path=../etc/passwd", json={"data": {}}, headers=h).status_code == 400
    big = {"data": {"x": "a" * (256 * 1024)}}
    assert client.put("/v1/store/doc?path=packs/big", json=big, headers=h).status_code == 413
    assert client.delete("/v1/store/doc?path=packs/p2", headers=h).json()["deleted"] is True
    assert client.get("/v1/store/doc?path=packs/p2").json()["exists"] is False


# ── IA de l'interface : mode dégradé, plafond journalier, journal des appels ──
def test_ai_complete_degraded_mode(client):
    r = client.post("/v1/ai/complete", json={"prompt": "Bonjour"}, headers=api_key("generate"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_granted"


def test_ai_complete_daily_cost_cap_and_call_journal(client, monkeypatch):
    from tests.fake_provider import FakeProvider

    class Echo(FakeProvider):
        def respond(self, task, prompt):  # noqa: ANN001
            return {"ok": True, "task": task}

    def fake_get_provider(name=None, *, budget_eur=None, cache_dir=None):  # noqa: ANN001
        return Echo(budget_eur=budget_eur, price_per_call=0.01)

    monkeypatch.setattr("pai.api.v1.get_provider", fake_get_provider)
    monkeypatch.setenv("COST_CAP_EUR_PER_DAY", "0.015")
    reset_settings_cache()
    headers = api_key("generate")
    first = client.post("/v1/ai/complete", json={"prompt": "x", "json": True, "tier": "quick"}, headers=headers)
    assert first.status_code == 200 and first.json()["json"] == {"ok": True, "task": "extract"}
    assert client.post("/v1/ai/complete", json={"prompt": "x", "tier": "complex"}, headers=headers).status_code == 200
    third = client.post("/v1/ai/complete", json={"prompt": "x"}, headers=headers)
    assert third.status_code == 429 and third.json()["detail"]["code"] == "rate_limited"
    with session_scope() as s:
        calls = s.query(LlmCall).all()
        assert [c.task for c in calls] == ["extract", "strategy"] and round(sum(c.cost_eur for c in calls), 3) == 0.02


# ── Routes historiques ───────────────────────────────────────────────────────
def test_legacy_routes_require_auth_and_are_factual(client):
    form = {"poste": "Business Developer Junior", "entreprise": "Acme SaaS", "description": TEST_OFFER}
    assert client.post("/cv", data=form).status_code == 401
    login(client)
    r = client.post("/cv", data=form, headers={"X-CSRF-Token": session_csrf(client)})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    assert "MBA" not in text and "Camille" in text


def test_outcomes_and_feedback_validation(client):
    headers = api_key("outcomes", "feedback")
    assert client.post("/v1/outcomes", json={"stage": "interview", "occurred_at": "2026-09-01T10:00:00"}, headers=headers).status_code == 201
    assert client.post("/v1/outcomes", json={"stage": "embauche-garantie"}, headers=headers).status_code == 422
    assert client.post("/v1/outcomes", json={"stage": "applied", "generation_id": "pack_inconnu"}, headers=headers).status_code == 404
    assert client.post("/v1/feedback", json={"element": "titre", "rating": 5}, headers=headers).status_code == 422


# ── File de jobs : concurrence (PostgreSQL) et reprise après interruption ────
def test_parallel_workers_never_process_a_job_twice(client, monkeypatch, request):
    if get_engine().dialect.name != "postgresql":
        pytest.skip("SKIP LOCKED : PostgreSQL uniquement (SQLite = un seul worker, documenté)")
    import threading

    seen: list[str] = []
    lock = threading.Lock()

    def slow_process(job):  # noqa: ANN001
        time.sleep(0.2)
        with lock:
            seen.append(job.id)
        return {"ok": True}

    monkeypatch.setattr(jobs, "process", slow_process)
    ids = {jobs.enqueue("generate_pack", {"n": i}).id for i in range(6)}

    def worker():
        while jobs.run_once():
            pass

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(seen) == sorted(ids)  # chaque job exactement une fois
    assert all(jobs.get_job(i).status == "DONE" for i in ids)


def test_interrupted_job_is_requeued_then_abandoned_after_max_attempts(client):
    from datetime import timedelta

    from pai.db.models import Job, utcnow

    job = jobs.enqueue("generate_pack", {"offer_text": TEST_OFFER})
    with session_scope() as s:
        row = s.get(Job, job.id)
        row.status, row.started_at, row.attempts = "RUNNING", utcnow() - timedelta(minutes=30), 1
    assert jobs.requeue_stale() == 1 and jobs.get_job(job.id).status == "PENDING"
    with session_scope() as s:
        row = s.get(Job, job.id)
        row.status, row.started_at, row.attempts = "RUNNING", utcnow() - timedelta(minutes=30), 3
    jobs.requeue_stale()
    final = jobs.get_job(job.id)
    assert final.status == "FAILED" and "tentatives" in final.error
