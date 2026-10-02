"""Matching offre ↔ profil : un maximum de calcul déterministe, l'IA seulement pour la sémantique.

Sorties : MATCH (adéquation), QUALITY (solidité des preuves), RISK (risque de rejet),
avec WHY FIT / WHY NOT / MISSING / STRENGTHS / RISKS et la couverture des mots-clés.
"""

from __future__ import annotations

import re
from datetime import date

from .claims import build_evidence
from .profile import language_level
from .rules import RuleSet, load_rules
from .schemas import Analysis, Fact, KeywordCoverage, MasterProfile, Match
from .textnorm import contains_term, norm

WEIGHTS = {"role": 0.18, "skills": 0.24, "experience": 0.12, "sector": 0.10, "degree": 0.06, "language": 0.08,
           "location": 0.07, "contract": 0.05, "salary": 0.02, "seniority": 0.04, "availability": 0.02, "preferences": 0.02}
PRIORITY_WEIGHT = {"REQUIRED": 3.0, "MUST": 3.0, "IMPORTANT": 2.0, "NICE": 1.0, "UNKNOWN": 1.0}
IDF_REGION = {"paris", "ile-de-france", "la defense", "boulogne-billancourt", "levallois", "neuilly", "saint-denis",
              "issy-les-moulineaux", "nanterre", "courbevoie", "puteaux", "montrouge", "clichy", "rueil-malmaison",
              "massy", "versailles", "montreuil", "saint-ouen", "vincennes", "pantin", "aubervilliers", "ivry", "vitry",
              "creteil", "cergy", "marne-la-vallee", "noisy-le-grand", "roissy", "rungis", "saint-cloud", "suresnes",
              "velizy", "guyancourt", "evry"}  # identique au moteur JS (web/studio/engine.js)


def fact_evidence_index(profile: MasterProfile) -> list[tuple[Fact, str]]:
    index = []
    for f in profile.usable_facts():
        if f.kind in ("contact", "preference"):
            continue
        index.append((f, build_evidence(profile, [f.id]).text))
    return index


def cover_term(term: str, index: list[tuple[Fact, str]], rules: RuleSet) -> KeywordCoverage:
    fact_ids: list[str] = []
    via = ""
    for fact, evidence in index:
        how = rules.synonyms.supported_by(term, evidence)
        if how:
            fact_ids.append(fact.id)
            via = via or how
    return KeywordCoverage(term=term, priority="", covered=bool(fact_ids), fact_ids=fact_ids[:6], via=via)


def _months(start: str | None, end: str | None) -> int:
    def parse(v: str | None, default_month: int) -> date | None:
        if not v:
            return None
        parts = v.split("-")
        return date(int(parts[0]), int(parts[1]) if len(parts) > 1 else default_month, 1)

    s = parse(start, 1)
    e = parse(end, 12) or date.today()
    if not s:
        return 0
    return max(1, (e.year - s.year) * 12 + (e.month - s.month) + 1)


