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
           ]
    if pack.ats:
        sc = pack.ats["score"]
        out += ["## Score PAI", "", f"**{sc['value']} %**" + ("" if sc.get("complete") else " (provisoire)") + f" — {sc['disclaimer']}", "",
                "| Dimension | % | Résumé |", "|---|---|---|"]
        out += [f"| {d['label']} | {d['value'] if d['available'] else '—'} | {d['summary']} |" for d in pack.ats["dimensions"]] + [""]
        req = pack.ats.get("requirements", {})
        for key, title in (("proven", "Prouvé"), ("plausible", "Correspondance possible"), ("unproven", "Non prouvé")):
            if req.get(key):
                out += [f"### {title}", ""] + [f"- {r['text']} ({r['class_label']}){' — ' + r['proof']['note'] if r['proof'].get('note') else ''}"
                                             for r in req[key]] + [""]
        if pack.ats.get("changes", {}).get("changes"):
            out += ["### Changements (avant → après, raison, preuve)", ""]
            for c in pack.ats["changes"]["changes"][:20]:
                proof = ", ".join(p["id"] for p in c["proof"]) or "—"
                out += [f"- **{c['section']}** : « {c['before'] or '—'} » → « {c['after']} » — {c['reason']} (preuve : {proof})"]
            out += [""]
    out += ["## Matching (détail interne)", "", f"Correspondance {m.match} · exigences obligatoires prouvées {m.quality} % · risque {m.risk}", ""]
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
        if pack.ats:
            zf.writestr("analyse_ats.json", json.dumps(pack.ats, ensure_ascii=False, indent=2, default=str))
    return buf.getvalue()
