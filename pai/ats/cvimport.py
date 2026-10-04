"""Import d'un CV (PDF, DOCX, texte) : texte lisible + profil provisoire construit UNIQUEMENT à partir du CV.

Sert à analyser un CV quelconque face à une offre sans profil PAI (API, JobAgent) : chaque ligne du CV devient un
fait IMPORTED dont la provenance est « cv:ligne N ». Rien n'est ajouté ni déduit au-delà du texte du CV.
DOCX : lu sans dépendance (archive ZIP + XML de Word).
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from ..claims import LANGUAGES, LEVEL_WORDS
from ..schemas import Fact, MasterProfile
from ..textnorm import norm
from .parser import ParsedCv, parse_cv_text

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class CvImportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise CvImportError("unreadable", "Fichier Word illisible (DOCX attendu).") from exc
    paras = []
    for p in root.iter(f"{_W}p"):
        text = "".join((t.text or "") if t.tag == f"{_W}t" else "\t" if t.tag == f"{_W}tab" else "" for t in p.iter()
                       if t.tag in (f"{_W}t", f"{_W}tab"))
        paras.append(text)
    return "\n".join(paras)


def kind_of(name: str, data: bytes, content_type: str = "") -> str:
    n, ct = (name or "").lower(), (content_type or "").lower()
    if data[:5] == b"%PDF-" or n.endswith(".pdf") or "pdf" in ct:
        return "pdf"
    if data[:2] == b"PK" and (n.endswith(".docx") or "wordprocessingml" in ct or b"word/document.xml" in data[:4000]):
        return "docx"
    head = data[:600].lower()
    if n.endswith((".html", ".htm")) or "html" in ct or head.lstrip().startswith((b"<!doctype html", b"<html")):
        return "html"
    if n.endswith((".txt", ".md")) or ct.startswith("text/") or not ct:
        try:
            data[:2000].decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            return ""
    return ""


def cv_text_from_file(name: str, data: bytes, content_type: str = "") -> tuple[str, bytes | None]:
    """(texte, octets PDF si c'est un PDF). Lève CvImportError(code, message)."""
    kind = kind_of(name, data, content_type)
    if kind == "pdf":
        from .scanner import read_pdf

        try:
            text = read_pdf(data)["text"]
        except Exception as exc:  # noqa: BLE001 — pdfplumber et pymupdf lèvent des erreurs variées
            raise CvImportError("unreadable", f"PDF illisible ({exc.__class__.__name__}).") from exc
        if len(text.strip()) < 80:
            raise CvImportError("no_text", "Le PDF ne contient pas de texte lisible (CV scanné en image ?) : un ATS ne le "
                                           "lira pas non plus. Exportez le CV en PDF texte depuis votre traitement de texte.")
        return text, data
    if kind == "docx":
        return docx_text(data), None
    if kind == "html":
        from ..ingest import html_to_text

        return html_to_text(data.decode("utf-8", "replace")), None
    if kind == "text":
        return data.decode("utf-8", "replace"), None
    raise CvImportError("unsupported_format", "Format non pris en charge : PDF, DOCX, HTML ou texte.")


def _languages(lines: list[str]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for line in lines:
        for seg in re.split(r"[,;·|/•]", line):
            n = norm(seg)
            word = next((w for w in LANGUAGES if re.search(rf"(?<![a-z]){w}(?![a-z])", n)), "")
            if word and all(LANGUAGES[word] != LANGUAGES.get(x[0], "") for x in out):
                level = next((lv for lv in sorted(LEVEL_WORDS, key=len, reverse=True)
                              if re.search(rf"(?<![a-z]){re.escape(lv)}(?![a-z])", n)), "")
                out.append((word, level, seg.strip()))
    return out


def profile_from_cv(parsed: ParsedCv | str, candidate_id: str = "cv_import") -> MasterProfile:
    p = parse_cv_text(parsed) if isinstance(parsed, str) else parsed
    facts: list[Fact] = []

    def add(fid: str, kind: str, text: str, **extra) -> None:
        facts.append(Fact(id=fid, kind=kind, text=text.strip(), status="IMPORTED", source="cv", provenance="cv importé",
                          **extra))

    if p.name:
        add("id.name", "identity", p.name)
    if p.email:
        add("contact.email", "contact", p.email)
    if p.phone:
        add("contact.phone", "contact", p.phone)
    summary = " ".join(p.sections.get("summary", []))
    if summary:
        add("profile.summary", "summary", summary[:600])
    for i, e in enumerate(p.experiences, 1):
        eid = f"exp.cv{i}"
        add(eid, "experience", " — ".join(x for x in (e.title, e.company) if x) + (f" ({e.dates})" if e.dates else ""),
            data={"title": e.title, "company": e.company, "start": e.start or None,
                  "end": None if e.end in ("", "present") else e.end, "current": e.end == "present", "period_label": e.dates})
        for j, b in enumerate(e.bullets, 1):
            add(f"{eid}.b{j}", "responsibility", b, parent=eid)
    for i, line in enumerate(p.education, 1):
        add(f"edu.cv{i}", "education", line)
    for i, s in enumerate(p.skills, 1):
        add(f"skill.cv{i}", "skill", s)
    for i, (word, level, seg) in enumerate(_languages(p.languages), 1):
        add(f"lang.cv{i}", "language", seg, data={"language": word, "level": level})
    return MasterProfile(candidate_id=candidate_id, facts=facts)
