"""CV Architect : OFFRE → PROFIL → POSITIONNEMENT → PLAN DE CONTENU → (rendu) → CRITIQUE → CORRECTION.

Deux voies produisent le même `CvDocument` :
  - déterministe (mode dégradé) : chaque ligne est un fait du profil, sélectionné et ordonné pour l'offre ;
  - IA : contenu rédigé par le fournisseur, chaque ligne liée à ses faits puis passée au validateur.
Les blocs structurels (intitulé, entreprise, dates des expériences, contact) viennent toujours des faits.
"""

from __future__ import annotations

import re
from typing import Any

from .rules import RuleSet, load_rules
from .schemas import Analysis, CvDocument, ExperienceBlock, Fact, Line, MasterProfile, Match, Strategy
from .textnorm import extract_numbers, norm

SECTION_TITLES = {
    "fr": {"summary": "Profil", "experience": "Expérience professionnelle", "skills": "Compétences",
           "education": "Formation", "certifications": "Certifications", "languages": "Langues"},
    "en": {"summary": "Profile", "experience": "Experience", "skills": "Skills", "education": "Education",
           "certifications": "Certifications", "languages": "Languages"},
}
SKILL_GROUPS = {
    "fr": {"commercial": "Commercial", "tools": "Outils", "digital": "Digital"},
    "en": {"commercial": "Sales", "tools": "Tools", "digital": "Digital"},
}
_DIGITAL = {"community management", "strategie de contenu", "planning editorial", "production de contenu", "ux",
            "optimisation conversion", "gestion de projets digitaux", "analyse de performance"}


def _cap(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:] if text else text


def contact_lines(profile: MasterProfile) -> list[str]:
    out = []
    city = profile.fact("contact.city")
    if city and city.usable:
        out.append(city.data.get("city") or city.text)
    for fid in ("contact.phone", "contact.email"):
        value = profile.value(fid)
        if value:
            out.append(value)
    linkedin = profile.value("contact.linkedin")
    if linkedin:
        out.append(re.sub(r"^https?://(www\.)?", "", linkedin).rstrip("/"))
    return out


def experience_blocks(profile: MasterProfile, strategy: Strategy) -> list[ExperienceBlock]:
    up = set(strategy.best.experiences_up)
    blocks = []
    for exp in profile.experiences():
        d = exp.data
        blocks.append(ExperienceBlock(experience_id=exp.id, title=d.get("title", ""), company=d.get("company", ""),
                                      city=d.get("city", ""), period=d.get("period_label", ""), featured=exp.id in up))
    return blocks


def _coverage_score(fact: Fact, match: Match) -> float:
    weights = {"REQUIRED": 3, "IMPORTANT": 2, "NICE": 1}
    return sum(weights.get(c.priority, 1) for c in match.coverage if c.covered and fact.id in c.fact_ids)


def _fact_lines(profile: MasterProfile, ids: list[str], section: str, prefix: str) -> list[Line]:
    lines = []
    for i, fid in enumerate(ids, 1):
        f = profile.fact(fid)
        if f is None or not f.usable:
            continue
        lines.append(Line(id=f"{prefix}{i}", section=section, kind="fact", text=_cap(f.text), fact_ids=[fid]))
    return lines


def language_line(profile: MasterProfile, lang: str) -> Line | None:
    facts = profile.by_kind("language")
    if not facts:
        return None
    toeic = profile.fact("cert.toeic")
    parts, ids = [], []
    for f in facts:
        name, level = f.data.get("language", f.text), f.data.get("level", "")
        label = f"{name} ({level}" + (", TOEIC 915/990" if toeic and toeic.usable and norm(name) == "anglais" else "") + ")"
        parts.append(label)
        ids.append(f.id)
    if toeic and toeic.usable:
        ids.append(toeic.id)
    return Line(id="l1", section="languages", kind="fact", text=" · ".join(parts), fact_ids=ids)


def education_ids(profile: MasterProfile) -> tuple[list[str], list[str]]:
    edu = [f.id for f in profile.by_kind("education")]
    certs = [f.id for f in profile.by_kind("certification") if f.id != "cert.toeic"]
    return edu, certs


