"""Scanner PDF « côté ATS » : ce qu'un logiciel de recrutement peut réellement lire dans le fichier.

Chaque contrôle rend OK / WARNING / ERROR avec une explication. Le score FORMAT & PARSING en découle
(100 − 25 par ERROR − 8 par WARNING, borné à 0). S'y ajoute la relecture (`roundtrip`) : le texte extrait
du PDF, relu par le parseur, doit contenir toutes les lignes du CV source (rien de perdu) et rien d'autre
(rien d'inventé : aucun reste de gabarit, aucune valeur vide type « undefined »).
"""

from __future__ import annotations

import io
import re
from typing import Any

from ..pdf_qa import check_pdf, extract_text
from ..textnorm import norm
from .parser import LABELS as SECTION_LABELS
from .parser import parse_cv_text

OK, WARNING, ERROR = "OK", "WARNING", "ERROR"
PENALTY = {ERROR: 25, WARNING: 8, OK: 0}
_PLACEHOLDERS = re.compile(r"\b(undefined|null|nan|none|lorem ipsum|\[object object\]|todo|xxx)\b|\{\{|\}\}|%s")
_PRIVATE_USE = re.compile("[-]")
_LIGATURES = re.compile("[ﬀ-ﬆ]")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def _check(cid: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "label": label, "status": status, "detail": detail}


def _layout(pdf: bytes) -> dict[str, Any]:
    """Colonnes, texte pivoté, petites images (pictogrammes), polices Type3, tableaux."""
    import pdfplumber
    import pymupdf

    out = {"columns": 1, "rotated_spans": 0, "icons": 0, "images": 0, "type3_fonts": 0, "tables": 0}
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        for page in doc:
            w = page.rect.width
            blocks = [b for b in page.get_text("dict").get("blocks", []) if b.get("type") == 0]
            lefts: list[float] = []
            for b in blocks:
                x0, y0, x1, y1 = b["bbox"]
                chars = sum(len(s.get("text", "")) for ln in b.get("lines", []) for s in ln.get("spans", []))
                if chars >= 40 and (x1 - x0) < 0.62 * w:
                    lefts.append(round(x0 / (w / 12)))
                for ln in b.get("lines", []):
                    if tuple(round(v, 2) for v in ln.get("dir", (1, 0))) != (1.0, 0.0):
                        out["rotated_spans"] += 1
            # deux zones de départ séparées d'au moins un tiers de page, chacune portant du texte : colonnes
            groups = sorted(set(lefts))
            if groups and groups[-1] - groups[0] >= 4 and min(lefts.count(groups[0]), lefts.count(groups[-1])) >= 2:
                out["columns"] = max(out["columns"], 2)
            for img in page.get_image_info():
                out["images"] += 1
                x0, y0, x1, y1 = img["bbox"]
                if (x1 - x0) < 24 and (y1 - y0) < 24:
                    out["icons"] += 1
            out["type3_fonts"] += sum(1 for f in page.get_fonts() if f[2] == "Type3")
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            out["tables"] += sum(1 for t in page.find_tables() if len(t.rows) >= 2 and len(t.rows[0].cells) >= 2)
    return out


def roundtrip(source_lines: list[str], extracted: str, allowed: list[str] | None = None) -> dict[str, Any]:
    """Relecture : lignes du CV source introuvables dans le PDF (perdues) et texte du PDF absent de la source (ajouté)."""
    flat = norm(re.sub(r"-\n(?=[a-zà-ÿ])", "", extracted)).replace("\n", " ")
    flat_tokens = set(re.findall(r"[a-z0-9][a-z0-9'+#.-]*", flat))
    lost = []
    for line in source_lines:
        n = norm(line)
        if not n or n in flat:
            continue
        toks = re.findall(r"[a-z0-9][a-z0-9'+#.-]*", n)
        if toks and sum(t in flat_tokens for t in toks) / len(toks) < 0.9:
            lost.append(line)
    known = set()
    for text in [*source_lines, *(allowed or []), *SECTION_LABELS.values()]:
        known |= set(re.findall(r"[a-z0-9][a-z0-9'+#.-]*", norm(text)))
    extra = sorted({t for t in flat_tokens if len(t) >= 3 and not t.isdigit() and t not in known
                    and t.rstrip(".,;:") not in known})
    placeholders = sorted({m.group(0) for m in _PLACEHOLDERS.finditer(flat)})
    return {"lost": lost[:12], "lost_count": len(lost), "unexpected": extra[:15], "unexpected_count": len(extra),
            "placeholders": placeholders, "source_lines": len(source_lines)}


