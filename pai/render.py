"""Rendu PDF : gabarits HTML/CSS (Jinja2) → Chromium headless (Playwright) → PDF vectoriel.

Les polices (Fira Sans, SIL OFL) sont embarquées en data URI : aucune police n'est chargée
à distance au moment du rendu. Le texte reste extractible (test ATS dans pdf_qa).
"""

from __future__ import annotations

import base64
import threading
from functools import lru_cache
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import paths
from .config import get_settings
from .rules import load_rules
from .schemas import CvDocument, LetterDocument, Line

DRAFT_LABEL = {"fr": "BROUILLON — PROFIL NON VALIDÉ", "en": "DRAFT — PROFILE NOT VALIDATED"}
_FONT_FACES = [("FiraSans-Regular.ttf", 400, "normal"), ("FiraSans-Italic.ttf", 400, "italic"),
               ("FiraSans-Medium.ttf", 500, "normal"), ("FiraSans-SemiBold.ttf", 600, "normal"),
               ("FiraSans-Bold.ttf", 700, "normal")]


@lru_cache(maxsize=1)
def font_css() -> str:
    rules = []
    for filename, weight, style in _FONT_FACES:
        data = base64.b64encode((paths.FONTS_DIR / filename).read_bytes()).decode("ascii")
        rules.append(f'@font-face {{ font-family: "PAI Sans"; src: url(data:font/ttf;base64,{data}) format("truetype"); '
                     f"font-weight: {weight}; font-style: {style}; }}")
    return "\n".join(rules)


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(loader=FileSystemLoader(paths.TEMPLATES_DIR), autoescape=select_autoescape(["html", "j2"]))


def cv_html(cv: CvDocument, photo_uri: str = "") -> str:
    design = load_rules().design(cv.design_profile)
    blocks = []
    for block in cv.experiences:
        bullets = [ln for bid in block.bullet_ids if (ln := cv.line(bid)) is not None]
        blocks.append({**block.model_dump(), "bullets": bullets})
    groups: dict[str, list[str]] = {}
    for ln in cv.section_lines("skills"):
        groups.setdefault(ln.group or "", []).append(ln.text)
    return _env().get_template("cv.html.j2").render(
        cv=cv, d=design, font_css=font_css(), titles=cv.section_titles, draft_label=DRAFT_LABEL.get(cv.language, DRAFT_LABEL["fr"]),
        headline=cv.section_lines("headline"), extras=cv.section_lines("extras"), summary=cv.section_lines("summary"),
        experiences=blocks, skills=list(groups.items()), education=cv.section_lines("education"),
        certifications=cv.section_lines("certifications"), languages=cv.section_lines("languages"),
        photo_uri=photo_uri if cv.photo_mode != "OFF" else "",
    )


def letter_paragraphs(letter: LetterDocument) -> list[str]:
    by_role: dict[str, list[Line]] = {}
    for ln in letter.lines:
        by_role.setdefault(ln.section, []).append(ln)
    paras = []
    for role in letter.paragraph_order:
        sentences = [ln.text.strip() for ln in by_role.get(role, []) if ln.text.strip()]
        if sentences:
            paras.append(" ".join(sentences))
    return paras


def letter_html(letter: LetterDocument, name: str, contact: list[str], design_id: str = "hybrid_modern") -> str:
    design = load_rules().design(design_id)
    return _env().get_template("letter.html.j2").render(
        letter=letter, name=name, contact=contact, d=design, font_css=font_css(),
        paragraphs=letter_paragraphs(letter), draft_label=DRAFT_LABEL.get(letter.language, DRAFT_LABEL["fr"]),
    )


class PdfRenderer:
    """Chromium partagé, confiné dans UN thread dédié : l'API synchrone de Playwright est liée au thread
    qui l'a créée, alors que FastAPI et le worker appellent le rendu depuis plusieurs threads."""

    _lock = threading.Lock()
    _instance: "PdfRenderer | None" = None

    def __init__(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pai-chromium")
        self._pw = None
        self._browser = None
        self._executor.submit(self._start).result()

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        executable = get_settings().chromium_executable or None
        self._browser = self._pw.chromium.launch(executable_path=executable, args=["--no-sandbox", "--disable-gpu"])

    def _render(self, html: str, paper: str) -> bytes:
        assert self._browser is not None
        page = self._browser.new_page()
        try:
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            return page.pdf(format="Letter" if paper == "Letter" else "A4", print_background=True, prefer_css_page_size=True)
        finally:
            page.close()

    @classmethod
    def get(cls) -> "PdfRenderer":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def pdf(self, html: str, paper: str = "A4") -> bytes:
        return self._executor.submit(self._render, html, paper).result(timeout=120)

    def _stop(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    @classmethod
    def shutdown(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                inst = cls._instance
                cls._instance = None
                try:
                    inst._executor.submit(inst._stop).result(timeout=30)
                finally:
                    inst._executor.shutdown(wait=True)


def render_cv_pdf(cv: CvDocument, photo_uri: str = "") -> bytes:
    return PdfRenderer.get().pdf(cv_html(cv, photo_uri), cv.paper)


def render_letter_pdf(letter: LetterDocument, name: str, contact: list[str], design_id: str = "hybrid_modern") -> bytes:
    return PdfRenderer.get().pdf(letter_html(letter, name, contact, design_id), "A4")


def pdf_page_count(pdf: bytes) -> int:
    import pymupdf

    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc.page_count


def render_cv_fitted(cv: CvDocument, max_pages: int = 1, photo_uri: str = "") -> tuple[CvDocument, bytes, dict[str, Any]]:
    """Rend le CV et retire du contenu secondaire tant qu'il dépasse `max_pages` (3 passes max)."""
    from .cv_architect import trim_for_space

    pdf = render_cv_pdf(cv, photo_uri)
    info: dict[str, Any] = {"trim_steps": 0}
    step = 0
    while pdf_page_count(pdf) > max_pages and step < 3:
        step += 1
        cv = trim_for_space(cv, step)
        pdf = render_cv_pdf(cv, photo_uri)
    info["trim_steps"] = step
    info["pages"] = pdf_page_count(pdf)
    return cv, pdf, info
