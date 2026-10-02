"""Persistance : profil courant, instantanés de version, offres, générations immuables, fichiers."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..pack import export_zip, slug
from ..profile import profile_version_tag
from ..providers.base import CallRecord
from ..schemas import ApplicationPack, MasterProfile, Offer
from .models import (AnalysisRow, AnswerSet, ApplicationPackRow, Candidate, Claim, Critique, CvVersion, FactRow, Generation,
                     LetterVersion, LlmCall, OfferRow, ProfileVersion, ScoreEvent, StoredFile, StoreDocument, utcnow)

PROFILE_PATH = "pai/profile"


def load_current_profile(s: Session) -> MasterProfile:
    """Profil courant = document `pai/profile` du magasin (édité depuis l'interface), sinon data/master_profile.json."""
    doc = s.get(StoreDocument, PROFILE_PATH)
    if doc is not None:
        return MasterProfile.model_validate(doc.data)
    from ..profile import load_profile

    profile = load_profile()
    save_profile_doc(s, profile)
    return profile


def ensure_profile_doc(s: Session) -> bool:
    """Au démarrage du serveur : publie data/master_profile.json dans le magasin si l'interface n'a encore rien."""
    from ..profile import load_profile, profile_path

    if s.get(StoreDocument, PROFILE_PATH) is not None or not profile_path().exists():
        return False
    save_profile_doc(s, load_profile())
    return True


def save_profile_doc(s: Session, profile: MasterProfile) -> None:
    data = json.loads(profile.model_dump_json(by_alias=True))
    doc = s.get(StoreDocument, PROFILE_PATH)
    if doc is None:
        s.add(StoreDocument(path=PROFILE_PATH, collection="pai", data=data))
    else:
        doc.data, doc.version, doc.updated_at = data, doc.version + 1, utcnow()


def snapshot_profile(s: Session, profile: MasterProfile) -> ProfileVersion:
    """Instantané immuable de la version utilisée par une génération (faits recopiés dans `facts`)."""
    tag = profile_version_tag(profile)
    if s.get(Candidate, profile.candidate_id) is None:
        s.add(Candidate(id=profile.candidate_id))
        s.flush()
    pv = s.scalar(select(ProfileVersion).where(ProfileVersion.candidate_id == profile.candidate_id, ProfileVersion.tag == tag))
    if pv is not None:
        return pv
    pv = ProfileVersion(candidate_id=profile.candidate_id, version=profile.version, tag=tag, validated=profile.validated,
                        payload=json.loads(profile.model_dump_json(by_alias=True)))
    s.add(pv)
    s.flush()
    for f in profile.facts:
        s.add(FactRow(profile_version_id=pv.id, fact_key=f.id, kind=f.kind, text=f.text, status=f.status, source=f.source,
                      provenance=f.provenance, confidence=f.confidence, parent_key=f.parent, data=f.data))
    return pv


def upsert_offer(s: Session, offer: Offer) -> OfferRow:
    row = s.scalar(select(OfferRow).where(OfferRow.text_hash == offer.text_hash))
    if row is None:
        row = OfferRow(id=offer.id, text_hash=offer.text_hash, source_type=offer.source_type, source_url=offer.source_url,
                       title_hint=offer.title_hint, company_hint=offer.company_hint, text=offer.text, synthetic=offer.synthetic)
        s.add(row)
        s.flush()
    return row


def store_file(s: Session, name: str, content_type: str, data: bytes, generation_id: str | None = None) -> StoredFile:
    row = StoredFile(id="fil_" + secrets.token_hex(8), generation_id=generation_id, name=name, content_type=content_type, data=data)
    s.add(row)
    s.flush()
    return row


def spent_today(s: Session) -> float:
    """Coût IA cumulé depuis minuit UTC (tous appels journalisés : packs et interface)."""
    start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    return float(s.scalar(select(func.coalesce(func.sum(LlmCall.cost_eur), 0.0)).where(LlmCall.created_at >= start)) or 0.0)


def record_calls(s: Session, calls: list[CallRecord], generation_id: str | None = None) -> None:
    from ..obs import request_id_var

    rid = request_id_var.get()
    for c in calls:
        s.add(LlmCall(generation_id=generation_id, task=c.task, provider=c.provider, model=c.model, prompt_tag=c.prompt_tag[:60],
                      input_hash=c.input_hash, tokens_in=c.tokens_in, tokens_out=c.tokens_out, cost_eur=c.cost_eur,
                      latency_ms=c.latency_ms, cached=c.cached, ok=c.ok, error=c.error[:500], tier=c.tier[:12],
                      request_id=rid[:64]))


def ats_summary(ats: dict[str, Any]) -> dict[str, Any]:
    """Résumé stable du rapport ATS (API, JobAgent, manifeste du pack) : pourcentages d'abord, sans contenu du CV."""
    req = ats.get("requirements", {})
    return {
        "score": {k: ats.get("score", {}).get(k) for k in ("value", "complete", "missing", "disclaimer", "label")},
        "dimensions": [{k: d.get(k) for k in ("id", "label", "value", "available", "summary", "weight")} for d in ats.get("dimensions", [])],
        "requirements": {k: len(v) for k, v in req.items()},
        "unproven_must": [r["text"] for r in req.get("unproven", []) if r.get("class") == "MUST"][:10],
        "keywords": [{k: kw.get(k) for k in ("term", "status", "in_cv", "priority")} for kw in ats.get("keywords", [])],
        "variant": {k: ats.get("variant", {}).get(k) for k in ("id", "label", "why")},
        "passes": ats.get("passes", []),
    }


def persist_pack(s: Session, pack: ApplicationPack, files: dict[str, bytes], calls: list[CallRecord],
                 profile: MasterProfile | None = None) -> dict[str, Any]:
    """Enregistre une génération complète (immuable) avec la version exacte du profil utilisée. Renvoie les id des fichiers."""
    pv = snapshot_profile(s, profile or load_current_profile(s))
    offer = upsert_offer(s, pack.offer)
    gen = Generation(id=pack.id, offer_id=offer.id, profile_version_id=pv.id, mode=pack.mode, status=pack.status,
                     provider=pack.provider, versions=pack.versions.model_dump(), scores=json.loads(json.dumps(pack.scores, default=str)),
                     risks=pack.risks, next_action=pack.next_action, cost_eur=pack.cost_eur, log=pack.log)
    s.add(gen)
    s.flush()
    s.add(AnalysisRow(offer_id=offer.id, engine_v=pack.versions.engine_v, provider=pack.provider,
                      analysis=pack.analysis.model_dump(), match=pack.match.model_dump(), strategy=pack.strategy.model_dump()))
    record_calls(s, calls, gen.id)
    ids: dict[str, Any] = {}
    base = f"{slug(pack.analysis.company, 24)}_{slug(pack.analysis.job_title, 30)}"
    if pack.cv is not None:
        f = store_file(s, f"CV_{base}.pdf", "application/pdf", files["cv.pdf"], gen.id) if "cv.pdf" in files else None
        s.add(CvVersion(generation_id=gen.id, version=1, content=pack.cv.model_dump(), file_id=f.id if f else None))
        ids["cv"] = f.id if f else None
    if pack.letter is not None:
        f = store_file(s, f"Lettre_{base}.pdf", "application/pdf", files["lettre.pdf"], gen.id) if "lettre.pdf" in files else None
        s.add(LetterVersion(generation_id=gen.id, version=1, content=pack.letter.model_dump(), file_id=f.id if f else None))
        ids["letter"] = f.id if f else None
    for doc_type, report in pack.validation.items():
        lines = (pack.cv.lines if doc_type == "cv" and pack.cv else pack.letter.lines if pack.letter else [])
        by_id = {v.line_id: v for v in report.verdicts}
        for ln in lines:
            v = by_id.get(ln.id)
            s.add(Claim(generation_id=gen.id, doc_type=doc_type, line_id=ln.id, text=ln.text, fact_ids=ln.fact_ids,
                        ok=bool(v.ok) if v else True, reasons=v.reasons if v else []))
    if pack.critique:
        s.add(Critique(generation_id=gen.id, payload=json.loads(json.dumps(pack.critique, default=str))))
    if pack.answers:
        s.add(AnswerSet(generation_id=gen.id, answers=[a.model_dump() for a in pack.answers]))
    for e in (pack.scores.get("points") or {}).get("events", []):
        s.add(ScoreEvent(generation_id=gen.id, event=e["event"], points=e["points"], reason=e.get("reason", "")))
    zip_file = store_file(s, f"PAI_Pack_{base}.zip", "application/zip", export_zip(pack, files), gen.id)
    ids["zip"] = zip_file.id
    s.add(ApplicationPackRow(id="apk_" + pack.id, generation_id=gen.id, zip_file_id=zip_file.id,
                             manifest={"versions": pack.versions.model_dump(), "status": pack.status, "scores": gen.scores,
                                       "ats": ats_summary(pack.ats) if pack.ats else {}}))
    return ids
