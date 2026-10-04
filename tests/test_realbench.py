"""Benchmark sur offres réelles (pai/realbench.py) : offres fournies comme fichiers et liens, CV original comparé au
CV ciblé, constance des générations, rapport sans contenu personnel. Offres de test FICTIVES, sans réseau."""

from __future__ import annotations

import json

from pai.providers.null import NullProvider
from pai.realbench import DISCLAIMER, run
from tests.conftest import TEST_OFFER
from tests.test_ats import CV_TEXT
from tests.test_public_api import HTML_OFFER


def test_real_job_benchmark_measures_quality_never_hiring_odds(profile, tmp_path):
    offers = tmp_path / "offres"
    offers.mkdir()
    (offers / "bd_saas.txt").write_text(TEST_OFFER, encoding="utf-8")
    (offers / "bd_saas_page.html").write_text(HTML_OFFER, encoding="utf-8")
    (offers / "liens.txt").write_text("# un lien que le serveur refuse (adresse interne)\nhttp://127.0.0.1/offre\n", encoding="utf-8")
    (offers / "cv_original.txt").write_text(CV_TEXT, encoding="utf-8")
    result = run(offers, provider_factory=lambda: NullProvider(), repeat=2, profile=profile, output_dir=tmp_path / "out")
    s = result["summary"]
    assert (s["offers"], s["measured"], s["unreadable"]) == (3, 2, 1)
    assert s["factuality_cv_min"] == 100.0 and s["factuality_letter_min"] == 100.0
    assert s["unsupported_published_total"] == 0 and s["forbidden_hits_total"] == 0
    assert s["consistency_rate"] == 100.0                      # même offre → même CV, même lettre
    assert s["ai_calls_total"] == 0                            # sans IA : aucun appel
    assert s["score_original_mean"] is not None and s["score_pai_mean"] is not None
    rows = {r["offer"]: r for r in result["rows"]}
    refused = rows["http://127.0.0.1/offre"]
    assert "error" in refused and refused["error"].startswith("blocked_address")
    bd = rows["bd_saas.txt"]
    assert bd["verified_keyword_coverage"] <= bd["keyword_coverage"]       # prouvé ⊂ présent
    assert bd["parsing"] is not None and bd["pdf_ok"] is True and bd["pages"] == 1
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert DISCLAIMER in report and "probabilité d'embauche" in report
    dumped = json.dumps(result["rows"], ensure_ascii=False)
    assert "camille.test@example.org" not in dumped and "06 00 00 00 00" not in dumped   # aucun contenu du CV
