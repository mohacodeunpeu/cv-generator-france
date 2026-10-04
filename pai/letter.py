"""Lettre de motivation : accroche spécifique → pourquoi ce poste → pourquoi cette entreprise →
preuves → valeur → conclusion. Chaque phrase est typée (claim / offer_ref / projection / closing)
et passe au validateur ; au moins 2 éléments propres à l'annonce sont cités.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .rules import RuleSet, load_rules
from .schemas import Analysis, LetterDocument, Line, MasterProfile, Match, Offer, Strategy
from .textnorm import extract_numbers, norm

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def place_date(profile: MasterProfile, lang: str, today: date | None = None) -> str:
    today = today or date.today()
    city_fact = profile.fact("contact.city")
    city = (city_fact.data.get("city") if city_fact else "") or "Paris"
    if lang == "en":
        return f"{city}, {MONTHS_EN[today.month - 1]} {today.day}, {today.year}"
    day = "1er" if today.day == 1 else str(today.day)
    return f"{city}, le {day} {MONTHS_FR[today.month - 1]} {today.year}"


def _intro_sentence(offer: Offer) -> str:
    """Première phrase descriptive de l'entreprise dans l'offre (hors titre)."""
    lines = [ln.strip() for ln in offer.text.splitlines() if ln.strip()]
    for ln in lines[1:4]:
        if len(ln) > 40 and not re.match(r"^\s*[-•*]", ln) and ":" not in ln[:25]:
            return ln.rstrip(".")
    return ""


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text


def build_letter_deterministic(profile: MasterProfile, analysis: Analysis, match: Match, strategy: Strategy,
                               offer: Offer, rules: RuleSet | None = None, today: date | None = None) -> LetterDocument:
    rules = rules or load_rules()
    lang = "en" if analysis.language_of_offer == "en" else "fr"
    company = analysis.company if analysis.company not in ("", "UNKNOWN") else ("your company" if lang == "en" else "votre entreprise")
    title = strategy.best.title
    lines: list[Line] = []

    def add(section: str, kind: str, text: str, fact_ids: list[str] | None = None, quote: str = "") -> None:
        lines.append(Line(id=f"{section.lower()}{sum(1 for ln in lines if ln.section == section) + 1}", section=section,
                          kind=kind, text=text, fact_ids=fact_ids or [], offer_quote=quote))

    up = [profile.fact(e) for e in strategy.best.experiences_up if profile.fact(e)]
    main = up[0] if up else (profile.experiences()[0] if profile.experiences() else None)
    covered = {fid for c in match.coverage if c.covered for fid in c.fact_ids}
    missions = [m for m in analysis.missions if len(m) > 15][:2]

    # HOOK
    if missions:
        quote = missions[0].rstrip(".")
        if lang == "en":
            add("HOOK", "offer_ref", f"Your {title} opening puts one mission first: “{quote}”.", quote=quote)
        else:
            add("HOOK", "offer_ref", f"Votre offre de {title} place une mission au premier plan : « {quote} ».", quote=quote)
    if main is not None:
        tasks = sorted(profile.children(main.id), key=lambda f: (f.id not in covered, f.kind != "responsibility"))
        task = next((t for t in tasks if t.kind == "responsibility"), None)
        if task is not None:
            d = main.data
            current = d.get("current")
            if lang == "en":
                verb = "I currently work" if current else "I worked"
                add("HOOK", "claim", f"{verb} as {d.get('title')} at {d.get('company')}: {_lower_first(task.text)}.", [main.id, task.id])
            else:
                verb = "J'exerce actuellement" if current else "J'ai exercé"
                add("HOOK", "claim", f"{verb} comme {d.get('title')} chez {d.get('company')} : {_lower_first(task.text)}.",
                    [main.id, task.id])

    # WHY_ROLE
    if len(missions) > 1:
        quote = missions[1].rstrip(".")
        if lang == "en":
            add("WHY_ROLE", "offer_ref", f"The role also involves this: “{quote}”.", quote=quote)
            add("WHY_ROLE", "projection", "That combination of field work and follow-up is exactly the scope I am looking for.")
        else:
            add("WHY_ROLE", "offer_ref", f"Le poste comprend aussi : « {quote} ».", quote=quote)
            add("WHY_ROLE", "projection", "C'est précisément ce périmètre, de la prise de contact au suivi, que je recherche.")

    # WHY_COMPANY (uniquement ce que dit l'offre)
    intro = _intro_sentence(offer)
    if intro:
        if lang == "en":
            add("WHY_COMPANY", "offer_ref", f"Your posting describes the company this way: “{intro}”.", quote=intro)
            add("WHY_COMPANY", "projection", f"I would like to contribute to that development at {company}.")
        else:
            add("WHY_COMPANY", "offer_ref", f"Votre annonce présente l'entreprise ainsi : « {intro} ».", quote=intro)
            add("WHY_COMPANY", "projection", f"C'est dans ce contexte que je souhaite m'investir chez {company}.")

    # PROOF : 2 à 3 résultats couverts par l'offre, chiffrés de préférence
    results = [f for f in profile.by_kind("result")]
    results.sort(key=lambda f: (f.id not in covered, not extract_numbers(f.text)))
    used_parents: set[str] = set()
    for fact in results:
        if len(used_parents) >= 3 or not fact.parent or fact.parent in used_parents:
            continue
        parent = profile.fact(fact.parent)
        if parent is None:
            continue
        used_parents.add(fact.parent)
        company_name = parent.data.get("company", "")
        if lang == "en":
            add("PROOF", "claim", f"At {company_name}: {_lower_first(fact.text)}.", [fact.id, parent.id])
        else:
            add("PROOF", "claim", f"Chez {company_name} : {_lower_first(fact.text)}.", [fact.id, parent.id])

    # VALUE
    if lang == "en":
        add("VALUE", "projection", f"I want to bring that same discipline to {company}, starting with the priorities set in your posting.")
    else:
        add("VALUE", "projection", f"Je souhaite apporter cette même rigueur à {company}, en commençant par les priorités fixées dans votre annonce.")

    # CLOSE
    extras = [fid for fid in ("avail.immediate", "mobility.idf") if profile.fact(fid) and profile.fact(fid).usable]  # type: ignore[union-attr]
    if extras:
        if lang == "en":
            add("CLOSE", "claim", "I am available immediately and can travel across the Île-de-France region.", extras)
        else:
            text = "Disponible immédiatement" + (" et mobile en Île-de-France" if "mobility.idf" in extras else "")
            add("CLOSE", "claim", f"{text}, je serais heureux d'échanger avec vous sur ce poste.", extras)
    if lang == "en":
        add("CLOSE", "closing", "Thank you for your time and consideration.")
    else:
        add("CLOSE", "closing", "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.")

    name = profile.value("id.name", profile.candidate_id)
    return LetterDocument(
        language=lang, draft=not profile.validated, place_date=place_date(profile, lang, today),
        recipient=(f"{company} — Recruitment team" if lang == "en" else f"{company} — Service recrutement"),
        subject=(f"Application — {title}" if lang == "en" else f"Objet : candidature au poste de {title}"),
        salutation=("Dear Hiring Team," if lang == "en" else "Madame, Monsieur,"),
        lines=lines, signature=name, source="deterministic",
    )


def letter_from_ai(payload: dict[str, Any], profile: MasterProfile, analysis: Analysis, base: LetterDocument) -> LetterDocument:
    lines: list[Line] = []
    for para in payload.get("paragraphs") or []:
        role = str(para.get("role", "PROOF")).upper()
        if role not in base.paragraph_order:
            role = "PROOF"
        for s in para.get("sentences") or []:
            kind = str(s.get("kind", "claim"))
            if kind not in ("claim", "offer_ref", "projection", "closing"):
                kind = "claim"
            lines.append(Line(id=f"{role.lower()}{sum(1 for ln in lines if ln.section == role) + 1}", section=role, kind=kind,
                              text=str(s.get("text", "")).strip(), fact_ids=[str(x) for x in s.get("fact_ids", [])],
                              offer_quote=str(s.get("offer_quote", ""))))
    doc = base.model_copy(deep=True)
    doc.lines = [ln for ln in lines if ln.text]
    if payload.get("subject"):
        doc.subject = str(payload["subject"])
    if payload.get("salutation"):
        doc.salutation = str(payload["salutation"])
    doc.signature = profile.value("id.name", doc.signature)
    doc.source = "ai"
    return doc


def letter_checks(letter: LetterDocument, analysis: Analysis, rules: RuleSet | None = None) -> list[dict[str, str]]:
    """Contrôles propres à la lettre : nom de l'entreprise, intitulé, ≥ 2 éléments de l'annonce, longueur."""
    rules = rules or load_rules()
    issues = []
    body = " ".join(ln.text for ln in letter.lines)
    full = norm(" ".join([letter.subject, body]))
    if analysis.company not in ("", "UNKNOWN") and norm(analysis.company) not in full:
        issues.append({"severity": "high", "check": "entreprise", "detail": f"« {analysis.company} » absent de la lettre"})
    title_words = [w for w in norm(analysis.job_title).split() if len(w) > 3]
    if title_words and not any(w in full for w in title_words):
        issues.append({"severity": "high", "check": "intitule", "detail": "intitulé du poste absent"})
    offer_refs = [ln for ln in letter.lines if ln.kind == "offer_ref"]
    if len(offer_refs) < 2:
        issues.append({"severity": "medium", "check": "personnalisation", "detail": f"{len(offer_refs)} élément(s) de l'annonce cité(s) (min 2)"})
    words = len(re.findall(r"\w+", body))
    low, high = rules.sector(analysis.sector_id).get("letter_style", {}).get("length_words", [200, 340])
    if words < low * 0.7 or words > high * 1.25:
        issues.append({"severity": "low", "check": "longueur", "detail": f"{words} mots (cible {low}-{high})"})
    for ln in letter.lines:
        hard, soft = rules.banned_found(ln.text)
        for p in soft:
            issues.append({"severity": "low", "check": "phrase_creuse", "detail": f"{ln.id} : « {p} »"})
    return issues