def build_cv_deterministic(profile: MasterProfile, analysis: Analysis, match: Match, strategy: Strategy,
                           rules: RuleSet | None = None, max_featured: int = 4, max_other: int = 2) -> CvDocument:
    rules = rules or load_rules()
    lang = "en" if analysis.language_of_offer == "en" else "fr"
    country = rules.country(analysis.country)
    best = strategy.best
    lines: list[Line] = [Line(id="h1", section="headline", kind="headline", text=best.title,
                              fact_ids=["target.roles"] if profile.fact("target.roles") else [],
                              offer_terms=[analysis.job_title])]

    # Profil (2 phrases, uniquement des faits)
    domains = profile.fact("profile.domains")
    if domains and domains.usable:
        lines.append(Line(id="s1", section="summary", kind="claim", text=_cap(domains.text) + ".", fact_ids=[domains.id]))
    if best.hook and best.hook_fact_ids:
        hook_fact = profile.fact(best.hook_fact_ids[0])
        parent = profile.fact(hook_fact.parent) if hook_fact and hook_fact.parent else None
        where = f" ({parent.data.get('company')})" if parent else ""
        lines.append(Line(id="s2", section="summary", kind="claim", text=_cap(best.hook) + where + ".",
                          fact_ids=best.hook_fact_ids))

    # Expériences : puces = faits enfants, les plus pertinents pour l'offre d'abord
    blocks = experience_blocks(profile, strategy)
    for block in blocks:
        children = [f for f in profile.children(block.experience_id) if f.kind in ("result", "responsibility")]
        children.sort(key=lambda f: (-_coverage_score(f, match), f.kind != "result", -len(extract_numbers(f.text))))
        limit = max_featured if block.featured else max_other
        for k, fact in enumerate(children[:limit], 1):
            line = Line(id=f"e.{block.experience_id.split('.', 1)[1]}.b{k}", section="experience", kind="claim",
                        text=_cap(fact.text), fact_ids=[fact.id], experience_id=block.experience_id)
            lines.append(line)
            block.bullet_ids.append(line.id)

    # Compétences : trois groupes, les éléments couverts par l'offre en premier
    groups: dict[str, list[Fact]] = {"commercial": [], "tools": [], "digital": []}
    for f in profile.by_kind("skill"):
        groups["digital" if norm(f.text) in _DIGITAL else "commercial"].append(f)
    groups["tools"] = profile.by_kind("tool")
    for key, facts in groups.items():
        facts.sort(key=lambda f: -_coverage_score(f, match))
        for i, f in enumerate(facts[:6], 1):
            lines.append(Line(id=f"k.{key}.{i}", section="skills", kind="fact", text=f.text, fact_ids=[f.id],
                              group=SKILL_GROUPS[lang][key]))

    edu_ids, cert_ids = education_ids(profile)
    lines += _fact_lines(profile, edu_ids, "education", "d")
    lines += _fact_lines(profile, cert_ids, "certifications", "c")
    toeic = profile.fact("cert.toeic")
    lang_line = language_line(profile, lang)
    if lang_line:
        lines.append(lang_line)
    elif toeic:
        lines += _fact_lines(profile, ["cert.toeic"], "certifications", "ct")

    extras = [fid for fid in ("avail.immediate", "mobility.idf") if profile.fact(fid) and profile.fact(fid).usable]  # type: ignore[union-attr]
    if extras:
        lines.append(Line(id="x1", section="extras", kind="fact",
                          text=" · ".join(profile.value(fid) for fid in extras), fact_ids=extras))

    return CvDocument(language=lang, design_profile=best.design_profile, photo_mode=best.photo_mode,
                      ats_mode=best.ats_mode, paper=country.get("paper", "A4"), draft=not profile.validated,
                      name=profile.value("id.name", profile.candidate_id), contact=contact_lines(profile), lines=lines,
                      experiences=blocks, section_titles=SECTION_TITLES[lang],
                      section_order=["summary", "experience", "skills", "education", "certifications", "languages"],
                      keywords_covered=[c.term for c in match.coverage if c.covered],
                      gaps=[{"keyword": m["requirement"], "why": m.get("note", "")} for m in match.missing],
                      source="deterministic")


def cv_from_ai(payload: dict[str, Any], profile: MasterProfile, analysis: Analysis, match: Match, strategy: Strategy,
               rules: RuleSet | None = None) -> CvDocument:
    """Convertit la sortie IA (prompts/cv_content.md) en CvDocument. Les ids inconnus sont écartés."""
    rules = rules or load_rules()
    base = build_cv_deterministic(profile, analysis, match, strategy, rules)
    lines: list[Line] = []
    head = payload.get("headline") or {}
    lines.append(Line(id="h1", section="headline", kind="headline", text=str(head.get("text") or strategy.best.title),
                      fact_ids=[str(x) for x in head.get("fact_ids", [])], offer_terms=[str(x) for x in head.get("offer_terms", [])]))
    for i, s in enumerate(payload.get("summary") or [], 1):
        lines.append(Line(id=f"s{i}", section="summary", kind="claim", text=str(s.get("text", "")),
                          fact_ids=[str(x) for x in s.get("fact_ids", [])]))

    blocks = {b.experience_id: b for b in base.experiences}
    for b in blocks.values():
        b.bullet_ids = []
    seen: set[str] = set()
    for exp in payload.get("experiences") or []:
        exp_id = str(exp.get("experience_id", ""))
        if exp_id not in blocks or exp_id in seen:
            continue
        seen.add(exp_id)
        for k, bullet in enumerate(exp.get("bullets") or [], 1):
            line = Line(id=f"e.{exp_id.split('.', 1)[1]}.b{k}", section="experience", kind="claim",
                        text=str(bullet.get("text", "")), fact_ids=[str(x) for x in bullet.get("fact_ids", [])],
                        experience_id=exp_id)
            lines.append(line)
            blocks[exp_id].bullet_ids.append(line.id)
    for exp_id, block in blocks.items():  # expérience oubliée par l'IA → puces déterministes
        if exp_id not in seen:
            for ln in base.lines:
                if ln.experience_id == exp_id:
                    lines.append(ln)
                    block.bullet_ids.append(ln.id)

    lang = "en" if analysis.language_of_offer == "en" else "fr"
    for g, group in enumerate(payload.get("skills") or [], 1):
        for i, item in enumerate(group.get("items") or [], 1):
            lines.append(Line(id=f"k{g}.{i}", section="skills", kind="claim", text=str(item.get("label", "")),
                              fact_ids=[str(x) for x in item.get("fact_ids", [])], group=str(group.get("group", ""))))
    usable = {f.id for f in profile.usable_facts()}
    edu = [i for i in payload.get("education_ids") or [] if i in usable] or education_ids(profile)[0]
    certs = [i for i in payload.get("certification_ids") or [] if i in usable and i != "cert.toeic"]
    lines += _fact_lines(profile, edu, "education", "d")
    lines += _fact_lines(profile, certs or education_ids(profile)[1], "certifications", "c")
    lang_line = language_line(profile, lang)
    if lang_line:
        lines.append(lang_line)
    lines += [ln for ln in base.lines if ln.section == "extras"]

    doc = base.model_copy(deep=True)
    doc.lines = lines
    doc.experiences = list(blocks.values())
    doc.keywords_covered = [str(k) for k in payload.get("keywords_covered") or base.keywords_covered]
    doc.gaps = payload.get("gaps") or base.gaps
    doc.source = "ai"
    return doc


