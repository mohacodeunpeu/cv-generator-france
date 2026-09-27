"""Application Pack figé : export ZIP (PDF + JSON + Markdown), versions incluses."""

from __future__ import annotations

import io
import json
import re
import zipfile

from .render import letter_paragraphs
from .schemas import ApplicationPack


def slug(text: str, length: int = 40) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text or "pack").strip("_")[:length] or "pack"


def pack_markdown(pack: ApplicationPack) -> str:
    a, m, s = pack.analysis, pack.match, pack.strategy.best
    out = [f"# Application Pack — {a.job_title} · {a.company}", "",
           f"Statut : **{pack.status}** · mode {pack.mode} · fournisseur {pack.provider} · {pack.created_at}", "",
           "## Versions", "", "| offer_v | profile_v | cv_v | letter_v | answers_v | engine_v | prompt_v | rules_v |",
           "|---|---|---|---|---|---|---|---|",
           f"| {pack.versions.offer_v} | {pack.versions.profile_v} | {pack.versions.cv_v} | {pack.versions.letter_v} | "
           f"{pack.versions.answers_v or '—'} | {pack.versions.engine_v} | {pack.versions.prompt_v} | {pack.versions.rules_v} |", "",
           "## Offre", "", f"- Lieu : {a.location} ({a.country}) · Contrat : {a.contract} · Séniorité : {a.seniority}",
           f"- Secteur détecté : {a.sector_id}", f"- Source : {pack.offer.source_type} {pack.offer.source_url}"
           + (" · **SYNTHETIC**" if pack.offer.synthetic else ""), "",
           "## Matching", "", f"MATCH **{m.match}** · QUALITY **{m.quality}** · RISK **{m.risk}**", ""]
    out += ["| Sous-score | Valeur |", "|---|---|"] + [f"| {k} | {v} |" for k, v in m.scores.items()] + [""]
    out += ["### Mots-clés", ""] + [f"- {'✅' if c.covered else '❌'} {c.term} ({c.priority}){' ← ' + ', '.join(c.fact_ids[:3]) if c.covered else ''}"
                                    for c in m.coverage] + [""]
    out += ["## Stratégie", "", f"- Titre : **{s.title}**", f"- Accroche : {s.hook}", f"- Mode ATS : {s.ats_mode} · design {s.design_profile} · photo {s.photo_mode}",
            f"- Expériences mises en avant : {', '.join(s.experiences_up)}", f"- Angle de lettre : {s.letter_angle}", f"- Pourquoi : {s.why}", ""]
    if pack.validation:
        out += ["## Factualité", ""] + [f"- {k} : {v.factuality} % ({v.traced}/{v.total} lignes tracées), faits interdits : {v.forbidden_hits}"
                                       for k, v in pack.validation.items()] + [""]
    if pack.letter:
        out += ["## Lettre", "", pack.letter.subject, "", pack.letter.salutation, ""] + [p + "\n" for p in letter_paragraphs(pack.letter)] + [pack.letter.signature, ""]
    if pack.answers:
        out += ["## Réponses aux questions", ""]
        for ans in pack.answers:
            out += [f"**{ans.question}** ({ans.type}, {ans.confidence})", "", ans.answer or f"➜ À fournir : {ans.ask_user}", ""]
    out += ["## Risques", ""] + [f"- {r}" for r in pack.risks] + ["", "## Prochaine action", "", pack.next_action, ""]
    if pack.missing_profile_data:
        out += ["## Données manquantes du profil", ""] + [f"- {d}" for d in pack.missing_profile_data] + [""]
    return "\n".join(out)


def export_zip(pack: ApplicationPack, files: dict[str, bytes]) -> bytes:
    base = f"{slug(pack.analysis.company, 24)}_{slug(pack.analysis.job_title, 30)}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if "cv.pdf" in files:
            zf.writestr(f"CV_{base}.pdf", files["cv.pdf"])
        if "lettre.pdf" in files:
            zf.writestr(f"Lettre_{base}.pdf", files["lettre.pdf"])
        zf.writestr("pack.json", pack.model_dump_json(indent=2))
        zf.writestr("pack.md", pack_markdown(pack))
        zf.writestr("versions.json", json.dumps(pack.versions.model_dump(), indent=2))
    return buf.getvalue()
