"""Tests e2e de l'interface PAI : vrai Chromium, doublure de window.claude (tests/e2e/claude_mock.js).

Parcours : accueil → analyse en 9 étapes → pack (8 onglets) → CV Studio (design, brouillon, V2) → lettre →
téléchargements → Training Lab (avis → V2 → comparaison) → profil (conflit Source A / Source B, validation) →
photo FICTIVE (dégradé, jamais une vraie photo) → onboarding → réglages (test de connexion) → largeurs mobiles.
Vérifie aussi que les pièges de la doublure IA (MBA, faux chiffre, fait UNVERIFIED, salaire inventé) n'atteignent
jamais un document. Captures → data/proofs/studio/ (hors Git), ou PAI_PROOFS_DIR=docs/proofs/studio pour régénérer
les preuves versionnées (profil FICTIF « Camille Test »).
"""

from __future__ import annotations

import copy
import functools
import http.server
import json
import os
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROOFS = Path(os.environ.get("PAI_PROOFS_DIR") or ROOT / "data" / "proofs" / "studio")
if not PROOFS.is_absolute():
    PROOFS = ROOT / PROOFS
OFFER = ("Business Developer Junior (H/F) — CDI — Paris\nAcme SaaS édite un logiciel pour les PME françaises depuis 2015.\n\n"
         "Vos missions\n- Prospecter de nouveaux clients PME par téléphone et LinkedIn.\n- Suivre votre pipeline dans HubSpot.\n\n"
         "Votre profil\n- Anglais courant requis.\n- Maîtrise d'un CRM indispensable.")
WIDTHS = [375, 390, 430, 768, 1280, 1440, 1920]

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


@pytest.fixture(scope="module")
def profile():
    return json.loads((ROOT / "tests" / "fixtures" / "profile_test.json").read_text(encoding="utf-8"))


def _page(browser, url, width, height, seed, scheme="dark"):
    ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1, color_scheme=scheme)
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


def _shot(page, name):
    PROOFS.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(350)
    page.screenshot(path=str(PROOFS / f"{name}.png"), full_page=True)


def _store(page, prefix):
    return page.evaluate("(p) => { const out = []; for (const [k, v] of window.__PAI_MOCK__.store) if (k.startsWith(p)) out.push(v); return out; }", prefix)


def _analyze(page, text=OFFER, questions=""):
    page.locator("#cmd-input").fill(text)
    if questions:
        page.locator(".more-opts > summary").click()
        page.locator("#f-questions").fill(questions)
    page.locator("#command button[data-act=analyze]").click()
    page.locator("#run-side button[data-act=open-pack]").wait_for(timeout=90000)


def _fake_photo(size=420):
    """Photo FACTICE (aplats de couleur) : jamais une vraie personne."""
    pymupdf = pytest.importorskip("pymupdf")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, size, size), False)
    pix.set_rect(pix.irect, (159, 184, 192))
    pix.set_rect(pymupdf.IRect(int(size * .32), int(size * .16), int(size * .68), int(size * .58)), (62, 90, 100))
    pix.set_rect(pymupdf.IRect(int(size * .16), int(size * .62), int(size * .84), size), (243, 241, 234))
    return pix.tobytes("png")


