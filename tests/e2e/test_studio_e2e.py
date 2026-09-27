"""Test e2e de PAI Studio : vrai Chromium, doublure de window.claude (tests/e2e/claude_mock.js).

Parcours : tableau de bord → nouvelle candidature (STANDARD) → pack → CV Studio → lettre → export PDF/ZIP →
profil → mobile. Vérifie aussi que les pièges de la doublure IA (MBA, faux chiffre, fait UNVERIFIED,
salaire inventé) n'atteignent jamais le document final. Captures d'écran → docs/proofs/studio/
(profil FICTIF « Camille Test » uniquement).
"""

from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROOFS = ROOT / "docs" / "proofs" / "studio"
OFFER = ("Business Developer Junior (H/F) — CDI — Paris\nAcme SaaS édite un logiciel pour les PME françaises depuis 2015.\n\n"
         "Vos missions\n- Prospecter de nouveaux clients PME par téléphone et LinkedIn.\n- Suivre votre pipeline dans HubSpot.\n\n"
         "Votre profil\n- Anglais courant requis.\n- Maîtrise d'un CRM indispensable.")

pw = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def studio_url():
    import sys

    sys.path.insert(0, str(ROOT / "web"))
    from build_studio import LIBS, build, ensure_vendor  # type: ignore[import-not-found]

    dist = ROOT / "web" / "dist"
    build(dist / "pai_studio.html")
    for name in LIBS:
        ensure_vendor(name)
    page = (dist / "pai_studio.html").read_text(encoding="utf-8")
    skeleton = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                "<style>:root{color-scheme:light}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>")
    (dist / "_e2e.html").write_text(skeleton + page + "</body></html>", encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(dist))
    handler.log_message = lambda *a, **k: None  # type: ignore[assignment]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/_e2e.html"
    server.shutdown()


def _page(browser, url, width, height, seed):
    ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
    page = ctx.new_page()
    vendor = ROOT / "web" / "vendor"
    page.route("https://cdn.jsdelivr.net/npm/**", lambda r: r.fulfill(path=str(vendor / r.request.url.rsplit("/", 1)[-1]), content_type="application/javascript"))
    page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, body="", content_type="text/css"))
    page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
    page.add_init_script(f"window.__PAI_SEED__ = {json.dumps(seed)};")
    page.add_init_script(path=str(ROOT / "tests" / "e2e" / "claude_mock.js"))
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    return ctx, page, errors


