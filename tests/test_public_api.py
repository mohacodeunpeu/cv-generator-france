"""API /api : santé, entrées directes (texte, URL, PDF, HTML, DOCX), analyses A et B, optimisation, validation PDF,
pack asynchrone et versions, état du système, usage de l'IA, cache, request_id. SQLite et PostgreSQL, sans IA ni réseau."""

from __future__ import annotations

import io
import json
import logging
import zipfile

import pytest

from pai.api import jobs
from pai.db.models import LlmCall
from pai.db.session import session_scope
from pai.ingest import UrlIngestError
from tests.conftest import TEST_OFFER
from tests.test_api import api_key, client  # noqa: F401 — fixture partagée (SQLite + PostgreSQL)
from tests.test_ats import CV_TEXT


def _pdf(text: str) -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for line in text.splitlines():
        page.insert_text((50, y), line, fontsize=10)
        y += 14
    return doc.tobytes()


def _docx(paragraphs: list[str]) -> bytes:
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


HTML_OFFER = ("<html><head><title>Offre</title><script type='application/ld+json'>" + json.dumps({
    "@context": "https://schema.org", "@type": "JobPosting", "title": "Business Developer Junior",
    "hiringOrganization": {"@type": "Organization", "name": "Acme SaaS"},
    "description": TEST_OFFER.replace("\n", "<br>")}) + "</script></head><body><main>Chargement</main></body></html>")


def test_health_ready_and_request_id(client, caplog):  # noqa: F811
    caplog.set_level(logging.INFO, logger="pai.events")
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and len(r.headers["x-request-id"]) >= 8
    r = client.get("/api/ready", headers={"X-Request-ID": "jobagent-1234abcd"})
    body = r.json()
    assert r.status_code == 200 and body["ready"] is True, body
    assert {"database", "migrations", "storage", "ai", "config"} <= set(body["checks"])
    assert body["checks"]["ai"]["mode"] == "DEGRADED"                      # sans IA : prêt quand même
    assert r.headers["x-request-id"] == "jobagent-1234abcd"               # identifiant de l'appelant repris
    assert client.get("/api/health", headers={"X-Request-ID": "x;rm -rf"}).headers["x-request-id"] != "x;rm -rf"
    events = [json.loads(rec.message) for rec in caplog.records if rec.name == "pai.events"]
    req = [e for e in events if e["event"] == "request" and e.get("path") == "/api/ready"]
    assert req and req[0]["request_id"] == "jobagent-1234abcd" and req[0]["status"] == 200


def test_auth_and_scopes(client):  # noqa: F811
    assert client.post("/api/jobs/analyze", json={"offer_text": TEST_OFFER}).status_code == 401
    assert client.post("/api/jobs/analyze", json={"offer_text": TEST_OFFER}, headers=api_key("read")).status_code == 403
    assert client.get("/api/system/status").status_code == 401