def compute_match(profile: MasterProfile, analysis: Analysis, rules: RuleSet | None = None) -> Match:
    rules = rules or load_rules()
    index = fact_evidence_index(profile)
    scores: dict[str, float] = {}

    # Couverture des mots-clés
    coverage: list[KeywordCoverage] = []
    for kw in analysis.keywords:
        cov = cover_term(kw.term, index, rules)
        cov.priority = kw.priority
        coverage.append(cov)
    total_w = sum(PRIORITY_WEIGHT.get(c.priority, 1) for c in coverage) or 1
    covered_w = sum(PRIORITY_WEIGHT.get(c.priority, 1) for c in coverage if c.covered)
    scores["skills"] = round(100 * covered_w / total_w, 1) if coverage else 50.0

    # Rôle : intitulé visé vs rôles cibles et intitulés occupés
    title_n = norm(analysis.job_title)
    targets = profile.fact("target.roles")
    target_roles = [norm(r) for r in (targets.data.get("roles", []) if targets else [])]
    held = [norm(e.data.get("title", "")) for e in profile.experiences()]
    role = 30.0
    if any(r and (r in title_n or title_n in r) for r in target_roles):
        role = 95.0
    elif any(r and any(w in title_n for w in r.split() if len(w) > 3) for r in target_roles):
        role = 75.0
    if any(h and any(w in title_n for w in h.replace("&", " ").split() if len(w) > 4) for h in held):
        role = max(role, 80.0)
    sector_targets = {"business_development", "commercial", "account_management", "international_vie"}
    if analysis.sector_id in sector_targets:
        role = max(role, 70.0)
    # Secteurs déjà pratiqués (détectés sur les intitulés et responsabilités des expériences)
    from .analyzer import detect_sector

    practiced: set[str] = set()
    for exp in profile.experiences():
        blob = " ".join([exp.data.get("title", "")] + [c.text for c in profile.children(exp.id)])
        sid, sc = detect_sector(exp.data.get("title", ""), blob, rules)
        top = sc.get(sid, 0)
        practiced.update(k for k, v in sc.items() if v >= 2 and v >= 0.25 * top)
    if analysis.sector_id in practiced:
        role = max(role, 75.0)
    if analysis.seniority == "senior":
        role = min(role, 45.0)
    scores["role"] = role

    # Expérience : durée cumulée vs exigence ; pertinence sectorielle
    months = sum(_months(e.data.get("start"), e.data.get("end")) for e in profile.experiences())
    years = months / 12
    need = analysis.experience_years_min
    scores["experience"] = 80.0 if need is None else round(min(100.0, 100 * years / need), 1) if need else 90.0

    sector = rules.sector(analysis.sector_id)
    dom = sector.get("dominant_skills", [])
    dom_cov = [cover_term(s, index, rules).covered for s in dom]
    scores["sector"] = round(100 * sum(dom_cov) / len(dom_cov), 1) if dom_cov else 50.0

    # Diplôme
    edu_text = norm(" ".join(f.text for f in profile.by_kind("education")))
    level_have = 3 if re.search(r"bachelor|licence|bac\+3", edu_text) else 2 if re.search(r"bts|dut|bac\+2", edu_text) else 0
    level_need = {"Bac+5": 5, "Bac+3": 3, "Bac+2": 2, "Bac": 1}.get(analysis.degree_required, 0)
    scores["degree"] = 70.0 if not level_need else 100.0 if level_have >= level_need else 45.0 if level_need - level_have == 2 else 65.0

    # Langues
    lang_scores = []
    for lang in analysis.languages:
        facts = [f for f in profile.by_kind("language") if norm(f.data.get("language", "")).startswith(norm(lang.get("name", ""))[:4])]
        if not facts:
            lang_scores.append(0.0 if lang.get("priority") == "MUST" else 40.0)
            continue
        have = max(language_level(f) for f in facts)
        needed = {"notions": 1, "intermediaire": 3, "courant": 5, "professionnel": 5, "bilingue": 6, "natif": 7,
                  "c1": 5, "c2": 6, "b2": 4, "fluent": 5}.get(norm(str(lang.get("level", ""))), 4)
        lang_scores.append(100.0 if have >= needed else 60.0)
    scores["language"] = round(sum(lang_scores) / len(lang_scores), 1) if lang_scores else 80.0

    # Lieu
    loc = norm(analysis.location)
    mobility = profile.fact("mobility.idf")
    if loc in IDF_REGION and mobility:
        scores["location"] = 100.0
    elif analysis.contract == "VIE":
        scores["location"] = 80.0
    elif loc == "unknown":
        scores["location"] = 60.0
    else:
        scores["location"] = 35.0

    # Contrat, salaire, séniorité, disponibilité, préférences
    wants_vie = any("vie" == r for r in target_roles)
    scores["contract"] = {"CDI": 95.0, "CDD": 75.0, "VIE": 95.0 if wants_vie else 60.0, "Freelance": 45.0,
                          "Alternance": 40.0, "Stage": 35.0, "Intérim": 55.0}.get(analysis.contract, 70.0)
    scores["salary"] = 60.0
    scores["seniority"] = {"junior": 95.0, "confirmé": 70.0, "senior": 30.0}.get(analysis.seniority, 75.0)
    scores["availability"] = 100.0 if profile.fact("avail.immediate") else 60.0
    scores["preferences"] = 100.0 if role >= 75 else 60.0

    match_score = round(sum(scores[k] * w for k, w in WEIGHTS.items()), 1)
    must = [c for c in coverage if c.priority == "REQUIRED"]
    must_cov = sum(1 for c in must if c.covered)
    quality = round(100 * must_cov / len(must), 1) if must else round(scores["skills"], 1)
    risk = 100 - round(0.5 * match_score + 0.5 * quality, 1)

    why_fit, strengths, why_not, missing, risks = [], [], [], [], []
    for c in coverage:
        if c.covered and c.priority in ("REQUIRED", "IMPORTANT"):
            why_fit.append({"text": f"« {c.term} » prouvé ({c.via})", "fact_ids": c.fact_ids[:3]})
        elif not c.covered:
            missing.append({"requirement": c.term, "priority": {"REQUIRED": "MUST"}.get(c.priority, c.priority),
                            "note": "Aucun fait ne le prouve : à ne pas écrire, à préparer pour l'entretien."})
    for f in profile.by_kind("result"):
        if any(f.id in c.fact_ids for c in coverage if c.covered):
            strengths.append({"text": f.text, "fact_ids": [f.id]})
    if scores["seniority"] < 50:
        why_not.append({"text": "Offre orientée profil senior", "fact_ids": []})
    if scores["location"] < 50:
        risks.append({"text": f"Lieu hors mobilité confirmée ({analysis.location})"})
    if scores["degree"] < 60:
        risks.append({"text": f"Diplôme demandé : {analysis.degree_required}"})
    if must and must_cov < len(must):
        risks.append({"text": f"{len(must) - must_cov} mot(s)-clé(s) REQUIRED non prouvé(s)"})
    if analysis.contract == "VIE":
        risks.append({"text": "Éligibilité VIE (âge, nationalité) à vérifier par l'utilisateur"})
    for rsk in analysis.hidden_risks:
        risks.append({"text": rsk})

    return Match(scores=scores, match=match_score, quality=quality, risk=round(risk, 1), coverage=coverage,
                 why_fit=why_fit[:8], why_not=why_not, missing=missing[:10], strengths=strengths[:6], risks=risks)
