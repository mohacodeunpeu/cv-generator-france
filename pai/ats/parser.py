"""Lecture d'un CV en texte brut (extrait d'un PDF, d'un DOCX ou collé) : ce qu'un ATS en comprend.

Sortie : coordonnées, sections reconnues et leur ordre, expériences (intitulé, entreprise, dates), formation,
compétences, langues. Déterministe. Sert au mode « CV seul », au scanner PDF et à la relecture après génération
(le CV généré, une fois relu, doit contenir toutes ses lignes et rien de plus).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..analyzer import CITIES
from ..claims import LANGUAGES
from ..textnorm import norm

SECTIONS: dict[str, str] = {
    "summary": r"profil|resume|a propos|summary|profile|about me|objectif|presentation",
    "experience": r"experiences?(?: professionnelles?)?|parcours(?: professionnel)?|emplois?|work experience|"
                  r"professional experience|employment|experiences? cles",
    "education": r"formations?|education|diplomes?|etudes|cursus|academic background",
    "skills": r"competences(?: cles| techniques)?|skills|savoir-faire|outils|informatique|logiciels|expertises?|atouts",
    "languages": r"langues?|languages",
    "certifications": r"certifications?|certificats?|habilitations?",
    "interests": r"centres? d'interets?|interets|loisirs|hobbies|activites extra-professionnelles",
    "projects": r"projets?|projects|realisations",
    "volunteering": r"benevolat|engagements?|volunteering|vie associative",
}
LABELS = {"summary": "Profil", "experience": "Expérience", "education": "Formation", "skills": "Compétences",
          "languages": "Langues", "certifications": "Certifications", "interests": "Centres d'intérêt",
          "projects": "Projets", "volunteering": "Engagements"}
_HEAD = {k: re.compile(rf"^\s*(?:mes |vos )?(?:{v})\s*:?\s*$") for k, v in SECTIONS.items()}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:(?:\+|00)\d{2,3}[\s.-]?(?:\(0\)[\s.-]?)?\d|\b0\d)(?:[\s.-]?\d{2}){4}")
LINKEDIN = re.compile(r"linkedin\.com/in/[\w-]+", re.I)
_MONTH = (r"(?:janv(?:ier)?|fevr?(?:ier)?|mars|avr(?:il)?|mai|juin|juil(?:let)?|aout|sept(?:embre)?|oct(?:obre)?|"
          r"nov(?:embre)?|dec(?:embre)?|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:tember)?|october|november|december)\.?")
_DATE = rf"(?:{_MONTH}\s+)?(?:(?:0?[1-9]|1[0-2])[/.-])?(?:19|20)\d{{2}}"
_NOW = r"(?:present|aujourd'hui|ce jour|actuel(?:lement)?|en cours|now|current|today)"
DATE_RANGE = re.compile(rf"({_DATE})\s*(?:-|a|au|to|>|→)\s*({_DATE}|{_NOW})|(?:depuis|since)\s+({_DATE})|({_DATE})")
_BULLET = re.compile(r"^\s*[-•*·▪►✓✔–]\s*")


@dataclass
class Experience:
    title: str = ""
    company: str = ""
    dates: str = ""
    start: str = ""
    end: str = ""
    bullets: list[str] = field(default_factory=list)


@dataclass
class ParsedCv:
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    city: str = ""
    sections: dict[str, list[str]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    experiences: list[Experience] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    words: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def heading(line: str) -> str:
    """Nom de section si la ligne est un intitulé (« EXPÉRIENCE PROFESSIONNELLE », « Formation : »)."""
    n = norm(line).strip(" :-—|•")
    if not n or len(n) > 42:
        return ""
    return next((k for k, pat in _HEAD.items() if pat.match(n)), "")


def _year_month(raw: str) -> str:
    n = norm(raw)
    y = re.search(r"(19|20)\d{2}", n)
    if not y:
        return "present" if re.search(_NOW, n) else ""
    m = re.search(r"(0?[1-9]|1[0-2])[/.-](?:19|20)\d{2}", n)
    months = ["jan", "fev", "mar", "avr", "mai", "juin", "juil", "aou", "sep", "oct", "nov", "dec"]
    en = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    mm = int(m.group(1)) if m else next((i + 1 for i, w in enumerate(months) if w in n[: y.start()]), 0) or \
        next((i + 1 for i, w in enumerate(en) if w in n[: y.start()]), 0)
    return f"{y.group(0)}-{mm:02d}" if mm else y.group(0)


def _split_header(text: str) -> tuple[str, str]:
    t = re.sub(r"[()\[\]]", " ", text).strip(" -—–|,·")
    for sep in (" — ", " – ", " | ", " - ", " chez ", " @ ", ", ", " · "):
        if sep in t:
            a, b = t.split(sep, 1)
            return a.strip(" -—–|,·"), b.strip(" -—–|,·")
    return t, ""


def parse_cv_text(text: str) -> ParsedCv:
    raw_lines = [ln.rstrip() for ln in (text or "").replace("\r", "").split("\n")]
    lines = [ln.strip() for ln in raw_lines if ln.strip()]
    cv = ParsedCv(lines=lines, words=len(re.findall(r"[\wÀ-ÿ'’-]+", text or "")))
    joined = "\n".join(lines)
    if m := EMAIL.search(joined):
        cv.email = m.group(0)
    for m in PHONE.finditer(joined):
        digits = re.sub(r"\D", "", m.group(0))
        if 9 <= len(digits) <= 13 and not re.fullmatch(r"(19|20)\d{2}(19|20)\d{2}", digits):
            cv.phone = m.group(0).strip()
            break
    if m := LINKEDIN.search(joined):
        cv.linkedin = m.group(0)
    head = norm(" ".join(lines[:8]))
    cv.city = next((c.title() for c in CITIES if re.search(rf"(?<![a-z]){re.escape(c)}(?![a-z])", head)), "")
    for ln in lines[:3]:
        if not heading(ln) and not EMAIL.search(ln) and not PHONE.search(ln) and 1 < len(ln.split()) <= 5:
            cv.name = ln
            break

    current = "header"
    cv.sections = {"header": []}
    for ln in lines:
        h = heading(ln)
        if h:
            current = h
            cv.sections.setdefault(h, [])
            if h not in cv.order:
                cv.order.append(h)
            continue
        cv.sections.setdefault(current, []).append(ln)

    for ln in lines:
        for m in DATE_RANGE.finditer(norm(ln)):
            cv.dates.append(m.group(0))

    exp: Experience | None = None
    pending = ""
    for ln in cv.sections.get("experience", []):
        n = norm(ln)
        m = DATE_RANGE.search(n)
        if m and not _BULLET.match(ln):
            start = m.group(1) or m.group(3) or m.group(4) or ""
            end = m.group(2) or ("present" if m.group(3) else "")
            header = (ln[: m.start()] + " " + ln[m.end():]).strip(" -—–|,·()")
            if not header and pending:
                header = pending
            title, company = _split_header(header)
            if not title and pending:
                title, company = _split_header(pending)
            exp = Experience(title=title, company=company, dates=m.group(0), start=_year_month(start),
                             end=_year_month(end) if end else "")
            cv.experiences.append(exp)
            pending = ""
        elif _BULLET.match(ln) and exp is not None:
            exp.bullets.append(_BULLET.sub("", ln))
        elif exp is not None and exp.bullets and len(ln) > 40:
            exp.bullets.append(ln)
        else:
            pending = ln
    cv.education = cv.sections.get("education", [])
    skills = cv.sections.get("skills", [])
    cv.skills = [s.strip() for ln in skills for s in re.split(r"[,;•·|]", _BULLET.sub("", ln)) if 1 < len(s.strip()) < 60]
    lang_lines = cv.sections.get("languages", []) or [ln for ln in lines if any(re.search(rf"\b{w}\b", norm(ln)) for w in LANGUAGES)][:4]
    cv.languages = [ln for ln in lang_lines if any(re.search(rf"\b{w}\b", norm(ln)) for w in LANGUAGES)]
    return cv