def replace_lines(doc: CvDocument, fixes: dict[str, dict[str, Any]]) -> CvDocument:
    """Applique des corrections {line_id: {text, fact_ids}} ; texte vide = suppression."""
    updated = doc.model_copy(deep=True)
    kept: list[Line] = []
    for line in updated.lines:
        fix = fixes.get(line.id)
        if fix is None:
            kept.append(line)
            continue
        text = str(fix.get("text", "")).strip()
        if not text:
            updated.removed_lines.append({"id": line.id, "text": line.text, "reasons": ["supprimée à la correction"]})
            continue
        line.text = text
        line.fact_ids = [str(x) for x in fix.get("fact_ids", line.fact_ids)]
        kept.append(line)
    updated.lines = kept
    for block in updated.experiences:
        block.bullet_ids = [b for b in block.bullet_ids if updated.line(b) is not None]
    return updated


def trim_for_space(doc: CvDocument, step: int) -> CvDocument:
    """Réduit le contenu pour tenir sur une page : puces secondaires, compétences, certifications."""
    updated = doc.model_copy(deep=True)
    drop: set[str] = set()
    if step >= 1:
        for block in updated.experiences:
            if not block.featured and len(block.bullet_ids) > 1:
                drop.update(block.bullet_ids[1:])
    if step >= 2:
        by_group: dict[str, list[Line]] = {}
        for ln in updated.section_lines("skills"):
            by_group.setdefault(ln.group or "", []).append(ln)
        for lines in by_group.values():
            drop.update(ln.id for ln in lines[4:])
        certs = updated.section_lines("certifications")
        drop.update(ln.id for ln in certs[1:])
    if step >= 3:
        for block in updated.experiences:
            if block.featured and len(block.bullet_ids) > 3:
                drop.update(block.bullet_ids[3:])
        summary = updated.section_lines("summary")
        drop.update(ln.id for ln in summary[2:])
    updated.removed_lines += [{"id": ln.id, "text": ln.text, "reasons": ["place (1 page)"]} for ln in updated.lines if ln.id in drop]
    updated.lines = [ln for ln in updated.lines if ln.id not in drop]
    for block in updated.experiences:
        block.bullet_ids = [b for b in block.bullet_ids if b not in drop]
    return updated


def cv_plain_text(doc: CvDocument) -> str:
    """Texte du CV avec les ids de ligne (pour le critique et le juge)."""
    out = [doc.name, " | ".join(doc.contact)]
    for ln in doc.section_lines("headline"):
        out.append(f"[{ln.id}] {ln.text}")
    for ln in doc.section_lines("extras"):
        out.append(f"[{ln.id}] {ln.text}")
    for section in doc.section_order:
        title = doc.section_titles.get(section, section)
        if section == "experience":
            out.append(f"\n## {title}")
            for block in doc.experiences:
                out.append(f"{block.title} — {block.company} ({block.city}) · {block.period}")
                for bid in block.bullet_ids:
                    ln = doc.line(bid)
                    if ln:
                        out.append(f"  [{ln.id}] {ln.text}")
            continue
        lines = doc.section_lines(section)
        if not lines:
            continue
        out.append(f"\n## {title}")
        if section == "skills":
            groups: dict[str, list[Line]] = {}
            for ln in lines:
                groups.setdefault(ln.group or "", []).append(ln)
            for g, items in groups.items():
                out.append(f"{g} : " + ", ".join(f"[{i.id}] {i.text}" for i in items))
        else:
            out.extend(f"[{ln.id}] {ln.text}" for ln in lines)
    return "\n".join(out)
