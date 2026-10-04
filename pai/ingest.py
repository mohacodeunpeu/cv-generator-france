"""Ingestion d'une offre (texte, URL publique, PDF). Le texte est figé et haché à l'ingestion.

Règle A9 : pas de scraping derrière un login ; URL bloquée → on demande le texte collé ou le PDF.
URL : lecture sûre (pai.netfetch, protection SSRF) ; données structurées schema.org `JobPosting` d'abord,
sinon texte principal de la page. Rien n'est inventé : trop peu de texte → échec explicite.
"""

from __future__ import annotations

import html
import io
import json
import re
from pathlib import Path
from typing import Any

import httpx
import yaml

from . import paths
from .schemas import Offer
from .textnorm import norm, stable_hash

# Sites fermés (connexion requise ou collecte interdite) : reconnus par un libellé du nom d'hôte.
LOGIN_WALLED = ("linkedin", "lnkd", "indeed", "glassdoor")
PASTE_HINT = "collez le texte de l'offre ou importez le PDF"
MIN_CHARS = 80
EMPLOYMENT = {"FULL_TIME": "Temps plein", "PART_TIME": "Temps partiel", "CONTRACTOR": "Prestataire / indépendant",
              "TEMPORARY": "Temporaire", "INTERN": "Stage", "VOLUNTEER": "Bénévolat", "PER_DIEM": "À la journée",
              "OTHER": "Autre"}
SALARY_UNITS = {"HOUR": "de l'heure", "DAY": "par jour", "WEEK": "par semaine", "MONTH": "par mois", "YEAR": "par an"}
_BLOCK_TAGS = ["p", "div", "section", "article", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "blockquote", "pre", "dd", "dt", "hr"]


class IngestError(ValueError):
    """Offre impossible à ingérer (message affichable à l'utilisateur)."""


class UrlIngestError(IngestError):
    """Lecture d'une URL impossible. `code` stable pour l'interface : login_walled, bad_url, blocked_address,
    too_large, timeout, forbidden, anti_bot, auth_required, not_found, rate_limited, unavailable, js_required,
    http_error, unreadable ; `message` affichable (français), qui dit pourquoi le serveur PAI n'a pas pu lire."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def offer_from_text(text: str, title: str = "", company: str = "", source_url: str = "",
                    source_type: str = "text", synthetic: bool = False) -> Offer:
    cleaned = _clean(text)
    if len(cleaned) < MIN_CHARS:
        raise IngestError("Texte d'offre trop court (80 caractères minimum). Collez l'annonce complète.")
    if len(cleaned) > 30000:
        cleaned = cleaned[:30000]
    text_hash = stable_hash(norm(cleaned), 16)
    return Offer(id=f"off_{text_hash[:12]}", source_type=source_type, source_url=source_url, title_hint=title.strip(),
                 company_hint=company.strip(), text=cleaned, text_hash=text_hash, synthetic=synthetic)


# ── URL ──────────────────────────────────────────────────────────────────────
def is_login_walled(url: str | httpx.URL) -> bool:
    """LinkedIn, Indeed, Glassdoor… : refus immédiat, sans aucun appel réseau."""
    try:
        host = (url if isinstance(url, httpx.URL) else httpx.URL(url.strip())).host.lower().rstrip(".")
    except (httpx.InvalidURL, TypeError, ValueError):
        return False
    return any(label in LOGIN_WALLED for label in host.split("."))


def _refuse_login_walled(url: str | httpx.URL) -> None:
    """Contrôle appliqué à l'URL collée ET à chaque redirection (un lien court peut mener à LinkedIn)."""
    if is_login_walled(url):
        raise UrlIngestError("login_walled", f"Ce site demande une connexion ou interdit la collecte automatique : {PASTE_HINT}.")


def _plain(value: Any) -> str:
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, (str, int, float, dict))), "")
    if isinstance(value, dict):
        value = value.get("name", "")
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def html_to_text(markup: Any) -> str:
    """HTML (éventuellement échappé) → texte à lignes : blocs et <br> = retours à la ligne, puces « - »."""
    from bs4 import BeautifulSoup

    if not isinstance(markup, str) or not markup.strip():
        return ""
    if "<" not in markup and "&lt;" in markup:
        markup = html.unescape(markup)  # description doublement échappée
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert(0, "- ")
        li.insert_before("\n")  # une puce par ligne, sans ligne vide entre deux puces
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = (re.sub(r"[ \t\u00a0\u202f]+", " ", ln).strip() for ln in soup.get_text().splitlines())
    return _clean(re.sub(r"^- *\n+", "- ", "\n".join(lines), flags=re.M))


