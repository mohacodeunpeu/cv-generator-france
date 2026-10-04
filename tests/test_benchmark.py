"""Benchmark ancien générateur vs PAI : plomberie, équité de l'instrument, documents PAI Studio (profil fictif)."""

from __future__ import annotations

import json

from pai.benchmark import _neutralize, free_text_factuality, keyword_scores, public_rows, run_benchmark, studio_payload
from pai.ingest import offer_from_text
from pai.rules import load_rules
from pai.textnorm import norm
from tests.conftest import TEST_OFFER


def test_instrument_neutralizes_layout_but_not_claims(profile):
    offer = offer_from_text(TEST_OFFER, company="Acme SaaS")
    text = ("Acme SaaS — Service recrutement Paris, le 27 septembre 2026\nMadame, Monsieur,\n"
            "Vous cherchez à « Suivre votre pipeline dans HubSpot ». Je suis titulaire d'un MBA.\n"
            "Anglais courant, 47 ans d'expérience commerciale.")
    result = free_text_factuality(text, profile, offer, ["CRM"], load_rules())
    reasons = " ".join(r for item in result["rejected"] for r in item["reasons"])
    assert result["forbidden"] == ["mba"] and result["score"] == 0.0  # un terme interdit met le document à 0
    assert "27" not in reasons and "2026" not in reasons and "HubSpot" not in reasons  # date et citation de l'offre neutralisées
    assert "Nombre sans preuve : 47" in reasons  # un chiffre inventé reste détecté
    assert "K€" in _neutralize("360 KEUR/mois", norm(TEST_OFFER))


def test_keyword_scores_flag_stuffing():
    rules = load_rules()
    keywords = [("CRM", "REQUIRED", True), ("SAP", "IMPORTANT", False), ("anglais", "REQUIRED", True)]
    raw, honest, stuffed = keyword_scores("Suivi CRM quotidien. Maîtrise de SAP.", keywords, rules)
    assert honest == 50.0 and stuffed == ["SAP"] and raw == 62.5


def test_benchmark_two_offers_with_legacy(profile, tmp_path):
    result = run_benchmark(include_legacy=True, output_dir=tmp_path, profile=profile, only=["bd_saas_paris", "vie_dubai_en"])
    summary = result["summary"]
    assert summary["n_offers"] == 2 and summary["offers_synthetic"] and summary["sector_accuracy"] == 100.0
    assert summary["pai"]["factuality"]["mean"] == 100.0 and summary["pai"]["forbidden_docs"] == 0
    assert summary["pai"]["unsupported_lines"]["mean"] == 0.0 and summary["pai"]["letter_factuality"]["mean"] == 100.0
    assert summary["legacy"]["forbidden_docs"] == 2  # l'ancien générateur écrit « MBA » (interdit, A1)
    assert "factuality" in summary["conclusion"]["pai_better_on"] and summary["conclusion"]["text"]
    for name in ("summary.json", "rows.json", "report.md", "studio.json"):
        assert (tmp_path / name).exists()
    published = json.dumps(public_rows(result["rows"]), ensure_ascii=False)
    assert "arena_text" not in published and "rejected_examples" not in published
    studio = studio_payload(summary, result["rows"])
    assert studio["bench/summary"]["new_avg"] == summary["pai"]["total"]["mean"] and len(studio["bench/summary"]["rows"]) == 2
    pairs = [v for k, v in studio.items() if k.startswith("bench_pairs/")]
    assert len(pairs) == 2 and all("@" not in p["pai_text"] + p["legacy_text"] for p in pairs)  # pas de coordonnées