def test_full_flow_desktop(studio_url, profile):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx, page, errors = _page(browser, studio_url, 1440, 900, {"pai/profile": profile})
        page.get_by_text("Bonjour Camille").wait_for(timeout=15000)
        assert page.locator(".hero-mark").inner_text().replace("\n", "") == "PAI"
        assert page.get_by_text("Transforme n'importe quelle offre en candidature personnalisée.").is_visible()
        assert page.locator("#cmd-input").get_attribute("placeholder") == "Colle l'URL de l'offre ici..."
        _shot(page, "desktop_1_accueil")

        # Un lien dans claude.ai : échec honnête + repli texte / PDF, aucune analyse lancée.
        page.locator("#cmd-input").fill("https://www.example.com/offre/123")
        page.locator("#command button[data-act=analyze]").click()
        page.locator("#command .notice").wait_for()
        assert "colle le texte" in page.locator("#command .notice").inner_text().lower()
        assert page.locator("#command .notice button[data-act=cmd-text]").is_visible()
        page.locator("#command button[data-act=cmd-clear]").click()

        _analyze(page, questions="Quelle est votre disponibilité ?\nQuelles sont vos prétentions salariales ?")
        stages = page.locator("#run-panel li.stage")
        assert stages.count() == 9
        assert page.locator("#run-panel li.stage.done").count() == 9, page.locator("#run-panel").inner_text()
        page.locator("#run-side .paper img.pv").first.wait_for(timeout=30000)
        _shot(page, "desktop_2_analyse")

        pack = _store(page, "packs/")[0]
        cv = pack["cvs"][pack["cv_index"]]
        texts = " ".join(line["text"] for line in cv["doc"]["lines"])
        assert "MBA" not in texts, "le piège MBA a atteint le CV"
        assert "40+" not in texts, "le faux chiffre a atteint le CV"
        assert "Licence de gestion" not in texts, "un fait UNVERIFIED a atteint le CV"
        assert cv["report"]["factuality"] == 100.0
        assert pack["letters"][0]["report"]["factuality"] == 100.0
        assert len([ln for ln in pack["letters"][0]["doc"]["lines"] if ln["kind"] == "offer_ref"]) >= 2
        salary = next(a for a in pack["answers"] if "salari" in a["question"])
        assert salary["confidence"] == "BLOCKED" and not salary["answer"], "salaire inventé non bloqué"
        assert cv["doc"]["design_profile"] in {"premium_corporate", "modern_commercial", "minimal_executive", "digital_creative", "ats_hybrid"}
        assert cv["doc"]["photo_mode"] == "OFF"  # aucune photo dans le profil
        assert pack["design"]["why"], "le design automatique doit s'expliquer"
        assert pack["company"]["logo"]["used"] is False
        assert pack["status"] == "DRAFT"  # profil non validé
        assert cv["qa"]["pages"] == 1 and cv["qa"]["ok"], cv["qa"]
        # Profil court : la page est étalée (jamais au-delà d'une page) au lieu de rester à moitié vide.
        assert cv["doc"]["spread"] >= 1 and cv["doc"]["spread_key"].startswith(cv["doc"]["design_profile"] + "|"), cv["doc"].get("spread_key")
        assert cv["qa"]["fill"] >= 0.65, cv["qa"]
        spread = page.evaluate("""() => { const { PDF } = window.__PAI_DEBUG__;
          const d = { design_profile: 'modern_commercial', density: 'airy', spread: 1.5, spread_key: 'modern_commercial|airy|OFF' };
          return [PDF.ctx(d).spread, PDF.ctx(Object.assign({}, d, { density_locked: true })).spread, PDF.ctx(Object.assign({}, d, { design_profile: 'ats_hybrid' })).spread]; }""")
        assert spread == [1.5, 1, 1], f"étalement : mesuré pour une mise en page, ignoré si la densité est choisie à la main {spread}"
        # Libellés en français : ni « (s) » ni jargon anglais dans le déroulé de l'analyse.
        run_text = page.locator("#run-panel").inner_text()
        assert "(s)" not in run_text and "REQUIRED" not in run_text and "QUALITY" not in run_text, run_text

        page.locator("#run-side button[data-act=open-pack]").click()
        for tab in ["Aperçu", "Offre", "Stratégie", "CV", "Lettre", "Questions", "Risques", "Versions"]:
            page.get_by_role("tab", name=tab, exact=True).click()
            page.wait_for_timeout(200)
            if tab in ("Aperçu", "CV", "Lettre"):
                page.locator(".paper img.pv").first.wait_for(timeout=30000)
                _shot(page, f"desktop_3_pack_{tab.lower().replace('ç', 'c')}")

        # CV Studio : 6 scores avec preuve, brouillon de design puis V2.
        page.get_by_role("tab", name="CV", exact=True).click()
        page.locator(".studio .score").first.wait_for()
        assert page.locator(".studio .score").count() == 6
        for k in ["ROLE FIT", "ATS FIT", "PERSONALIZATION", "READABILITY", "DESIGN", "FACTUALITY"]:
            assert page.locator(".studio .score .k", has_text=k).count() == 1, k
        assert page.get_by_text("Pourquoi ce CV ?").is_visible() and page.get_by_text("Ce qui a changé").is_visible()
        page.locator(".toolbar [data-act=toggle-gallery]").click()
        page.locator(".gallery .designs button").nth(4).wait_for()
        assert page.locator(".gallery .designs button").count() == 5, "5 designs réels attendus"
        page.locator(".gallery .designs .paper img.pv").nth(4).wait_for(timeout=45000)
        _shot(page, "desktop_4a_cv_studio_5_designs")
        page.locator(".gallery button[data-arg=minimal_executive]").click()
        page.locator(".draft-pill").wait_for()
        page.locator(".canvas-wrap .paper img.pv").wait_for(timeout=30000)
        page.locator(".draft-pill button[data-act=studio-save]").click()
        page.wait_for_function("() => { for (const [k, v] of window.__PAI_MOCK__.store) if (k.startsWith('packs/')) return v.cvs.length === 2; return false; }", timeout=30000)
        pack = _store(page, "packs/")[0]
        assert pack["cvs"][1]["doc"]["design_profile"] == "minimal_executive" and pack["cv_index"] == 1
        assert pack["cvs"][0]["doc"]["design_profile"] != "minimal_executive", "V1 doit rester intacte"
        _shot(page, "desktop_4_cv_studio")

        page.get_by_role("tab", name="Versions", exact=True).click()
        page.locator("table.cmp").wait_for()
        cmp = page.locator("table.cmp").inner_text().lower()
        assert "modern commercial → minimal executive" in cmp or "→ minimal executive" in cmp, cmp
        _shot(page, "desktop_5_versions_comparaison")

        page.locator(".cover-head button[data-act=dl-cv]").click()
        page.locator(".cover-head button[data-act=dl-zip]").click()
        page.wait_for_function("() => window.__PAI_MOCK__.saved.length >= 2", timeout=30000)
        saved = page.evaluate("() => window.__PAI_MOCK__.saved")
        assert saved[0]["head"] == "%PDF-" and saved[0]["size"] > 20000, saved
        assert saved[1]["head"].startswith("PK") and saved[1]["filename"].endswith(".zip"), saved

        # Training Lab : verdict + raisons → V3 → comparaison visuelle.
        page.locator("#nav button[data-arg=lab]").click()
        page.locator("button[data-act=lab-rate][data-arg='-1']").click()
        page.locator("button[data-act=lab-reason][data-arg=Couleur]").click()
        page.locator("button[data-act=lab-reason][data-arg=Photo]").click()
        page.locator("button[data-act=lab-generate]").click()
        page.wait_for_function("() => { for (const [k, v] of window.__PAI_MOCK__.store) if (k.startsWith('packs/')) return v.cvs.length === 3; return false; }", timeout=30000)
        page.locator("table.cmp").wait_for()
        pack = _store(page, "packs/")[0]
        assert pack["cvs"][2]["doc"]["palette"] != pack["cvs"][1]["doc"].get("palette")
        fb = _store(page, "feedback/")
        assert fb and fb[0]["reasons"] == ["Couleur", "Photo"] and fb[0]["rating"] == -1
        _shot(page, "desktop_6_training_lab")

        for view in ["learning", "benchmark", "versions", "packs"]:
            page.locator(f"#nav button[data-arg={view}]").click()
            page.wait_for_timeout(300)
            _shot(page, f"desktop_7_{view}")

        page.locator("#nav button[data-arg=reglages]").click()
        page.locator("button[data-act=ai-test]").click()
        page.locator(".chip.good", has_text="OK ·").wait_for(timeout=10000)
        assert "REMOTE" in page.locator(".mode-badge").first.inner_text()
        _shot(page, "desktop_8_reglages")
        assert not errors, errors
        ctx.close()
        browser.close()


