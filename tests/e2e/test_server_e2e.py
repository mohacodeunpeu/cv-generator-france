"""Test e2e du serveur PAI : vrai uvicorn + vrai Chromium, CSP stricte active.

Parcours : /login → PAI Studio (même interface, pont server_shim.js) → génération (IA absente → voies
déterministes) → pack enregistré en base via /v1/store → rechargement → le pack est toujours là.
Vérifie qu'aucune violation CSP ni erreur JS ne survient. Profil FICTIF « Camille Test ».
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "mot-de-passe-de-test-e2e"
OFFER = ("Business Developer Junior (H/F) — CDI — Paris\nAcme SaaS édite un logiciel pour les PME françaises depuis 2015.\n\n"
         "Vos missions\n- Prospecter de nouveaux clients PME par téléphone et LinkedIn.\n- Suivre votre pipeline dans HubSpot.\n\n"
         "Votre profil\n- Anglais courant requis.\n- Maîtrise d'un CRM indispensable.")

pw = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server(tmp_path):
    sys.path.insert(0, str(ROOT / "web"))
    from build_studio import LIBS, build, ensure_vendor  # type: ignore[import-not-found]

    build(server=True)
    for name in LIBS:
        ensure_vendor(name)
    port = _free_port()
    env = os.environ | {"DB_URL": f"sqlite:///{tmp_path}/pai.db", "PAI_DATA_DIR": str(tmp_path / "data"), "SECRET_KEY": "e" * 48,
                        "ENVIRONMENT": "development", "PAI_INLINE_WORKER": "0", "COOKIE_SECURE": "false",
                        "PAI_AI_PROVIDER": "null", "BASE_URL": f"http://127.0.0.1:{port}"}
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "master_profile.json").write_text((ROOT / "tests" / "fixtures" / "profile_test.json").read_text(encoding="utf-8"),
                                                          encoding="utf-8")
    subprocess.run([sys.executable, "-c", f"from pai.api.auth import create_user; create_user('camille', {PASSWORD!r})"],
                   cwd=ROOT, env=env, check=True)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield base
    proc.terminate()
    proc.wait(timeout=10)


def test_server_studio_login_generate_persist(server):
    vendor = ROOT / "web" / "vendor"
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 860})
        page = ctx.new_page()
        page.route("https://cdn.jsdelivr.net/npm/**", lambda r: r.fulfill(path=str(vendor / r.request.url.rsplit("/", 1)[-1]),
                                                                           content_type="application/javascript"))
        page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, body="", content_type="text/css"))
        page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if "Content Security Policy" in m.text else None)
        page.add_init_script("document.addEventListener('securitypolicyviolation', e => console.error("
                             "'Content Security Policy violation: ' + e.violatedDirective + ' ' + e.blockedURI));")

        page.goto(f"{server}/")
        assert page.url.endswith("/login")
        page.fill("#u", "camille")
        page.fill("#p", PASSWORD)
        page.get_by_role("button", name="Se connecter").click()
        page.get_by_text("Bonjour Camille").wait_for(timeout=20000)

        page.locator("#nav button[data-arg=nouvelle]").click()
        page.fill("#f-offer", OFFER)
        page.get_by_role("button", name="Analyser et générer").click()
        page.get_by_role("button", name="Ouvrir le pack").wait_for(timeout=120000)

        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        with httpx.Client(base_url=server, cookies={"pai_session": cookies["pai_session"]}) as api:
            docs = api.get("/v1/store/query", params={"collection": "packs"}).json()["docs"]
            assert len(docs) == 1, docs
            pack = docs[0]["data"]
            cv = pack["cvs"][0]
            assert cv["report"]["factuality"] == 100.0 and pack["status"] == "DRAFT"
            assert "MBA" not in json.dumps(cv["doc"]["lines"], ensure_ascii=False)
            assert api.get("/v1/profile").json()["candidate_id"]  # profil lisible par le serveur (même format)

        page.reload()
        page.locator("#nav button[data-arg=packs]").click()
        page.get_by_text("Business Developer Junior").first.wait_for(timeout=20000)
        assert not errors, errors
        browser.close()
