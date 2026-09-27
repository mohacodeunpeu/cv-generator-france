"""Analyse d'offre : extraction déterministe, puis enrichissement IA (si disponible).

Le déterministe donne une base vérifiable (contrat, lieu, salaire, langues, outils,
mots-clés, secteur). L'IA complète (missions, priorités, « ce que le recruteur veut
vraiment »), sans pouvoir écraser une valeur déterministe par UNKNOWN.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .claims import LANGUAGES, LEVEL_WORDS, TOOLS
from .rules import RuleSet, load_rules
from .schemas import Analysis, Keyword, Offer, Skill
from .textnorm import contains_term, norm, unique

CITIES = {
    "paris": "FR", "ile-de-france": "FR", "la defense": "FR", "boulogne-billancourt": "FR", "levallois": "FR",
    "neuilly": "FR", "saint-denis": "FR", "issy-les-moulineaux": "FR", "nanterre": "FR", "courbevoie": "FR",
    "puteaux": "FR", "montrouge": "FR", "clichy": "FR", "rueil-malmaison": "FR", "massy": "FR", "versailles": "FR",
    "montreuil": "FR", "saint-ouen": "FR", "vincennes": "FR", "pantin": "FR", "aubervilliers": "FR", "ivry": "FR",
    "vitry": "FR", "creteil": "FR", "cergy": "FR", "marne-la-vallee": "FR", "noisy-le-grand": "FR", "roissy": "FR",
    "rungis": "FR", "saint-cloud": "FR", "suresnes": "FR", "velizy": "FR", "guyancourt": "FR", "evry": "FR",
    "lyon": "FR", "marseille": "FR", "lille": "FR", "bordeaux": "FR", "toulouse": "FR", "nantes": "FR", "nice": "FR",
    "strasbourg": "FR", "rennes": "FR", "montpellier": "FR", "grenoble": "FR",
    "bruxelles": "BE", "brussels": "BE", "geneve": "CH", "lausanne": "CH", "zurich": "CH", "luxembourg": "LU",
    "londres": "GB", "london": "GB", "dublin": "IE", "madrid": "ES", "barcelone": "ES", "barcelona": "ES",
    "lisbonne": "PT", "lisbon": "PT", "milan": "IT", "berlin": "DE", "munich": "DE", "amsterdam": "NL",
    "dubai": "AE", "abu dhabi": "AE", "new york": "US", "montreal": "CA", "toronto": "CA", "singapour": "SG",
    "singapore": "SG", "shanghai": "CN", "hong kong": "HK", "casablanca": "MA", "tunis": "TN",
}
COUNTRIES = {"france": "FR", "belgique": "BE", "suisse": "CH", "luxembourg": "LU", "royaume-uni": "GB",
             "united kingdom": "GB", "espagne": "ES", "spain": "ES", "portugal": "PT", "italie": "IT", "allemagne": "DE",
             "germany": "DE", "pays-bas": "NL", "etats-unis": "US", "usa": "US", "canada": "CA", "emirats": "AE",
             "maroc": "MA", "tunisie": "TN", "chine": "CN", "singapour": "SG"}

_MUST = re.compile(r"impératif|imperatif|requis|exig|indispensable|obligatoire|maîtrise|maitrise|must|required|minimum|essential|"
                   r"vous avez|vous disposez|vous justifiez|nécessaire|necessaire|essentiel")
_NICE = re.compile(r"un plus|idéalement|idealement|apprécié|apprecie|souhaité|souhaite|bonus|nice to have|serait un atout|"
                   r"est un atout|appréciée|appreciee|preferred|a plus|strong plus|advantage|un atout")
_MISSION_HEAD = re.compile(r"^\s*(vos |les |tes )?(missions?|responsabilit|ce que vous ferez|votre r[oô]le|au quotidien|"
                           r"what you.ll do|responsibilities|your role|le poste)", re.I)
_PROFILE_HEAD = re.compile(r"^\s*(votre |le |ton )?(profil|compétences|competences|qualifications|requirements|"
                           r"what we.re looking for|vous êtes|vous etes|ce que nous recherchons)", re.I)
_BULLET = re.compile(r"^\s*([-•*·▪►✓✔]|\d+[.)])\s*")


def _best_priority(sentences: list[str], term: str) -> tuple[str, str]:
    """La phrase la plus exigeante qui cite le terme décide de sa priorité."""
    best, best_rank = "", 3
    for sentence in sentences:
        sn = norm(sentence)
        if not contains_term(sn, term):
            continue
        rank = 0 if _MUST.search(sn) else 2 if _NICE.search(sn) else 1
        if rank < best_rank:
            best, best_rank = sentence, rank
    return best[:160], {0: "MUST", 1: "IMPORTANT", 2: "NICE", 3: "IMPORTANT"}[best_rank]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def detect_language(text: str) -> str:
    t = f" {norm(text)} "
    fr = sum(t.count(f" {w} ") for w in ("le", "la", "les", "des", "vous", "nous", "et", "pour", "une", "avec"))
    en = sum(t.count(f" {w} ") for w in ("the", "and", "you", "we", "with", "for", "our", "your", "will", "to"))
    return "en" if en > fr * 1.2 else "fr"


_CONTRACT_RULES = [
    ("VIE", r"(?<![a-z])v\.?i\.?e\.?(?![a-z])|volontariat international"),
    ("CDI", r"\bcdi\b|contrat a duree indeterminee|\bpermanent\b"),
    ("CDD", r"\bcdd\b|contrat a duree determinee|fixed-term"),
    ("Alternance", r"\balternance\b|apprentissage|contrat pro"),
    ("Stage", r"\bstage\b|stagiaire|internship"),
    ("Freelance", r"freelance|independant|auto-entrepreneur"),
    ("Intérim", r"mission d'interim|contrat d'interim|\binterim\b"),
]


def detect_contract(t: str, head: str = "") -> str:
    """Le titre et les premières lignes priment (« stage, alternance ou CDI » dans le profil ne compte pas)."""
    for zone in (norm(head), t):
        if not zone:
            continue
        hits = [(m.start(), label) for label, pattern in _CONTRACT_RULES for m in [re.search(pattern, zone)] if m]
        if hits:
            if zone is not t or len(hits) == 1:
                return min(hits)[1]
            return next(label for label, pattern in _CONTRACT_RULES if re.search(pattern, t))
    return "UNKNOWN"


def detect_salary(text: str) -> dict[str, Any]:
    t = norm(text).replace(" ", " ")
    m = re.search(r"(\d{2,3})\s?(?:k|000)?\s?(?:€|eur|euros)?\s?(?:-|a|à|to)\s?(\d{2,3})\s?(k|000)\s?(€|eur|euros)?", t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        period = "year" if lo >= 15 else "UNKNOWN"
        return {"min": lo * 1000, "max": hi * 1000, "currency": "EUR", "period": period, "raw": m.group(0)}
    m = re.search(r"(\d{2})\s?(\d{3})\s?(?:€|eur|euros)\s*(brut|bruts)?\s*(annuel|par an|/an|mensuel|par mois|/mois)?", t)
    if m:
        value = int(m.group(1) + m.group(2))
        period = "month" if m.group(4) and "mois" in m.group(4) or m.group(4) == "mensuel" else "year"
        return {"min": value, "max": value, "currency": "EUR", "period": period, "raw": m.group(0)}
    m = re.search(r"(\d{2,3})\s?k\s?(?:€|eur)", t)
    if m:
        return {"min": int(m.group(1)) * 1000, "max": None, "currency": "EUR", "period": "year", "raw": m.group(0)}
    return {"min": None, "max": None, "currency": "EUR", "period": "UNKNOWN", "raw": ""}


def detect_location(text: str) -> tuple[str, str]:
    t = norm(text)
    for city, cc in CITIES.items():
        if contains_term(t, city):
            return city.title().replace("Ile-De-France", "Île-de-France"), cc
    for name, cc in COUNTRIES.items():
        if contains_term(t, name):
            return name.title(), cc
    return "UNKNOWN", "UNKNOWN"


def detect_seniority(t: str) -> tuple[str, float | None]:
    years = None
    m = re.search(r"(\d{1,2})\s?(?:\+|a \d+)?\s?ans? (?:d'experience|minimum|d'exp)", t) or \
        re.search(r"minimum (\d{1,2}) ans|au moins (\d{1,2}) ans|(\d{1,2})\+? years", t)
    if m:
        years = float(next(g for g in m.groups() if g))
    if years is not None and years >= 6 or re.search(r"\bsenior\b|head of|directeur|directrice|10 ans", t):
        return "senior", years
    if re.search(r"junior|debutant|premiere experience|jeune diplome|0 a 2 ans|entry level|graduate", t) or \
            (years is not None and years <= 2):
        return "junior", years
    if re.search(r"confirme|experimente|\b3 a 5 ans\b", t) or (years and years >= 3):
        return "confirmé", years
    return "UNKNOWN", years


def detect_degree(t: str) -> str:
    """Le niveau explicite (Bac+N) prime ; « Bac+3 à Bac+5 » → Bac+3 (minimum exigé)."""
    explicit = [int(n) for n in re.findall(r"bac\s?\+\s?([2-5])", t)]
    if explicit:
        return f"Bac+{min(explicit)}"
    for label, pattern in [("Bac+5", r"\bmaster\b|\bmba\b|grande ecole|\bmsc\b"),
                           ("Bac+3", r"\blicence\b|\bbachelor|ecole de commerce|universit"),
                           ("Bac+2", r"\bbts\b|\bdut\b|\bbut\b"), ("Bac", r"\bbac\b|baccalaureat")]:
        if re.search(pattern, t):
            return label
    return "UNKNOWN"


def detect_remote(t: str) -> str:
    if re.search(r"full remote|100 ?% (remote|teletravail)|teletravail total", t):
        return "full"
    if re.search(r"teletravail|hybride|remote partiel|jours? de remote|hybrid", t):
        return "hybrid"
    if re.search(r"sur site|presentiel|on-site|onsite", t):
        return "onsite"
    return "UNKNOWN"


def detect_sector(title: str, text: str, rules: RuleSet) -> tuple[str, dict[str, float]]:
    tn, xn = norm(title), norm(text)
    scores: dict[str, float] = {}
    for sid, sector in rules.sectors.items():
        detect = sector.get("detect") or {}
        s = 0.0
        for kw in detect.get("title_keywords", []):
            if contains_term(tn, kw):
                s += 5
            elif contains_term(xn, kw):
                s += 1
        for kw in detect.get("text_keywords", []):
            if contains_term(xn, kw):
                s += 1
        scores[sid] = s
    best = max(scores, key=lambda k: scores[k]) if scores and max(scores.values()) > 0 else "commercial"
    return best, scores


def _section_bullets(lines: list[str], head: re.Pattern[str]) -> list[str]:
    out: list[str] = []
    active = False
    for line in lines:
        if head.search(line):
            active = True
            continue
        if active:
            if (_PROFILE_HEAD.search(line) or _MISSION_HEAD.search(line)) and not _BULLET.match(line):
                break
            if _BULLET.match(line) or (len(line) > 25 and len(out) < 12):
                cleaned = _BULLET.sub("", line).strip()
                if 8 < len(cleaned) < 220:
                    out.append(cleaned)
            elif out and len(line) < 60 and line.endswith(":"):
                break
    return out[:10]


def deterministic_analysis(offer: Offer, rules: RuleSet | None = None) -> Analysis:
    rules = rules or load_rules()
    text = offer.text
    t = norm(text)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    title = offer.title_hint or (lines[0][:120] if lines else "UNKNOWN")
    location, country = detect_location(text)
    seniority, years = detect_seniority(t)
    contract = detect_contract(t, head=" ".join([offer.title_hint, lines[0] if lines else ""]))
    sector_id, sector_scores = detect_sector(title, text, rules)
    if contract == "VIE":
        sector_id = "international_vie"  # le VIE est décisif, quel que soit le métier

    # Zone utile : à partir du premier intitulé « missions » ou « profil » (la présentation de
    # l'entreprise ne produit pas de mots-clés : « maroquinier français » n'est pas une exigence de langue).
    start = next((i for i, ln in enumerate(lines) if _MISSION_HEAD.search(ln) or _PROFILE_HEAD.search(ln)), None)
    useful_lines = [lines[0]] + lines[start:] if start is not None and start > 0 else lines
    useful = "\n".join(useful_lines)
    u = norm(useful)
    sentences = _sentences(useful)

    # Compétences : vocabulaire des profils secteurs + groupes d'équivalences
    vocab: list[str] = []
    for sector in rules.sectors.values():
        vocab += sector.get("dominant_skills", []) + sector.get("vocabulary", [])
    for group in rules.synonyms.groups:
        vocab += group[:2]
    vocab = unique(v for v in vocab if len(v) > 2 and norm(v) not in _NOT_SKILLS)
    skills: list[Skill] = []
    for term in vocab:
        if not contains_term(u, term):
            continue
        sentence, priority = _best_priority(sentences, term)
        if norm(term) in _SOFT_SKILLS and priority != "MUST":
            priority = "NICE"
        skills.append(Skill(name=term, priority=priority, evidence=sentence[:160]))
    tools = [tool for tool in TOOLS if contains_term(u, tool) and tool not in ("ats",)]

    languages: list[dict[str, Any]] = []
    for word, code in LANGUAGES.items():
        if code in [lang["code"] for lang in languages] or not contains_term(u, word):
            continue
        mentions = [s for s in sentences if contains_term(norm(s), word)]
        sentence = max(mentions, key=lambda s: (bool(_MUST.search(norm(s)) or re.search(r"essential", norm(s))),
                                                any(contains_term(norm(s), lvl) for lvl in LEVEL_WORDS)), default="")
        sn = norm(sentence)
        level = next((lvl for lvl in LEVEL_WORDS if contains_term(sn, lvl)), "")
        if not (level or _MUST.search(sn) or _NICE.search(sn) or re.search(r"langue|language|parl|speak|advantage|atout", sn)):
            continue  # langue citée hors exigence (nationalité, marché…)
        languages.append({"name": word.capitalize(), "code": code, "level": level or "UNKNOWN",
                          "priority": "MUST" if _MUST.search(sn) or re.search(r"essential|imperatif", sn)
                          else "NICE" if _NICE.search(sn) or re.search(r"advantage|atout", sn) else "IMPORTANT"})

    to_kw = {"MUST": "REQUIRED", "NICE": "NICE", "IMPORTANT": "IMPORTANT", "UNKNOWN": "IMPORTANT"}
    for hard in HARD_REQUIREMENTS:
        if contains_term(u, hard):
            sentence, prio = _best_priority(sentences, hard)
            skills.append(Skill(name=hard, priority=prio, evidence=sentence))
    keywords: list[Keyword] = [Keyword(term=s.name, priority=to_kw[s.priority]) for s in skills]  # type: ignore[arg-type]
    for tool in tools:
        _, tool_priority = _best_priority(sentences, tool)
        prio = to_kw[tool_priority]
        keywords.append(Keyword(term=tool.upper() if len(tool) <= 3 else tool.title(), priority=prio))
    for lang in languages:
        keywords.append(Keyword(term=lang["name"], priority=to_kw[lang["priority"]]))  # type: ignore[arg-type]

    missions = _section_bullets(lines, _MISSION_HEAD)
    profile_reqs = _section_bullets(lines, _PROFILE_HEAD)
    return Analysis(
        company=offer.company_hint or "UNKNOWN",
        job_title=clean_title(title),
        location=location, country=country,
        contract=contract, salary=detect_salary(text),
        seniority=seniority, experience_years_min=years, degree_required=detect_degree(t),
        missions=missions, skills=skills, tools=tools, languages=languages,
        remote=detect_remote(t), sector=rules.sector(sector_id).get("name", sector_id),
        recruiter_wants={"explicit": profile_reqs[:6], "inferred": []},
        keywords=_dedupe_keywords(keywords), language_of_offer=detect_language(text),
        sector_id=sector_id, sector_scores=sector_scores, source="deterministic",
    )


def clean_title(title: str) -> str:
    t = re.sub(r"\s*[\(\[]?\s*(h\s*/\s*f|f\s*/\s*h|m\s*/\s*f|f\s*/\s*m|h/f/x|x/f/h)\s*[\)\]]?", "", title, flags=re.I)
    t = re.sub(r"\s*[-–—|]\s*(cdi|cdd|stage|alternance|freelance|vie|v\.i\.e|interim|intérim)\b.*$", "", t, flags=re.I)
    return t.strip(" -–|,") or "UNKNOWN"


HARD_REQUIREMENTS = ["permis b", "permis de conduire", "vehicule personnel", "casier judiciaire vierge", "titre de sejour",
                     "nationalite", "passeport", "habilitation electrique", "cariste"]
_SOFT_SKILLS = {"organisation", "communication", "autonomie", "adaptabilite", "presentation", "rigueur", "tenacite",
                "ecoute", "polyvalence", "reactivite", "patience", "precision", "discretion", "fiabilite"}
_NOT_SKILLS = {"business france", "filiale", "logistique", "zone geographique", "marche local", "implantation",
               "maison", "boutique", "store", "hotel", "hotellerie"}


def _singular(term_norm: str) -> str:
    words = term_norm.split(" ")
    words[-1] = words[-1][:-1] if len(words[-1]) > 3 and words[-1].endswith("s") else words[-1]
    return " ".join(words)


def _dedupe_keywords(keywords: list[Keyword]) -> list[Keyword]:
    """Un seul mot-clé par notion : pluriels fusionnés, forme courte absorbée par la forme longue."""
    rank = {"REQUIRED": 0, "IMPORTANT": 1, "NICE": 2}
    best: dict[str, Keyword] = {}
    for kw in keywords:
        key = _singular(norm(kw.term))
        if key not in best or rank[kw.priority] < rank[best[key].priority]:
            best[key] = kw
    keys = list(best)
    for short in keys:
        for long in keys:
            if short != long and short in best and long in best and re.search(rf"(?<![a-z]){re.escape(short)}(?![a-z])", long):
                if rank[best[short].priority] < rank[best[long].priority]:
                    best[long].priority = best[short].priority
                del best[short]
                break
    return sorted(best.values(), key=lambda k: rank[k.priority])[:24]


def merge_ai_analysis(base: Analysis, ai: dict[str, Any], rules: RuleSet | None = None) -> Analysis:
    """Fusionne la sortie IA : l'IA complète, le déterministe n'est jamais remplacé par UNKNOWN."""
    rules = rules or load_rules()
    merged = base.model_dump()
    for key, value in ai.items():
        if value in (None, "", "UNKNOWN", [], {}):
            continue
        if key in ("sector_id", "sector_scores", "source"):
            continue
        if key == "salary" and isinstance(value, dict) and not value.get("min") and base.salary.get("min"):
            continue
        if key == "country" and base.country != "UNKNOWN" and value != base.country:
            continue
        merged[key] = value
    merged["source"] = "ai+deterministic"
    analysis = Analysis.model_validate(merged)
    # Le secteur reste déterministe (profils /sector_profiles) ; l'IA ne le choisit que si rien n'a été détecté.
    analysis.sector_id, analysis.sector_scores = base.sector_id, base.sector_scores
    if not any(base.sector_scores.values()):
        sector_id, scores = detect_sector(analysis.job_title, " ".join([analysis.job_title, *analysis.missions]), rules)
        analysis.sector_id, analysis.sector_scores = sector_id, scores
    if analysis.contract == "VIE":
        analysis.sector_id = "international_vie"
    return analysis


def analysis_json_for_prompt(analysis: Analysis) -> str:
    data = analysis.model_dump(exclude={"sector_scores"})
    return json.dumps(data, ensure_ascii=False)