def test_profile_conflict_photo_onboarding(studio_url, profile):
    prof = copy.deepcopy(profile)
    prof["facts"].append({"id": "edu.legacy_bachelor", "kind": "education", "text": "Bachelor Commerce International — École Y (2019-2022)",
                          "status": "UNVERIFIED", "source": "legacy:ancien_cv", "data": {}})
    prof["review_queue"] = [{"fact_id": "edu.legacy_bachelor", "severity": "conflict",
                             "reason": "Deux intitulés proches : « Bachelor Commerce International — École Y » (ancien CV) et « Bachelor Commerce » (confirmé). Même diplôme ?"}]
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx, page, errors = _page(browser, studio_url, 1280, 860, {"pai/profile": prof})
        page.get_by_text("Bonjour Camille").wait_for(timeout=15000)
        page.locator("#nav button[data-arg=profil]").click()
        card = page.locator(".conflict-card")
        card.wait_for()
        assert card.locator(".side").count() == 2
        assert "edu.bachelor" in card.inner_text() and "edu.legacy_bachelor" in card.inner_text()
        assert page.locator("button[data-act=profile-validate]").is_disabled(), "un conflit ouvert doit bloquer la validation"
        _shot(page, "desktop_9_profil_conflit")
        card.locator("button[data-act=conflict-pick][data-arg='0:B']").click()
        page.wait_for_function("() => (window.__PAI_MOCK__.store.get('pai/profile').review_queue || []).length === 0", timeout=10000)
        saved = page.evaluate("() => window.__PAI_MOCK__.store.get('pai/profile')")
        legacy = next(f for f in saved["facts"] if f["id"] == "edu.legacy_bachelor")
        assert legacy["status"] == "UNVERIFIED" and "edu.bachelor" in legacy["note"]
        assert saved["version"] == prof["version"] + 1 and not saved["validated"]

        # Photo FICTIVE : import, recadrage, alerte basse résolution (image de 180 px).
        page.set_input_files("#f-photo", files=[{"name": "photo.png", "mimeType": "image/png", "buffer": _fake_photo(180)}])
        page.locator("#photo-frame img").wait_for(timeout=10000)
        page.locator("#photo-card .notice.warn").wait_for(timeout=10000)
        assert "basse résolution" in page.locator("#photo-card").inner_text().lower()
        box = page.locator("#photo-frame").bounding_box()
        page.mouse.move(box["x"] + 75, box["y"] + 75)
        page.mouse.down()
        page.mouse.move(box["x"] + 95, box["y"] + 90, steps=4)
        page.mouse.up()
        page.locator("#photo-card button[data-act=photo-mode][data-arg=HEADER]").click()
        page.wait_for_function("() => (window.__PAI_MOCK__.store.get('pai/prefs') || {}).photo_mode === 'HEADER'", timeout=10000)
        photo = page.evaluate("() => window.__PAI_MOCK__.store.get('pai/photo')")
        assert photo and photo["data"].startswith("data:image/jpeg") and len(photo["data"]) < 180000
        _shot(page, "desktop_10_profil_photo")

        page.locator("button[data-act=profile-validate]").click()
        page.wait_for_function("() => window.__PAI_MOCK__.store.get('pai/profile').validated === true", timeout=10000)

        # Avec photo + préférence « en-tête », le CV porte la photo ; la lettre n'en a jamais.
        page.locator("#nav button[data-arg=accueil]").click()
        _analyze(page)
        pack = _store(page, "packs/")[0]
        cv = pack["cvs"][pack["cv_index"]]["doc"]
        assert cv["photo_mode"] in ("HEADER", "SIDEBAR"), cv["photo_mode"]
        assert pack["status"] == "FINAL", pack["next_action"]
        page.locator("#run-side .paper img.pv").first.wait_for(timeout=30000)
        _shot(page, "desktop_11_analyse_avec_photo")

        # Onboarding : 5 étapes, « Votre profil est prêt. »
        page.evaluate("() => { location.hash = 'onboarding'; }")
        for step in ["profil", "documents", "photo", "preferences", "validation"]:
            page.locator(f"button[data-act=ob-done][data-arg={step}]").click()
            page.wait_for_timeout(150)
        page.get_by_text("Votre profil est prêt.").first.wait_for(timeout=10000)
        _shot(page, "desktop_12_onboarding_pret")
        assert not errors, errors
        ctx.close()
        browser.close()


