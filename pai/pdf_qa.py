"""PDF QA : un PDF mal rendu est un ÉCHEC.

Contrôles : pagination, page blanche, débordement hors page, marges, tailles de police,
contraste, liens, images, texte extractible et ordre de lecture (test ATS via pdfplumber),
présence des mots-clés REQUIRED couverts. Rendu PNG pour la QA visuelle.
"""

from __future__ import annotations

import io
from typing import Any

from .textnorm import contains_term, norm


def _luminance(rgb: tuple[float, float, float]) -> float:
    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: tuple[float, float, float], bg: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> float:
    l1, l2 = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def render_png(pdf: bytes, page: int = 0, dpi: int = 110) -> bytes:
    import pymupdf

    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc[page].get_pixmap(dpi=dpi).tobytes("png")


def extract_text(pdf: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def check_pdf(pdf: bytes, *, expect_pages: int = 1, required_terms: list[str] | None = None,
              reading_order: list[str] | None = None, min_margin_pt: float = 18.0) -> dict[str, Any]:
    import pymupdf

    issues: list[dict[str, str]] = []
    report: dict[str, Any] = {"ok": True, "issues": issues}
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        report["pages"] = doc.page_count
        report["page_size_pt"] = [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)] if doc.page_count else []
        if doc.page_count > expect_pages:
            issues.append({"severity": "high", "check": "pagination", "detail": f"{doc.page_count} pages (max {expect_pages})"})
        min_size, low_contrast, overflow, fonts, links, images = 99.0, 0, 0, set(), 0, 0
        for pno, page in enumerate(doc):
            width, height = page.rect.width, page.rect.height
            text = page.get_text("text").strip()
            if not text and not page.get_images():
                issues.append({"severity": "high", "check": "page_blanche", "detail": f"page {pno + 1} vide"})
            links += len(page.get_links())
            images += len(page.get_images())
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if not span.get("text", "").strip():
                            continue
                        fonts.add(span.get("font", ""))
                        size = float(span.get("size", 0))
                        min_size = min(min_size, size)
                        x0, y0, x1, y1 = span["bbox"]
                        if x0 < 0 or y0 < 0 or x1 > width + 0.5 or y1 > height + 0.5:
                            overflow += 1
                        elif x0 < min_margin_pt - 6 or x1 > width - (min_margin_pt - 6):
                            overflow += 1
                        color = span.get("color", 0)
                        rgb = (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)
                        if contrast_ratio(rgb) < 4.5 and size < 14:
                            low_contrast += 1
        report.update({"min_font_pt": round(min_size, 2) if min_size < 99 else None, "fonts": sorted(fonts),
                       "links": links, "images": images, "low_contrast_spans": low_contrast, "overflow_spans": overflow})
        if min_size < 7.5:
            issues.append({"severity": "medium", "check": "taille", "detail": f"police minimale {min_size:.1f} pt (< 7,5 pt)"})
        if low_contrast:
            issues.append({"severity": "medium", "check": "contraste", "detail": f"{low_contrast} segment(s) sous 4,5:1"})
        if overflow:
            issues.append({"severity": "high", "check": "debordement", "detail": f"{overflow} segment(s) hors zone imprimable"})
        if any("Fira" not in f and "PAI" not in f for f in fonts if f):
            issues.append({"severity": "low", "check": "polices", "detail": f"police de secours utilisée : {sorted(fonts)}"})

    extracted = extract_text(pdf)
    en = norm(extracted)
    report["ats_text_chars"] = len(extracted)
    if len(extracted) < 300:
        issues.append({"severity": "high", "check": "ats_extraction", "detail": "texte peu ou pas extractible"})
    if reading_order:
        # Recherche séquentielle : chaque repère doit apparaître APRÈS le précédent.
        positions: list[int] = []
        cursor = 0
        for marker in reading_order:
            pos = en.find(norm(marker), cursor)
            positions.append(pos)
            if pos >= 0:
                cursor = pos + 1
        report["reading_order"] = dict(zip(reading_order, positions))
        if any(p < 0 for p in positions):
            anywhere = [en.find(norm(m)) >= 0 for m in reading_order]
            detail = "section introuvable" if not all(anywhere) else "ordre de lecture ATS incohérent"
            issues.append({"severity": "high", "check": "ordre_lecture", "detail": detail})
    if required_terms:
        found = [t for t in required_terms if contains_term(en, t)]
        report["required_found"] = f"{len(found)}/{len(required_terms)}"
        report["required_missing"] = [t for t in required_terms if t not in found]
    report["ok"] = not any(i["severity"] == "high" for i in issues)
    return report
