"""Changements expliqués entre le CV d'origine et le CV ciblé : AVANT / APRÈS / RAISON / PREUVE.

AVANT = la ligne du CV d'origine la plus proche (CV importé) ou, à défaut, le fait du profil tel qu'il est écrit.
APRÈS = la ligne du CV ciblé. RAISON = pourquoi elle change (vocabulaire de l'offre, titre aligné, mise en avant).
PREUVE = les faits du profil qui l'autorisent. Une ligne sans preuve n'existe pas dans le CV ciblé.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from ..schemas import CvDocument, MasterProfile
from ..textnorm import norm

SECTIONS = {"headline": "Titre", "summary": "Profil", "experience": "Expérience", "skills": "Compétences",
            "education": "Formation", "certifications": "Certifications", "languages": "Langues", "extras": "Informations"}


def _closest(text: str, candidates: list[str]) -> tuple[str, float]:
    n = norm(text)
    best, score = "", 0.0
    for c in candidates:
        r = SequenceMatcher(None, n, norm(c)).ratio()
        if r > score:
            best, score = c, r
    return best, score


def explain(cv: CvDocument, profile: MasterProfile, original_text: str | None = None) -> dict[str, Any]:
    original = [ln.strip(" -•·*") for ln in (original_text or "").splitlines() if len(ln.strip()) > 3]
    changes: list[dict[str, Any]] = []
    unchanged = 0
    used: set[str] = set()
    for ln in cv.lines:
        facts = [f for f in (profile.fact(fid) for fid in ln.fact_ids) if f is not None]
        used.update(f.id for f in facts)
        if original:
            before, sim = _closest(ln.text, original)
            before = before if sim >= 0.45 else ""
        else:
            before = facts[0].text if facts and ln.section != "headline" else ""
        if norm(before).rstrip(".") == norm(ln.text).rstrip("."):
            unchanged += 1
            continue
        if ln.section == "headline":
            roles = [norm(r) for r in ((profile.fact("target.roles").data.get("roles", []) if profile.fact("target.roles") else []))]
            declared = any(r and (r in norm(ln.text) or norm(ln.text) in r) for r in roles)
            reason = ("Titre aligné sur le poste visé, qui fait partie des rôles déclarés du profil." if declared else
                      "Titre = intitulé du poste visé par cette candidature (ce n'est pas un poste déjà occupé).")
        elif ln.offer_terms:
            reason = "Reprend les mots de l'offre : " + ", ".join(ln.offer_terms[:4]) + "."
        elif not before:
            reason = "Ajoutée depuis le profil : ce fait prouve une exigence de l'offre."
        else:
            reason = "Reformulée pour être plus directe (même fait, même sens)."
        changes.append({"line_id": ln.id, "section": SECTIONS.get(ln.section, ln.section), "before": before, "after": ln.text,
                        "reason": reason, "proof": [{"id": f.id, "text": f.text, "status": f.status} for f in facts]})
    dropped = []
    for exp in profile.experiences():
        left = [c for c in profile.children(exp.id) if c.kind in ("result", "responsibility") and c.usable and c.id not in used]
        if left:
            dropped.append({"experience": exp.data.get("company") or exp.text, "count": len(left),
                            "reason": "Moins liées à cette offre (place limitée) ; elles restent dans le CV maître."})
    return {"changes": changes, "unchanged": unchanged, "dropped": dropped,
            "rule": "Aucune ligne sans preuve : chaque APRÈS cite les faits qui l'autorisent."}