@pytest.mark.parametrize("width", WIDTHS)
def test_widths_no_horizontal_scroll(studio_url, profile, width):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx, page, errors = _page(browser, studio_url, width, 900 if width >= 768 else 844, {"pai/profile": profile}, "light" if width in (390, 1280, 1920) else "dark")
        page.get_by_text("Bonjour Camille").wait_for(timeout=15000)
        _shot(page, f"w{width}_1_accueil")
        _analyze(page)
        page.locator("#run-side .paper img.pv").first.wait_for(timeout=30000)
        _shot(page, f"w{width}_2_analyse")
        page.locator("#run-side button[data-act=open-studio]").click()
        page.locator(".canvas-wrap .paper img.pv").wait_for(timeout=30000)
        _shot(page, f"w{width}_3_cv_studio")
        for view in ["profil", "reglages"]:
            page.evaluate(f"() => {{ location.hash = '{view}'; }}")
            page.wait_for_timeout(250)
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width, f"défilement horizontal ({view}, {width}px)"
        if width < 960:
            page.locator("#tabbar button[data-act=open-more]").click()
            page.locator("#more-sheet.open").wait_for()
            _shot(page, f"w{width}_4_menu_plus")
            page.locator("#more-sheet button[data-arg=lab]").click()
            page.locator("#more-sheet.open").wait_for(state="hidden")
        for view in ["accueil", "analyser", "studio", "packs", "lab"]:
            page.evaluate(f"() => {{ location.hash = '{view}'; }}")
            page.wait_for_timeout(250)
            scroll = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll <= width, f"défilement horizontal sur {view} à {width}px ({scroll}px)"
        assert not errors, errors
        ctx.close()
        browser.close()