def scan_pdf(pdf: bytes, *, max_pages: int = 2, source_lines: list[str] | None = None,
             allowed: list[str] | None = None) -> dict[str, Any]:
    qa = check_pdf(pdf, expect_pages=max_pages)
    text = extract_text(pdf)
    parsed = parse_cv_text(text)
    lay = _layout(pdf)
    checks: list[dict[str, str]] = []

    chars = len(text.strip())
    checks.append(_check("text", "Texte extractible", OK if chars >= 300 else ERROR,
                         f"{chars} caractères lus" if chars >= 300 else "Peu ou pas de texte lisible : un ATS ne lira rien (PDF image ?)."))
    cid = text.count("(cid:") + text.count("�")
    checks.append(_check("encoding", "Encodage des caractères", ERROR if cid else OK,
                         f"{cid} caractère(s) illisible(s) (police sans table Unicode)" if cid else "Caractères correctement encodés"))
    pua, lig, emo = len(_PRIVATE_USE.findall(text)), len(_LIGATURES.findall(text)), len(_EMOJI.findall(text))
    odd = pua + lig + emo
    checks.append(_check("characters", "Caractères spéciaux", WARNING if odd else OK,
                         f"{pua} pictogramme(s) de police, {lig} ligature(s), {emo} emoji" if odd else "Aucun caractère à risque"))
    pages = qa.get("pages", 0)
    checks.append(_check("pages", "Pagination", OK if pages <= max_pages else WARNING if pages == max_pages + 1 else ERROR,
                         f"{pages} page(s) (maximum conseillé : {max_pages})"))
    over = qa.get("overflow_spans", 0)
    checks.append(_check("overflow", "Débordement", ERROR if over else OK,
                         f"{over} segment(s) hors de la zone imprimable" if over else "Tout le texte tient dans la page"))
    checks.append(_check("columns", "Colonnes", WARNING if lay["columns"] > 1 else OK,
                         "Mise en page sur plusieurs colonnes : certains ATS mélangent l'ordre de lecture"
                         if lay["columns"] > 1 else "Une seule colonne de lecture"))
    checks.append(_check("tables", "Tableaux", WARNING if lay["tables"] else OK,
                         f"{lay['tables']} tableau(x) détecté(s) : contenu parfois mal lu" if lay["tables"] else "Aucun tableau"))
    img_only = lay["images"] - lay["icons"]
    checks.append(_check("images", "Images", ERROR if img_only and chars < 300 else WARNING if img_only > 1 else OK,
                         f"{lay['images']} image(s) dont {lay['icons']} pictogramme(s)" if lay["images"] else "Aucune image"))
    checks.append(_check("textboxes", "Zones de texte pivotées", WARNING if lay["rotated_spans"] else OK,
                         f"{lay['rotated_spans']} ligne(s) pivotée(s)" if lay["rotated_spans"] else "Aucun texte pivoté"))
    fonts_ok = not lay["type3_fonts"]
    small = qa.get("min_font_pt")
    checks.append(_check("fonts", "Polices", OK if fonts_ok and (small is None or small >= 7.5) else WARNING,
                         (f"{len(qa.get('fonts', []))} police(s), taille minimale {small} pt" if fonts_ok else
                          f"{lay['type3_fonts']} police(s) Type3 (texte parfois illisible)")))
    email_ok, phone_ok = bool(parsed.email), bool(parsed.phone)
    checks.append(_check("contact", "Coordonnées", OK if email_ok and phone_ok else ERROR if not email_ok else WARNING,
                         "E-mail et téléphone lus" if email_ok and phone_ok else
                         ("E-mail introuvable" if not email_ok else "Téléphone introuvable")))
    found = [s for s in ("experience", "education", "skills") if s in parsed.order]
    missing = [SECTION_LABELS[s] for s in ("experience", "education", "skills") if s not in found]
    checks.append(_check("sections", "Sections reconnues",
                         OK if not missing else ERROR if "experience" not in found and "education" not in found else WARNING,
                         "Sections lues : " + ", ".join(SECTION_LABELS[s] for s in parsed.order) +
                         (f" ; introuvables : {', '.join(missing)}" if missing else "")))
    dated = [e for e in parsed.experiences if e.start]
    checks.append(_check("experience", "Expériences et dates",
                         OK if parsed.experiences and len(dated) == len(parsed.experiences) else
                         WARNING if parsed.experiences else ERROR,
                         f"{len(parsed.experiences)} expérience(s) lue(s), {len(dated)} datée(s)" if parsed.experiences
                         else "Aucune expérience datée reconnue"))
    checks.append(_check("education", "Formation", OK if parsed.education else WARNING,
                         f"{len(parsed.education)} ligne(s) de formation" if parsed.education else "Formation introuvable"))

    report: dict[str, Any] = {"checks": checks, "pages": pages, "text_chars": chars, "layout": lay,
                              "parsed": parsed.as_dict(), "qa": {k: v for k, v in qa.items() if k != "issues"}}
    if source_lines is not None:
        rt = roundtrip(source_lines, text, allowed)
        report["roundtrip"] = rt
        checks.append(_check("lost", "Rien de perdu", OK if not rt["lost_count"] else ERROR,
                             "Toutes les lignes du CV sont relues dans le PDF" if not rt["lost_count"]
                             else f"{rt['lost_count']} ligne(s) du CV introuvable(s) dans le PDF"))
        bad = rt["placeholders"]
        checks.append(_check("added", "Rien d'ajouté", ERROR if bad else WARNING if rt["unexpected_count"] > 8 else OK,
                             f"Texte de gabarit dans le PDF : {', '.join(bad)}" if bad else
                             f"{rt['unexpected_count']} mot(s) sans origine dans le CV source" if rt["unexpected_count"] > 8
                             else "Aucun texte sans origine"))
    report["score"] = max(0, 100 - sum(PENALTY[c["status"]] for c in checks))
    report["status"] = ERROR if any(c["status"] == ERROR for c in checks) else WARNING if any(
        c["status"] == WARNING for c in checks) else OK
    return report
