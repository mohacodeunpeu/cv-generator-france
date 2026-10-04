"""Master Profile : chargement, versions, validation, import/export.

Le profil appartient à l'utilisateur. Chaque modification crée une nouvelle version ;
une version validée ne change plus (on repart d'une copie). Tant qu'aucune version
n'est validée, tous les documents portent le badge « BROUILLON — PROFIL NON VALIDÉ ».
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable

from . import paths
from .schemas import Fact, MasterProfile, ProfileEvent, ReviewItem, now_iso
from .textnorm import stable_hash

PROFILE_FILE = "master_profile.json"
LEVELS = {"notions": 1, "debutant": 1, "a1": 1, "a2": 2, "intermediaire": 3, "b1": 3, "b2": 4,
          "courant": 5, "professionnel": 5, "c1": 5, "bilingue": 6, "c2": 6, "natif": 7, "langue maternelle": 7}


def profile_path() -> Path:
    return paths.DATA_DIR / PROFILE_FILE


def load_profile(path: Path | None = None) -> MasterProfile:
    target = path or profile_path()
    if not target.exists():
        raise FileNotFoundError(
            f"Aucun Master Profile trouvé ({target}). Lancez `python -m pai bootstrap-profile` "
            "ou importez un export JSON (`python -m pai import-profile fichier.json`)."
        )
    return MasterProfile.model_validate_json(target.read_text(encoding="utf-8"))


def save_profile(profile: MasterProfile, path: Path | None = None) -> Path:
    paths.ensure_data_dirs()
    target = path or profile_path()
    target.write_text(profile.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    versions_dir = target.parent / "profile_versions"
    versions_dir.mkdir(exist_ok=True)
    (versions_dir / f"v{profile.version}.json").write_text(profile.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    return target


def profile_hash(profile: MasterProfile) -> str:
    facts = [(f.id, f.text, f.status, json.dumps(f.data, sort_keys=True, ensure_ascii=False)) for f in profile.facts]
    return stable_hash(facts, 10)


def profile_version_tag(profile: MasterProfile) -> str:
    return f"v{profile.version}-{profile_hash(profile)[:6]}{'' if profile.validated else '-draft'}"


# ── Modifications (toujours versionnées) ─────────────────────────────────────

def _new_version(profile: MasterProfile, action: str, detail: str) -> MasterProfile:
    updated = profile.model_copy(deep=True)
    updated.version = profile.version + 1
    updated.validated = False
    updated.validated_at = None
    updated.history.append(ProfileEvent(action=action, detail=detail))
    return updated


def set_fact_status(profile: MasterProfile, fact_id: str, status: str, note: str = "") -> MasterProfile:
    fact = profile.fact(fact_id)
    if fact is None:
        raise KeyError(f"Fait inconnu : {fact_id}")
    updated = _new_version(profile, "status", f"{fact_id}: {fact.status} → {status}")
    target = updated.fact(fact_id)
    assert target is not None
    target.status = status  # type: ignore[assignment]
    target.updated_at = now_iso()
    if status in ("CONFIRMED", "FORBIDDEN"):
        target.needs_confirmation = False
    if note:
        target.note = note
    updated.review_queue = [r for r in updated.review_queue if r.fact_id != fact_id]
    return updated


def upsert_fact(profile: MasterProfile, fact: Fact) -> MasterProfile:
    updated = _new_version(profile, "upsert", fact.id)
    existing = updated.fact(fact.id)
    if existing:
        fact.created_at = existing.created_at
        updated.facts = [fact if f.id == fact.id else f for f in updated.facts]
    else:
        updated.facts.append(fact)
    fact.updated_at = now_iso()
    return updated


def validate_profile(profile: MasterProfile) -> MasterProfile:
    """« Valider le profil vX » : l'utilisateur certifie la version courante."""
    blocking = [r for r in profile.review_queue if r.severity == "conflict"]
    if blocking:
        raise ValueError(
            "Validation impossible : conflits à résoudre d'abord → " + "; ".join(f"{r.fact_id} ({r.reason})" for r in blocking)
        )
    validated = profile.model_copy(deep=True)
    validated.validated = True
    validated.validated_at = now_iso()
    validated.history.append(ProfileEvent(action="validate", detail=f"Profil v{profile.version} validé"))
    return validated


