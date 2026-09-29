"""Stratégie de positionnement A/B/C (déterministe par défaut, IA si disponible)."""

from __future__ import annotations

from .analyzer import clean_title
from .rules import RuleSet, load_rules
from .schemas import Analysis, MasterProfile, Match, Strategy, StrategyChoice
from .textnorm import extract_numbers, norm


def _experience_relevance(profile: MasterProfile, match: Match) -> dict[str, float]:
    covered_ids = {fid for c in match.coverage if c.covered for fid in c.fact_ids}
    weights = {"REQUIRED": 3, "IMPORTANT": 2, "NICE": 1}
    scores: dict[str, float] = {}
    for exp in profile.experiences():
        family = {exp.id} | {f.id for f in profile.children(exp.id)}
        score = 0.0
        for c in match.coverage:
            if c.covered and family & set(c.fact_ids):
                score += weights.get(c.priority, 1)
        score += 0.5 * len(family & covered_ids)
        scores[exp.id] = score
    return scores


def best_hook(profile: MasterProfile, match: Match, exp_ids: list[str]) -> tuple[str, list[str]]:
    covered = {fid for c in match.coverage if c.covered for fid in c.fact_ids}
    candidates = []
    for exp_id in exp_ids:
        for f in profile.children(exp_id):
            if f.kind != "result":
                continue
            score = (2 if f.id in covered else 0) + (1 if extract_numbers(f.text) else 0)
            candidates.append((score, f))
    if not candidates:
        return "", []
    candidates.sort(key=lambda x: -x[0])
    fact = candidates[0][1]
    return fact.text, [fact.id]


def deterministic_strategy(profile: MasterProfile, analysis: Analysis, match: Match, rules: RuleSet | None = None) -> Strategy:
    rules = rules or load_rules()
    sector = rules.sector(analysis.sector_id)
    style = sector.get("cv_style", {})
    country = rules.country(analysis.country)
    relevance = _experience_relevance(profile, match)
    ordered = sorted(relevance, key=lambda k: -relevance[k])
    up = [e for e in ordered if relevance[e] > 0][:2] or ordered[:1]
    down = [e for e in ordered if e not in up]

    # Le titre du CV est l'intitulé VISÉ (celui de l'offre), jamais un poste présenté comme occupé.
    title = clean_title(analysis.job_title) if analysis.job_title not in ("", "UNKNOWN") else ""
    if not title:
        targets = profile.fact("target.roles")
        roles = targets.data.get("roles", []) if targets else []
        title = roles[0] if roles else "Business Developer"

    key_skills: list[str] = []
    for c in match.coverage:
        if c.covered:
            for fid in c.fact_ids:
                f = profile.fact(fid)
                if f and f.kind in ("skill", "tool", "language", "certification") and fid not in key_skills:
                    key_skills.append(fid)
    hook, hook_ids = best_hook(profile, match, up)
    photo_rule = country.get("photo", "never")
    ats_mode = style.get("ats_mode", "HYBRID")
    design = style.get("design", "hybrid_modern")
    if design == "human_premium" and ats_mode != "HUMAN_FIRST":
        design = "hybrid_modern"

    def choice(key: str, angle: str, mode: str, design_id: str) -> dict:
        return {"key": key, "angle": angle, "title": title, "hook": hook, "hook_fact_ids": hook_ids,
                "experiences_up": up, "experiences_down": down, "key_skill_fact_ids": key_skills[:8],
                "ats_mode": mode, "design_profile": design_id, "strengths": [], "risks": [], "score": 0}

    options = [
        choice("A", "ATS / mots-clés : couverture maximale des REQUIRED prouvés", "ATS_FIRST", "ats_classic"),
        choice("B", "Récit humain : preuves chiffrées et trajectoire", "HUMAN_FIRST",
               "human_premium" if sector.get("cv_style", {}).get("design") == "human_premium" else "hybrid_modern"),
        choice("C", "Hybride : lisible en 10 s et robuste ATS", "HYBRID", "hybrid_modern"),
    ]
    chosen = {"ATS_FIRST": "A", "HUMAN_FIRST": "B"}.get(ats_mode, "C")
    missing_must = [m["requirement"] for m in match.missing if m.get("priority") == "MUST"]
    risks = [r["text"] for r in match.risks]
    if missing_must:
        risks.append("Non prouvé (ne pas écrire, préparer l'entretien) : " + ", ".join(missing_must[:5]))
    best = StrategyChoice(
        title=title, hook=hook, hook_fact_ids=hook_ids, experiences_up=up, experiences_down=down,
        key_skill_fact_ids=key_skills[:8], ats_mode=ats_mode if chosen != "C" else "HYBRID", design_profile=design,
        photo_mode="OFF" if photo_rule in ("never", "discouraged") or not profile.by_kind("media") else "HEADER",
        letter_angle=sector.get("letter_style", {}).get("tone", "factuel"),
        channel="Candidature via le lien de l'offre (PAI n'envoie rien)",
        risks=risks, next_action="Relire le pack, valider le profil si ce n'est pas fait, puis postuler soi-même.",
        why=f"Secteur « {sector.get('name', analysis.sector_id)} » : {style.get('summary_angle', '')}".strip(),
    )
    return Strategy(options=options, comparison="Choix déterministe selon le profil secteur.", chosen=chosen, best=best,
                    source="deterministic")


def sanitize_strategy(strategy: Strategy, profile: MasterProfile, analysis: Analysis, rules: RuleSet | None = None) -> Strategy:
    """Garde-fous sur une stratégie IA : ids existants, photo conforme au pays, design cohérent."""
    rules = rules or load_rules()
    best = strategy.best
    known = {f.id for f in profile.usable_facts()}
    best.experiences_up = [e for e in best.experiences_up if e in known]
    best.experiences_down = [e for e in best.experiences_down if e in known]
    all_exps = [e.id for e in profile.experiences()]
    for e in all_exps:
        if e not in best.experiences_up and e not in best.experiences_down:
            best.experiences_down.append(e)
    best.key_skill_fact_ids = [f for f in best.key_skill_fact_ids if f in known]
    best.hook_fact_ids = [f for f in best.hook_fact_ids if f in known]
    photo_rule = rules.country(analysis.country).get("photo", "never")
    if photo_rule in ("never", "discouraged") or not profile.by_kind("media"):
        best.photo_mode = "OFF"
    if best.design_profile not in rules.designs:
        best.design_profile = "hybrid_modern"
    if best.design_profile == "human_premium" and best.ats_mode != "HUMAN_FIRST":
        best.design_profile = "hybrid_modern"
    if norm(best.title) in ("", "unknown"):
        best.title = clean_title(analysis.job_title)
    return strategy