def test_studio_full_flow(studio_url):
    PROOFS.mkdir(parents=True, exist_ok=True)
    profile = json.loads((ROOT / "tests" / "fixtures" / "profile_test.json").read_text(encoding="utf-8"))
    seed = {"pai/profile": profile}
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx, page, errors = _page(browser, studio_url, 1360, 900, seed)
        page.get_by_text("Bonjour Camille").wait_for(timeout=15000)
        page.screenshot(path=str(PROOFS / "desktop_1_dashboard.png"), full_page=True)

        page.locator("#nav button[data-arg=nouvelle]").click()
        page.fill("#f-offer", OFFER)
        page.fill("#f-questions", "Quelle est votre disponibilité ?\nQuelles sont vos prétentions salariales ?")
        page.get_by_role("button", name="Analyser et générer").click()
        page.get_by_role("button", name="Ouvrir le pack").wait_for(timeout=90000)
        page.screenshot(path=str(PROOFS / "desktop_2_generation.png"), full_page=True)

        page.get_by_role("button", name="Ouvrir le pack").click()
        page.get_by_role("tab", name="Synthèse").wait_for()
        page.screenshot(path=str(PROOFS / "desktop_3_pack_synthese.png"), full_page=True)

        pack = page.evaluate("() => { const s = window.__PAI_MOCK__.store; for (const [k, v] of s) if (k.startsWith('packs/')) return v; return null; }")
        cv = pack["cvs"][0]
        texts = " ".join(line["text"] for line in cv["doc"]["lines"])
        assert "MBA" not in texts, "le piège MBA a atteint le CV"
        assert "40+" not in texts, "le faux chiffre a atteint le CV"
        assert "Licence de gestion" not in texts, "un fait UNVERIFIED a atteint le CV"
        assert cv["report"]["factuality"] == 100.0
        assert any("MBA" in r["text"] for r in cv["doc"]["removed_lines"])
        assert pack["letters"][0]["report"]["factuality"] == 100.0
        salary = next(a for a in pack["answers"] if "salari" in a["question"])
        assert salary["confidence"] == "BLOCKED" and not salary["answer"], "salaire inventé non bloqué"
        assert pack["strategy"]["best"]["photo_mode"] == "OFF"
        assert pack["status"] == "DRAFT"  # profil non validé
        assert cv["qa"]["pages"] == 1 and cv["qa"]["ok"], cv["qa"]

        page.get_by_role("tab", name="CV Studio").click()
        page.locator("#cv-sheet .sheet").wait_for()
        page.screenshot(path=str(PROOFS / "desktop_4_cv_studio.png"), full_page=True)
        page.get_by_role("tab", name="Letter Studio").click()
        page.screenshot(path=str(PROOFS / "desktop_5_letter_studio.png"), full_page=True)

        page.get_by_role("tab", name="Export").click()
        page.get_by_role("button", name="CV (PDF)").click()
        page.get_by_role("button", name="Pack complet (ZIP)").click()
        page.wait_for_function("() => window.__PAI_MOCK__.saved.length >= 2", timeout=30000)
        saved = page.evaluate("() => window.__PAI_MOCK__.saved")
        assert saved[0]["head"] == "%PDF-" and saved[0]["size"] > 20000, saved
        assert saved[1]["head"].startswith("PK") and saved[1]["filename"].endswith(".zip"), saved

        page.locator("#nav button[data-arg=profil]").click()
        page.get_by_role("button", name="Valider le profil v3").click()
        page.get_by_text("validé").first.wait_for()
        page.screenshot(path=str(PROOFS / "desktop_6_profil.png"), full_page=True)
        for view, name in (("arene", "7_arene"), ("apprentissage", "8_apprentissage"), ("jobagent", "9_jobagent"),
                           ("versions", "10_versions"), ("reglages", "11_reglages"), ("lab", "12_training_lab")):
            page.locator(f"#nav button[data-arg={view}]").click()
            page.wait_for_timeout(150)
            page.screenshot(path=str(PROOFS / f"desktop_{name}.png"), full_page=True)
        assert not errors, errors
        ctx.close()

        mctx, mpage, merrors = _page(browser, studio_url, 390, 844, seed)
        mpage.get_by_text("Bonjour Camille").wait_for(timeout=15000)
        mpage.screenshot(path=str(PROOFS / "mobile_1_dashboard.png"), full_page=True)
        mpage.locator("#tabbar button[data-arg=nouvelle]").click()
        mpage.fill("#f-offer", OFFER)
        mpage.get_by_role("button", name="Analyser et générer").click()
        mpage.get_by_role("button", name="Ouvrir le pack").wait_for(timeout=90000)
        mpage.get_by_role("button", name="Ouvrir le pack").click()
        mpage.get_by_role("tab", name="CV Studio").click()
        mpage.locator("#cv-sheet .sheet").wait_for()
        mpage.screenshot(path=str(PROOFS / "mobile_2_cv_studio.png"), full_page=True)
        mpage.locator("#tabbar button[data-arg=profil]").click()
        mpage.screenshot(path=str(PROOFS / "mobile_3_profil.png"), full_page=True)
        width = mpage.evaluate("() => document.documentElement.scrollWidth")
        assert width <= 390, f"défilement horizontal sur mobile ({width}px)"
        assert not merrors, merrors
        mctx.close()
        browser.close()
