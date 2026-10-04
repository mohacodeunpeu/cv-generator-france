"""Régénère les fichiers de parité Python ↔ JS (profil FICTIF « Camille Test », offres SYNTHETIC du benchmark).

    python tests/golden/make_golden.py

- analysis_parity.json : secteur, contrat, pays, langue, mots-clés REQUIRED de chaque offre ;
- cv_parity.json       : lignes (id, texte, faits) du CV déterministe de chaque offre ;
- ats_parity.json      : moteur ATS (exigences classées et prouvées, mots-clés, Score PAI et dimensions, variante,
                         changements) sur un profil aux expériences toutes datées (résultat indépendant du jour du test),
                         plus les cas de l'auto-évaluation (classement, preuve).
Le test Node (tests/js/*.test.js) recalcule tout côté JS et exige le même résultat.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pai.ai import selfeval  # noqa: E402
from pai.analyzer import deterministic_analysis  # noqa: E402
from pai.ats import classify_requirement, match_report, proof_status_for_texts  # noqa: E402
from pai.ats.changes import explain  # noqa: E402
from pai.claims import validate_cv  # noqa: E402
from pai.cv_architect import build_cv_deterministic  # noqa: E402
from pai.ingest import benchmark_fixtures  # noqa: E402
from pai.matching import compute_match  # noqa: E402
from pai.schemas import MasterProfile  # noqa: E402
from pai.strategy import deterministic_strategy  # noqa: E402

GOLDEN = ROOT / "tests" / "golden"


def main() -> None:
    profile = MasterProfile.model_validate_json((ROOT / "tests" / "fixtures" / "profile_test.json").read_text(encoding="utf-8"))
    analysis_items, cv_items = [], []
    for offer, meta in benchmark_fixtures():
        a = deterministic_analysis(offer)
        base = {"id": meta["id"], "text": offer.text, "title_hint": offer.title_hint, "company_hint": offer.company_hint}
        analysis_items.append(base | {"sector_id": a.sector_id, "contract": a.contract, "country": a.country,
                                      "language_of_offer": a.language_of_offer,
                                      "required": [k.term for k in a.keywords if k.priority == "REQUIRED"],
                                      "missions": a.missions, "explicit": a.recruiter_wants.get("explicit", []),
                                      "degree_required": a.degree_required, "experience_years_min": a.experience_years_min})
        m = compute_match(profile, a)
        s = deterministic_strategy(profile, a, m)
        cv = build_cv_deterministic(profile, a, m, s)
        cv_items.append(base | {"lines": [{"id": ln.id, "text": ln.text, "fact_ids": ln.fact_ids} for ln in cv.lines]})
    for name, items in (("analysis_parity.json", analysis_items), ("cv_parity.json", cv_items)):
        (GOLDEN / name).write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(GOLDEN / name, len(items))
    ats = ats_golden(profile)
    (GOLDEN / "ats_parity.json").write_text(json.dumps(ats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(GOLDEN / "ats_parity.json", len(ats["offers"]))


def ats_golden(profile: MasterProfile) -> dict:
    """Profil figé : l'expérience en cours reçoit une date de fin (sinon la durée dépendrait du jour du test)."""
    data = json.loads(profile.model_dump_json(by_alias=True))
    for f in data["facts"]:
        if f["kind"] == "experience" and not (f.get("data") or {}).get("end"):
            f["data"]["end"], f["data"]["current"] = "2025-12", False
    fixed = MasterProfile.model_validate(data)
    offers = []
    for offer, meta in benchmark_fixtures():
        a = deterministic_analysis(offer)
        m = compute_match(fixed, a)
        s = deterministic_strategy(fixed, a, m)
        cv = build_cv_deterministic(fixed, a, m, s)
        v = validate_cv(cv, fixed, offer.text, [a.job_title, a.company])
        r = match_report(fixed, a, m, offer.text, cv=cv, validation=v)
        reqs = {k: [{x: q[x] for x in ("text", "class", "kind")} | {x: q["proof"][x] for x in ("status", "match", "via", "note", "fact_ids", "related")}
                    for q in items] for k, items in r["requirements"].items()}
        offers.append({"id": meta["id"], "text": offer.text, "title_hint": offer.title_hint, "company_hint": offer.company_hint,
                       "requirements": reqs,
                       "keywords": [{x: k[x] for x in ("term", "status", "in_cv", "why")} for k in r["keywords"]],
                       "dimensions": [{x: d[x] for x in ("id", "value", "available", "summary")} for d in r["dimensions"]],
                       "criteria": {d["id"]: [{x: c[x] for x in ("label", "status", "detail")} for c in d["details"]] for d in r["dimensions"]},
                       "score": {x: r["score"][x] for x in ("value", "complete", "missing", "formula")},
                       "variant": r["variant"]["id"],
                       "strengths": [x["text"] for x in r["strengths"]], "improvements": [x["text"] for x in r["improvements"]],
                       "changes": [{x: c[x] for x in ("line_id", "before", "after", "reason")} for c in explain(cv, fixed)["changes"]]})
    c = selfeval.cases()
    return {"profile": data, "offers": offers,
            "classification": [{"text": x["text"], "expected": classify_requirement(x["text"])} for x in c["classification"]],
            "matching": {"facts": c["facts"], "items": [{"requirement": x["requirement"], "expected": proof_status_for_texts(x["requirement"], c["facts"])}
                                                        for x in c["matching"]]}}


if __name__ == "__main__":
    main()