def job_postings(soup: Any) -> list[dict[str, Any]]:
    """Objets schema.org JobPosting des blocs <script type="application/ld+json"> (liste, @graph, mainEntity)."""
    found: list[dict[str, Any]] = []
    for tag in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = re.sub(r"^\s*(<!--|<!\[CDATA\[)|(-->|\]\]>)\s*$", "", tag.string or tag.get_text() or "")
        try:
            data = json.loads(raw, strict=False)
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(reversed(node))
            elif isinstance(node, dict):
                raw_type = node.get("@type")
                types = raw_type if isinstance(raw_type, list) else [raw_type]
                if any(str(t).rsplit("/", 1)[-1].rsplit(":", 1)[-1] == "JobPosting" for t in types if t):
                    found.append(node)
                stack.extend(node[k] for k in ("mainEntity", "@graph") if isinstance(node.get(k), (list, dict)))
    return found


def _places(posting: dict[str, Any]) -> str:
    out: list[str] = []
    places = posting.get("jobLocation")
    for place in places if isinstance(places, list) else [places]:
        address = place.get("address") if isinstance(place, dict) else place
        address = address[0] if isinstance(address, list) and address else address
        if isinstance(address, dict):
            city, postal = _plain(address.get("addressLocality")), _plain(address.get("postalCode"))
            parts = [f"{city} ({postal})" if city and postal else city or postal, _plain(address.get("addressRegion")),
                     _plain(address.get("addressCountry"))]
            text = ", ".join(dict.fromkeys(p for p in parts if p))
        else:
            text = _plain(address)
        if text and text not in out:
            out.append(text)
    if "TELECOMMUTE" in str(posting.get("jobLocationType", "")).upper():
        out.append("Télétravail")
    return " ; ".join(out)


def _employment(value: Any) -> str:
    values = value if isinstance(value, list) else [value]
    labels = [EMPLOYMENT.get(re.sub(r"[\s-]+", "_", str(v).strip().upper()), _plain(v)) for v in values if v]
    return ", ".join(dict.fromkeys(label for label in labels if label))


def _amount(value: Any) -> str:
    try:
        number = float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    text = f"{number:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")  # 40000 → « 40 000 », 11.88 → « 11,88 »


def _salary(raw: Any) -> str:
    """baseSalary (MonetaryAmount) → « 40 000 – 45 000 EUR par an » ; vide si aucun montant."""
    if not isinstance(raw, dict):
        return ""
    value = raw.get("value")
    spec = value if isinstance(value, dict) else {"value": value}
    amounts = [a for a in (_amount(spec.get("minValue")), _amount(spec.get("maxValue"))) if a] or \
              [a for a in [_amount(spec.get("value"))] if a]
    if not amounts:
        return ""
    unit = SALARY_UNITS.get(str(spec.get("unitText") or raw.get("unitText") or "").upper(), "")
    return " ".join(x for x in (" – ".join(dict.fromkeys(amounts)), _plain(raw.get("currency")), unit) if x)


def posting_offer(posting: dict[str, Any]) -> tuple[str, str, str, str]:
    """(texte, titre, entreprise, description) : titre, entreprise, lieu, contrat, salaire, date, puis description."""
    title = _plain(posting.get("title") or posting.get("name"))
    company = _plain(posting.get("hiringOrganization"))
    description = html_to_text(posting.get("description"))
    head = [(label, value) for label, value in (
        ("Entreprise", company), ("Lieu", _places(posting)), ("Contrat", _employment(posting.get("employmentType"))),
        ("Salaire", _salary(posting.get("baseSalary"))), ("Publiée le", _plain(posting.get("datePosted"))[:10])) if value]
    lines = [title] if title else []
    lines += [f"{label} : {value}" for label, value in head]
    return "\n".join(lines + ["", description]), title, company, description


def _page_offer(body: bytes, charset: str | None) -> tuple[str, str, str]:
    """(texte, titre, entreprise) d'une page HTML : JobPosting JSON-LD d'abord, sinon texte principal."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser", from_encoding=charset)
    for posting in job_postings(soup):
        text, title, company, description = posting_offer(posting)
        if len(description) >= MIN_CHARS:
            return text, title, company
    for tag in soup(["script", "style", "nav", "footer", "header", "form", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return main.get_text("\n", strip=True), title, ""


_SPA = re.compile(rb"<div id=[\"'](?:root|app|__next|__nuxt)[\"'][^>]*>\s*</div>|<app-root|enable javascript|"
                 rb"activer javascript|activez javascript|javascript is required|javascript est requis|javascript required",
                 re.I)


def needs_javascript(body: bytes) -> bool:
    """Page d'application (SPA) : le contenu n'existe qu'après exécution de JavaScript."""
    head = body[:200_000]
    scripts = len(re.findall(rb"<script(?![^>]*application/ld\+json)", head, re.I))
    return bool(_SPA.search(head)) or scripts >= 8


