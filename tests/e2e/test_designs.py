"""Les 5 familles de design (CV + lettre assortie) : vrai pdfmake dans Chromium, profil FICTIF « Camille Test ».

Pour chaque famille : 1 page, polices embarquées (aucune police de secours), texte extractible dans l'ordre
(nom → expérience → formation), et le contenu du document identique d'un design à l'autre (même texte, autre mise en page).
Aperçus PNG → data/proofs/designs/ (hors Git) ou PAI_PROOFS_DIR.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ["premium_corporate", "modern_commercial", "minimal_executive", "digital_creative", "ats_hybrid"]
OUT = Path(os.environ.get("PAI_PROOFS_DIR") or ROOT / "data" / "proofs") / "designs"
if not OUT.is_absolute():
    OUT = ROOT / OUT
OFFER = ("Business Developer Junior (H/F) — CDI — Paris\nNordlys (entreprise FICTIVE) édite un logiciel SaaS pour les PME françaises.\n\n"
         "Vos missions\n- Prospecter de nouveaux clients PME par téléphone, email et LinkedIn.\n- Suivre votre pipeline dans HubSpot.\n"
         "- Négocier avec les décideurs.\n\nVotre profil\n- Anglais courant requis.\n- Maîtrise d'un CRM indispensable.")

pw = pytest.importorskip("playwright.sync_api")
pymupdf = pytest.importorskip("pymupdf")


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    sys.path.insert(0, str(ROOT / "web"))
    from build_studio import FONTS, ensure_vendor, studio_data  # type: ignore[import-not-found]

    vendor = ensure_vendor("pdfmake.min.js")
    fonts = {n: base64.b64encode((ROOT / "fonts" / n).read_bytes()).decode("ascii") for n in FONTS}
    page = tmp_path_factory.mktemp("designs") / "harness.html"
    page.write_text("<!doctype html><meta charset='utf-8'><body>"
                    f"<script>{vendor.read_text(encoding='utf-8')}</script>"
                    f"<script>window.PAI_DATA={json.dumps(studio_data(), ensure_ascii=False)};window.PAI_FONTS={json.dumps(fonts)};</script>"
                    f"<script>{(ROOT / 'web/studio/engine.js').read_text(encoding='utf-8')}</script>"
                    f"<script>{(ROOT / 'web/studio/designs.js').read_text(encoding='utf-8')}</script></body>", encoding="utf-8")
    return page


RENDER = """async ([profile, offer, fam, palette, withPhoto]) => {
  const E = window.PAIEngine; E.setData(window.PAI_DATA); const D = window.PAIDesigns; D.registerFonts(window.pdfMake, window.PAI_FONTS);
  const P = E.P(profile); const a = E.deterministicAnalysis({ text: offer, title_hint: '', company_hint: 'Nordlys' });
  const m = E.computeMatch(P, a); const s = E.deterministicStrategy(P, a, m);
  const cv = E.buildCvDeterministic(P, a, m, s, false); cv.design_profile = fam;
  let photo = null;
  if (withPhoto) {  // photo FACTICE (dégradé + initiales), jamais une vraie photo
    const c = document.createElement('canvas'); c.width = c.height = 400; const g = c.getContext('2d');
    const gr = g.createLinearGradient(0, 0, 400, 400); gr.addColorStop(0, '#9FB8C0'); gr.addColorStop(1, '#3E5A64'); g.fillStyle = gr; g.fillRect(0, 0, 400, 400);
    g.fillStyle = '#F3F1EA'; g.font = '600 150px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('CT', 200, 212);
    const square = c.toDataURL('image/jpeg', 0.9);
    const k = document.createElement('canvas'); k.width = k.height = 400; const h = k.getContext('2d'); h.beginPath(); h.arc(200, 200, 200, 0, Math.PI * 2); h.clip(); h.drawImage(c, 0, 0);
    photo = { square, circle: k.toDataURL('image/png') };
  }
  const ctx = { palette: D.palette(palette), density: 'balanced', photo, photoMode: withPhoto ? (fam === 'digital_creative' ? 'SIDEBAR' : 'HEADER') : 'OFF' };
  const toB64 = (def) => new Promise((res) => window.pdfMake.createPdf(def).getBase64(res));
  const letter = E.buildLetterDeterministic(P, a, m, s, { text: offer }, false, new Date(2026, 8, 27));
  return { cv: await toB64(D.cv(E, cv, ctx)), letter: await toB64(D.letter(E, letter, Object.assign({}, ctx, { designId: fam, name: P.value('id.name'), contact: E.contactLines(P), headline: s.best.title, photoMode: 'OFF' }))),
    lines: cv.lines.map((l) => [l.section, l.text]), titles: cv.section_titles, name: cv.name };
}"""


def _check(pdf: bytes, name: str, order: list[str]) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        assert doc.page_count == 1, f"{name} : {doc.page_count} pages"
        text = doc[0].get_text()
        fonts = {f[3] for f in doc[0].get_fonts()}
        assert not [f for f in fonts if not any(k in f for k in ("Fira", "SourceSerif", "Manrope"))], f"{name} : police de secours {fonts}"
        low = " ".join(text.split()).lower()  # un titre peut passer à la ligne : un ATS lit les mots, pas les retours
        pos = -1
        for marker in order:
            nxt = low.find(marker.lower(), pos + 1)
            assert nxt > pos, f"{name} : ordre de lecture ({marker!r} introuvable après la position {pos})"
            pos = nxt
        png = doc[0].get_pixmap(dpi=72).tobytes("png")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.png").write_bytes(png)
    return text


@pytest.mark.parametrize("family", FAMILIES)
def test_design_family_renders_one_clean_page(harness, profile, family):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(harness.as_uri())
        data = profile.model_dump(by_alias=True)
        for palette, with_photo in (("petrol", False), ("navy", True)):
            r = page.evaluate(RENDER, [data, OFFER, family, palette, with_photo])
            order = [r["name"], r["titles"]["experience"], r["titles"]["education"]]
            text = _check(base64.b64decode(r["cv"]), f"cv_{family}_{palette}{'_photo' if with_photo else ''}", order)
            # Même contenu quel que soit le design : chaque ligne du document est dans le PDF (retours à la ligne ignorés ;
            # les langues peuvent être présentées « langue + niveau », chaque morceau doit alors être présent).
            flat = re.sub(r"-\s+", "-", " ".join(text.split())).lower()
            norm = lambda t: re.sub(r"-\s+", "-", " ".join(t.split())).lower()  # noqa: E731
            missing = []
            for section, ln in r["lines"]:
                parts = [x for x in re.split(r"[()·,]", ln) if x.strip()] if section == "languages" else [ln]
                missing += [ln for part in parts if norm(part).strip()[:40] not in flat]
            assert not missing, f"{family} : lignes absentes du PDF {missing[:3]}"
            _check(base64.b64decode(r["letter"]), f"lettre_{family}_{palette}", [r["name"]])
        browser.close()
