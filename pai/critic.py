"""Critique : contrôles déterministes + jury IA (7 juges) ; boucle CORRECT → RENDER → RECHECK.

Le score (rules/scoring.yaml) mesure, il ne modifie jamais le profil.
"""

from __future__ import annotations

from typing import Any

from .rules import RuleSet, load_rules
from .schemas import Analysis, CvDocument, LetterDocument, Match, Strategy, ValidationReport
from .textnorm import contains_term, norm

GENERIC_TITLES = {"cv", "curriculum vitae", "profil", "candidat", "commercial polyvalent", "chercheur d'emploi", "profil junior"}


def cv_text(doc: CvDocument) -> str:
    return " ".join(ln.text for ln in doc.lines)


def deterministic_critique(cv: CvDocument, analysis: Analysis, match: Match, strategy: Strategy,
                           validation: ValidationReport, rules: RuleSet | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    issues: list[dict[str, Any]] = []
    text_n = norm(cv_text(cv))
    headline = " ".join(ln.text for ln in cv.section_lines("headline"))
    if not headline or norm(headline) in GENERIC_TITLES:
        issues.append({"severity": "high", "type": "titre_generique", "line_ids": ["h1"], "problem": "Titre absent ou générique",
                       "fix": "Reprendre l'intitulé exact du poste visé."})
    summary = cv.section_lines("summary")
    if not summary:
        issues.append({"severity": "medium", "type": "profil_absent", "line_ids": [], "problem": "Pas de résumé de profil",
                       "fix": "Ajouter 2 phrases : qui, et la preuve la plus forte pour l'offre."})
    elif sum(len(ln.text) for ln in summary) > 380:
        issues.append({"severity": "low", "type": "profil_dense", "line_ids": [ln.id for ln in summary],
                       "problem": "Résumé trop long", "fix": "Réduire à 45 mots."})
    for block in cv.experiences:
        if block.featured and not block.bullet_ids:
            issues.append({"severity": "high", "type": "experience_vide", "line_ids": [], "problem": f"{block.title} sans puce",
                           "fix": "Ajouter 2-3 puces prouvées."})
    for ln in cv.section_lines("experience"):
        if len(ln.text) > 130:
            issues.append({"severity": "low", "type": "puce_longue", "line_ids": [ln.id], "problem": "Puce > 130 caractères",
                           "fix": "Couper à 110 caractères."})
    # Mots-clés REQUIRED prouvés mais absents du CV = manque important (-10)
    major_gaps = [c.term for c in match.coverage if c.covered and c.priority == "REQUIRED"
                  and not rules.synonyms.supported_by(c.term, text_n)]
    for term in major_gaps:
        issues.append({"severity": "high", "type": "mot_cle_absent", "line_ids": [], "problem": f"« {term} » est prouvé mais absent du CV",
                       "fix": f"Intégrer « {term} » dans une puce qui le prouve."})
    # Bourrage de mots-clés
    for kw in analysis.keywords:
        count = text_n.count(norm(kw.term))
        if len(kw.term) > 3 and count > 4:
            issues.append({"severity": "medium", "type": "bourrage", "line_ids": [], "problem": f"« {kw.term} » répété {count} fois",
                           "fix": "Garder 2 occurrences utiles."})
    for w in validation.warnings:
        if "Phrase à éviter" in w:
            issues.append({"severity": "low", "type": "phrase_creuse", "line_ids": [w.split(":")[0]], "problem": w, "fix": "Remplacer par une preuve."})
    return {"issues": issues, "major_gaps": major_gaps}


def score_events(cv: CvDocument | None, letter: LetterDocument | None, analysis: Analysis, match: Match, strategy: Strategy,
                 validations: dict[str, ValidationReport], critique: dict[str, Any], rules: RuleSet | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    grid = rules.scoring.get("events", {})
    events: list[dict[str, Any]] = []

    def add(key: str, reason: str) -> None:
        events.append({"event": key, "points": grid[key]["points"], "label": grid[key]["label"], "reason": reason})

    if cv is not None:
        headline = norm(" ".join(ln.text for ln in cv.section_lines("headline")))
        title_words = [w for w in norm(analysis.job_title).split() if len(w) > 3]
        if title_words and all(w in headline for w in title_words[:3]):
            add("good_title", "Titre aligné sur l'intitulé de l'offre")
        elif not headline or headline in GENERIC_TITLES:
            add("weak_title", "Titre générique")
        up = strategy.best.experiences_up
        if up and cv.experiences and cv.experiences[0].experience_id in up or any(b.featured for b in cv.experiences):
            add("good_experience_pick", "Expériences les plus pertinentes mises en avant")
        design = rules.sector(analysis.sector_id).get("cv_style", {}).get("design")
        if design and design == cv.design_profile or cv.design_profile == "hybrid_modern":
            add("design_fit", "Design conforme au profil secteur / ATS")
        for term in critique.get("major_gaps", []):
            add("major_gap", f"« {term} » prouvé mais absent")
    if letter is not None and sum(1 for ln in letter.lines if ln.kind == "offer_ref") >= 2:
        add("personalization", "≥ 2 éléments propres à l'annonce dans la lettre")
    forbidden = sum(v.forbidden_hits for v in validations.values())
    for _ in range(forbidden):
        add("invented_fact", "Fait interdit détecté (ligne supprimée)")
    return {"events": events, "total": sum(e["points"] for e in events)}


def ai_issue_instructions(ai_critique: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Regroupe les corrections IA par ligne ; renvoie aussi les consignes globales."""
    per_line: dict[str, str] = {}
    general: list[str] = []
    for issue in ai_critique.get("issues", []) or []:
        if str(issue.get("severity", "low")) not in ("high", "medium"):
            continue
        fix = f"{issue.get('problem', '')} → {issue.get('fix', '')}".strip(" →")
        ids = [str(i) for i in issue.get("line_ids", []) or []]
        if ids:
            for lid in ids:
                per_line[lid] = (per_line.get(lid, "") + " ; " + fix).strip(" ;")
        else:
            general.append(fix)
    return per_line, general


def keyword_in_text(term: str, text: str) -> bool:
    return contains_term(norm(text), term)
