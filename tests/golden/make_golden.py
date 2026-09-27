"""Régénère les fichiers de parité Python ↔ JS (profil FICTIF « Camille Test », offres SYNTHETIC du benchmark).

    python tests/golden/make_golden.py

- analysis_parity.json : secteur, contrat, pays, langue, mots-clés REQUIRED de chaque offre ;
- cv_parity.json       : lignes (id, texte, faits) du CV déterministe de chaque offre.
Le test Node (tests/js/engine.test.js) recalcule tout côté JS et exige le même résultat.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pai.analyzer import deterministic_analysis  # noqa: E402
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
                                      "required": [k.term for k in a.keywords if k.priority == "REQUIRED"]})
        m = compute_match(profile, a)
        s = deterministic_strategy(profile, a, m)
        cv = build_cv_deterministic(profile, a, m, s)
        cv_items.append(base | {"lines": [{"id": ln.id, "text": ln.text, "fact_ids": ln.fact_ids} for ln in cv.lines]})
    for name, items in (("analysis_parity.json", analysis_items), ("cv_parity.json", cv_items)):
        (GOLDEN / name).write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(GOLDEN / name, len(items))


if __name__ == "__main__":
    main()