def _decode(body: bytes, charset: str | None) -> str:
    try:
        return body.decode(charset or "utf-8", "replace")
    except LookupError:  # jeu de caractères inconnu annoncé par le site
        return body.decode("utf-8", "replace")


def offer_from_url(url: str, timeout: float = 15.0, *, transport: httpx.BaseTransport | None = None,
                   resolver: Any = None) -> Offer:
    """Offre depuis une URL publique (lecture sûre). Lève UrlIngestError (code + message) ; aucun appel réseau
    pour un site fermé. `transport` / `resolver` : injection pour les tests (httpx.MockTransport, résolveur factice)."""
    from .netfetch import FetchError, safe_get

    _refuse_login_walled(url)
    try:
        page = safe_get(url, timeout=timeout, transport=transport, guard=_refuse_login_walled,
                        **({"resolver": resolver} if resolver else {}))
    except FetchError as exc:
        raise UrlIngestError(exc.code, exc.message) from exc
    if page.mime == "application/pdf" or page.body.lstrip()[:5] == b"%PDF-":
        name = Path(httpx.URL(page.final_url).path).name
        try:
            return offer_from_pdf(page.body, name if name.lower().endswith(".pdf") else "", source_url=page.final_url)
        except IngestError as exc:
            raise UrlIngestError("unreadable", str(exc)) from exc
    if page.mime.startswith("text/plain"):
        text, title, company = _decode(page.body, page.charset), "", ""
    elif not page.mime or "html" in page.mime or "xml" in page.mime:
        text, title, company = _page_offer(page.body, page.charset)
    else:
        raise UrlIngestError("unreadable", f"Format non pris en charge ({page.mime}) : {PASTE_HINT}.")
    if len(_clean(text)) < MIN_CHARS:
        if needs_javascript(page.body):
            raise UrlIngestError("js_required", "Le serveur PAI n'a pas pu lire cette offre : la page ne l'affiche qu'avec "
                                                f"JavaScript (site dynamique), que le serveur n'exécute pas. Sinon, {PASTE_HINT}.")
        raise UrlIngestError("unreadable", "Lecture de l'offre impossible : la page ne contient pas assez de texte lisible "
                                           f"(contenu chargé par script ou protégé ?). Sinon, {PASTE_HINT}.")
    return offer_from_text(text, title=title, company=company, source_url=page.final_url, source_type="url")


def offer_from_pdf(data: bytes, filename: str = "", *, source_url: str = "") -> Offer:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:6])
    except Exception as exc:  # pdfplumber lève des exceptions variées
        raise IngestError(f"PDF illisible : {exc}") from exc
    if len(text.strip()) < MIN_CHARS:
        raise IngestError("Le PDF ne contient pas de texte extractible (scan ?) : collez le texte de l'offre.")
    return offer_from_text(text, title=Path(filename).stem, source_url=source_url, source_type="pdf")


def offer_from_file(name: str, data: bytes, content_type: str = "", *, title: str = "", company: str = "") -> Offer:
    """Offre importée comme fichier : PDF, HTML (page enregistrée, JSON-LD JobPosting compris), DOCX ou texte."""
    from .ats.cvimport import CvImportError, docx_text, kind_of

    kind = kind_of(name, data, content_type)
    if kind == "pdf":
        offer = offer_from_pdf(data, name)
    elif kind == "html":
        text, t, c = _page_offer(data, None)
        if len(_clean(text)) < MIN_CHARS:
            raise IngestError(f"La page HTML ne contient pas assez de texte d'offre : {PASTE_HINT}.")
        offer = offer_from_text(text, title=title or t, company=company or c, source_type="html")
    elif kind == "docx":
        try:
            offer = offer_from_text(docx_text(data), title=title or Path(name).stem, company=company, source_type="file")
        except CvImportError as exc:
            raise IngestError(exc.message) from exc
    elif kind == "text":
        offer = offer_from_text(data.decode("utf-8", "replace"), title=title, company=company, source_type="file")
    else:
        raise IngestError("Format de fichier non pris en charge : PDF, HTML, DOCX ou texte.")
    if title and not offer.title_hint:
        offer.title_hint = title
    if company and not offer.company_hint:
        offer.company_hint = company
    return offer


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