def test_ingest_text_html_pdf_docx_and_errors(client, monkeypatch):  # noqa: F811
    h = api_key("analyze")
    r = client.post("/api/jobs/ingest", json={"offer_text": TEST_OFFER, "company": "Acme SaaS"}, headers=h)
    assert r.status_code == 200 and r.json()["offer"]["source_type"] == "text"
    r = client.post("/api/jobs/ingest", files={"offer_file": ("offre.html", HTML_OFFER.encode(), "text/html")}, headers=h)
    offer = r.json()["offer"]
    assert r.status_code == 200 and offer["source_type"] == "html" and offer["company_hint"] == "Acme SaaS", r.text
    r = client.post("/api/jobs/ingest", files={"offer_file": ("offre.pdf", _pdf(TEST_OFFER), "application/pdf")}, headers=h)
    assert r.status_code == 200 and r.json()["offer"]["source_type"] == "pdf" and "HubSpot" in r.json()["offer"]["text"]
    r = client.post("/api/jobs/ingest", files={"offer_file": ("offre.docx", _docx(TEST_OFFER.splitlines()), "")}, headers=h)
    assert r.status_code == 200 and "Prospecter" in r.json()["offer"]["text"]
    r = client.post("/api/jobs/ingest", files={"offer_file": ("image.png", b"\x89PNG\r\n\x1a\n" + bytes(200), "image/png")}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unreadable"
    assert client.post("/api/jobs/ingest", json={}, headers=h).json()["detail"]["code"] == "missing_offer"

    def blocked(url):  # noqa: ANN001
        raise UrlIngestError("anti_bot", "Le serveur PAI n'a pas pu récupérer cette URL (HTTP 403) : protection anti-robot.")

    monkeypatch.setattr("pai.api.public.offer_from_url", blocked)
    r = client.post("/api/jobs/ingest", json={"offer_url": "https://jobs.example.fr/offre/1"}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "anti_bot" and "Claude" not in r.text


def test_analyze_offer_with_profile_and_cache(client):  # noqa: F811
    h = api_key("analyze")
    r = client.post("/api/jobs/analyze", json={"offer_text": TEST_OFFER, "company": "Acme SaaS", "ai": "none"}, headers=h)
    body = r.json()
    assert r.status_code == 200 and body["cache"] == "miss", r.text
    report = body["report"]
    assert report["score"]["label"] == "Score PAI" and 0 <= report["score"]["value"] <= 100
    proven = {x["text"].lower() for x in report["requirements"]["proven"]}
    assert "hubspot" in proven and "crm" in proven
    again = client.post("/api/jobs/analyze", json={"offer_text": TEST_OFFER, "company": "Acme SaaS", "ai": "none"}, headers=h).json()
    assert again["cache"] == "hit" and again["report"]["score"] == report["score"]   # même entrée → même résultat


def test_cv_analyze_modes_a_and_b(client):  # noqa: F811
    h = api_key("analyze")
    a = client.post("/api/cv/analyze", json={"cv_text": CV_TEXT}, headers=h).json()
    assert a["mode"] == "cv_only" and [d["id"] for d in a["report"]["dimensions"]][:2] == ["parsing", "structure"]
    b = client.post("/api/cv/analyze", data={"offer_text": TEST_OFFER},
                    files={"cv_file": ("cv.pdf", _pdf(CV_TEXT), "application/pdf")}, headers=h).json()
    assert b["mode"] == "cv_offer" and b["report"]["score"]["complete"] is False      # pas de validation ligne à ligne
    dims = {d["id"]: d for d in b["report"]["dimensions"]}
    assert dims["parsing"]["available"] and dims["parsing"]["measured"]                # PDF réel scanné
    assert "Preuves tirées du CV fourni" in b["report"]["source"]
    bad = client.post("/api/cv/analyze", files={"cv_file": ("cv.pdf", b"%PDF-1.4 vide", "application/pdf")}, headers=h)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] in ("unreadable", "no_text")


def test_cv_validate_and_optimize(client):  # noqa: F811
    h = api_key("analyze")
    r = client.post("/api/cv/validate", files={"cv_file": ("cv.pdf", _pdf(CV_TEXT), "application/pdf")},
                    data={"source_text": "Qualifié 25 leads par mois\nLigne absente du PDF"}, headers=h).json()["report"]
    checks = {c["id"]: c["status"] for c in r["checks"]}
    assert checks["text"] == "OK" and checks["lost"] == "ERROR" and r["roundtrip"]["lost"] == ["Ligne absente du PDF"]
    o = client.post("/api/cv/optimize", json={"offer_text": TEST_OFFER, "ai": "none"}, headers=h).json()
    assert o["validation"]["factuality"] == 100 and o["cv"]["lines"]
    assert all(ln["fact_ids"] or ln["section"] == "headline" for ln in o["cv"]["lines"])
    assert o["changes"]["rule"].startswith("Aucune ligne sans preuve")


def test_application_prepare_async_versions_and_status(client):  # noqa: F811
    h = api_key("generate", "read")
    r = client.post("/api/application/prepare", json={"offer_text": TEST_OFFER, "company": "Acme SaaS", "source": "jobagent"},
                    headers=h | {"Idempotency-Key": "ja-offre-42"})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    same = client.post("/api/application/prepare", json={"offer_text": TEST_OFFER, "company": "Acme SaaS"},
                       headers=h | {"Idempotency-Key": "ja-offre-42"})
    assert same.json()["job_id"] == job_id                                        # jamais de doublon
    assert jobs.run_once()
    done = client.get(f"/api/jobs/{job_id}", headers=h).json()
    assert done["status"] == "DONE", done
    res = done["result"]
    assert res["application_id"].startswith("app_") and res["version_id"].startswith("pack_")
    assert res["pai_score"] == res["ats"]["score"]["value"] and res["ats"]["score"]["complete"] is True
    assert res["application_pack"]["cv_pdf"] and res["versions"]["template"]
    letter = res["letter_text"]                                                   # texte du PDF, pour un formulaire
    assert letter.startswith(("Madame", "Monsieur", "Bonjour")) and "\n\n" in letter and "MBA" not in letter
    v = client.get(f"/api/application/{res['version_id']}", headers=h).json()
    assert v["latest"]["pai_score"] == res["pai_score"] and any(n.endswith(".pdf") for n in v["latest"]["files"])
    app = client.get(f"/api/application/{res['application_id']}", headers=h).json()
    assert app["versions"][0]["version_id"] == res["version_id"]
    assert client.get("/api/application/pack_inconnu", headers=h).status_code == 404
    status = client.get("/api/system/status", headers=h).json()
    items = {i["id"]: i for i in status["items"]}
    assert set(items) >= {"pai", "ats", "api", "database", "ai", "local_model", "cache", "cloudflare", "jobagent"}
    assert items["ats"]["status"] == "OK" and items["jobagent"]["status"] == "OK"       # appel « source=jobagent » vu


def test_ai_usage_counts_cache_hits(client):  # noqa: F811
    with session_scope() as s:
        for cached in (False, True, True):
            s.add(LlmCall(task="letter", provider="local", model="qwen3:4b", input_hash="h", tokens_in=100, tokens_out=50,
                          latency_ms=1200, cached=cached, tier="large"))
    u = client.get("/api/ai/usage", headers=api_key("read")).json()
    assert u["total_requests"] == 3 and u["cache_hit"] == 2 and u["cache_hit_rate"] == 67 and u["cost_eur"] == 0
    row = u["by_model"][0]
    assert (row["provider"], row["tier"], row["tokens_in"]) == ("local", "large", 300)


def test_corpus_endpoint(client):  # noqa: F811
    c = client.get("/api/corpus", headers=api_key("read")).json()
    assert "families" in c and c["thresholds"] == {"top20": 10, "top40": 25}


def test_system_status_cloudflare_tunnel(client, monkeypatch):  # noqa: F811
    from pai.api import public
    from pai.config import get_settings

    monkeypatch.setattr(get_settings(), "compose_profiles", "cloudflare,ai-local")
    monkeypatch.setattr(get_settings(), "base_url", "https://pai.example.org")
    h = api_key("read")
    monkeypatch.setattr(public, "tunnel_state", lambda url: None)
    items = {i["id"]: i for i in client.get("/api/system/status", headers=h).json()["items"]}
    assert items["cloudflare"]["status"] == "ERROR" and "injoignable" in items["cloudflare"]["detail"]
    monkeypatch.setattr(public, "tunnel_state", lambda url: {"connections": 4})
    items = {i["id"]: i for i in client.get("/api/system/status", headers=h).json()["items"]}
    assert items["cloudflare"]["status"] == "OK" and "4\u00a0connexions actives" in items["cloudflare"]["detail"]
    monkeypatch.setattr(get_settings(), "compose_profiles", "cloudflare,caddy")        # deux accès : aucun n'est déduit
    assert get_settings().access == ""


def test_client_ip_from_cloudflare_only_behind_the_tunnel(monkeypatch):
    import asyncio

    from pai.api.security import CloudflareClientIp
    from pai.config import get_settings

    seen = {}

    async def app(scope, receive, send):  # noqa: ANN001, ANN202
        seen["client"] = scope["client"]

    def call(headers):  # noqa: ANN001, ANN202
        scope = {"type": "http", "client": ("10.0.0.2", 5000), "headers": headers}
        asyncio.run(CloudflareClientIp(app)(scope, None, None))
        return seen["client"][0]

    spoof = [(b"x-forwarded-for", b"198.51.100.7"), (b"cf-connecting-ip", b"203.0.113.9")]
    monkeypatch.setattr(get_settings(), "pai_access", "caddy")
    assert call(spoof) == "10.0.0.2"                                   # Caddy : l'en-tête serait falsifiable, ignoré
    monkeypatch.setattr(get_settings(), "pai_access", "cloudflare")
    assert call(spoof) == "203.0.113.9"                                # tunnel : l'IP posée par Cloudflare
    assert call([(b"cf-connecting-ip", b"pas-une-ip")]) == "10.0.0.2"
