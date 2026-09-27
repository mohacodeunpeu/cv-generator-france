"""Ingestion d'une offre (texte, URL publique, PDF). Le texte est figé et haché à l'ingestion.

Règle A9 : pas de scraping derrière un login ; URL bloquée → on demande le texte collé ou le PDF.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import yaml

from . import paths
from .schemas import Offer
from .textnorm import norm, stable_hash

LOGIN_WALLED = ("linkedin.com", "indeed.", "glassdoor.")


class IngestError(ValueError):
    """Offre impossible à ingérer (message affichable à l'utilisateur)."""


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def offer_from_text(text: str, title: str = "", company: str = "", source_url: str = "",
                    source_type: str = "text", synthetic: bool = False) -> Offer:
    cleaned = _clean(text)
    if len(cleaned) < 80:
        raise IngestError("Texte d'offre trop court (80 caractères minimum). Collez l'annonce complète.")
    if len(cleaned) > 30000:
        cleaned = cleaned[:30000]
    text_hash = stable_hash(norm(cleaned), 16)
    return Offer(id=f"off_{text_hash[:12]}", source_type=source_type, source_url=source_url, title_hint=title.strip(),
                 company_hint=company.strip(), text=cleaned, text_hash=text_hash, synthetic=synthetic)  # type: ignore[arg-type]


def offer_from_url(url: str, timeout: float = 15.0) -> Offer:
    if any(host in url for host in LOGIN_WALLED):
        raise IngestError("Ce site demande une connexion ou interdit la collecte automatique : collez le texte de l'offre.")
    import httpx
    from bs4 import BeautifulSoup

    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "PAI/1.0 (usage personnel)"})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise IngestError(f"URL inaccessible ({exc.__class__.__name__}) : collez le texte de l'offre ou importez le PDF.") from exc
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "form", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)
    return offer_from_text(text, title=title, source_url=url, source_type="url")


def offer_from_pdf(data: bytes, filename: str = "") -> Offer:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:6])
    except Exception as exc:  # pdfplumber lève des exceptions variées
        raise IngestError(f"PDF illisible : {exc}") from exc
    if len(text.strip()) < 80:
        raise IngestError("Le PDF ne contient pas de texte extractible (scan ?) : collez le texte de l'offre.")
    return offer_from_text(text, title=Path(filename).stem, source_type="pdf")


def load_fixture(path: Path) -> tuple[Offer, dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    offer = offer_from_text(raw["text"], title=raw.get("title", ""), company=raw.get("company", ""),
                            source_url=raw.get("source_url", ""), source_type="fixture",
                            synthetic=bool(raw.get("synthetic", True)))
    if raw.get("fetched_at"):
        offer.fetched_at = str(raw["fetched_at"])
    return offer, raw


def benchmark_fixtures() -> list[tuple[Offer, dict]]:
    return [load_fixture(p) for p in sorted((paths.BENCHMARK_DIR / "offers").glob("*.yaml"))]