def missing_data(profile: MasterProfile) -> list[str]:
    items = list(profile.unknowns)
    for r in profile.review_queue:
        items.append(f"{r.fact_id} — {r.reason}")
    for f in profile.facts:
        if f.needs_confirmation and f.usable:
            items.append(f"À confirmer : {f.text} ({f.id})")
    return items


# ── Tables pour les prompts ──────────────────────────────────────────────────

ALWAYS_IN_CONTEXT = ("identity", "target", "education", "language")


def facts_table(profile: MasterProfile, kinds: Iterable[str] | None = None, include_contact: bool = False,
                only: Iterable[str] | None = None) -> str:
    """Table des faits pour un prompt. `only` : contexte minimal — ces faits, leurs expériences parentes et les faits
    d'identité, de cible, de formation et de langue (moins de jetons, et l'IA ne voit que ce qui sert à l'offre)."""
    rows = []
    kind_filter = set(kinds) if kinds else None
    keep: set[str] | None = None
    if only is not None:
        keep = set(only)
        keep |= {f.parent for f in profile.usable_facts() if f.id in keep and f.parent}
    for f in profile.usable_facts():
        if f.kind == "contact" and not include_contact:
            continue
        if kind_filter and f.kind not in kind_filter:
            continue
        if keep is not None and f.id not in keep and f.kind not in ALWAYS_IN_CONTEXT:
            continue
        parent = f" (↳ {f.parent})" if f.parent else ""
        rows.append(f"{f.id} | {f.kind}{parent} | {f.status} | {f.text}")
    return "\n".join(rows)


def experiences_table(profile: MasterProfile) -> str:
    rows = []
    for e in profile.experiences():
        d = e.data
        rows.append(f"{e.id} | {d.get('title', '')} | {d.get('company', '')} | {d.get('period_label', '')}")
    return "\n".join(rows)


def language_level(fact: Fact) -> int:
    from .textnorm import norm

    level = norm(str(fact.data.get("level", "")))
    return LEVELS.get(level, 0)


# ── Export / import ──────────────────────────────────────────────────────────

def export_json(profile: MasterProfile) -> str:
    return profile.model_dump_json(by_alias=True, indent=2)


def export_csv(profile: MasterProfile) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "kind", "status", "text", "parent", "source", "provenance", "confidence", "needs_confirmation", "note"])
    for f in profile.facts:
        writer.writerow([f.id, f.kind, f.status, f.text, f.parent or "", f.source, f.provenance, f.confidence, f.needs_confirmation, f.note])
    return buf.getvalue()


def export_markdown(profile: MasterProfile) -> str:
    lines = [f"# Master Profile — {profile.value('id.name', profile.candidate_id)}", "",
             f"Version : v{profile.version} · {'VALIDÉ le ' + profile.validated_at if profile.validated and profile.validated_at else 'NON VALIDÉ'}", ""]
    by_kind: dict[str, list[Fact]] = {}
    for f in profile.facts:
        by_kind.setdefault(f.kind, []).append(f)
    for kind, facts in by_kind.items():
        lines.append(f"## {kind}")
        for f in facts:
            flag = " ⚠️ à confirmer" if f.needs_confirmation else ""
            lines.append(f"- `{f.id}` **{f.status}** — {f.text}{flag}  \n  _source : {f.source}_")
        lines.append("")
    if profile.review_queue:
        lines.append("## File REVIEW")
        lines.extend(f"- `{r.fact_id}` ({r.severity}) — {r.reason}" for r in profile.review_queue)
        lines.append("")
    if profile.unknowns:
        lines.append("## Données manquantes (UNKNOWN)")
        lines.extend(f"- {u}" for u in profile.unknowns)
    return "\n".join(lines) + "\n"


def import_json(raw: str | bytes | dict[str, Any]) -> MasterProfile:
    data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    profile = MasterProfile.model_validate(data)
    ids = [f.id for f in profile.facts]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Identifiants de faits en double : {sorted(duplicates)}")
    return profile


def add_review(profile: MasterProfile, fact_id: str, reason: str, severity: str = "warning") -> None:
    profile.review_queue.append(ReviewItem(fact_id=fact_id, reason=reason, severity=severity))
