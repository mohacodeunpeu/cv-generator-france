"""Validateur claim → evidence : cas partagés avec le moteur JS (tests/golden/validator_cases.json)."""

from __future__ import annotations

import pytest

from pai.claims import ClaimValidator, proper_noun_candidates
from pai.schemas import Line


def test_golden_cases(profile, golden):
    v = ClaimValidator(profile, golden["offer"], offer_terms=golden["offer_terms"])
    for case in golden["cases"]:
        r = v.validate_line(Line(id=case["id"], section="experience", kind=case["kind"], text=case["text"],
                                 fact_ids=case["fact_ids"], offer_quote=case.get("offer_quote", "")))
        assert r.ok is case["ok"], f"{case['id']} → {r.ok} ({'; '.join(r.reasons)})"


def test_forbidden_is_flagged(profile):
    r = ClaimValidator(profile).validate_line(Line(id="x", section="summary", kind="claim", text="Diplômé d'un MBA", fact_ids=["edu.bachelor"]))
    assert r.forbidden and not r.ok


@pytest.mark.parametrize("text", ["Management d'une équipe de commerciaux", "Encadrement de 3 stagiaires", "Head of Sales pour la zone"])
def test_leadership_inflation(profile, text):
    r = ClaimValidator(profile).validate_line(Line(id="x", section="experience", kind="claim", text=text, fact_ids=["exp.alpha.t1"]))
    assert not r.ok


def test_report_counts(profile):
    lines = [Line(id="a", section="experience", kind="claim", text="Négociation directe avec décideurs", fact_ids=["exp.alpha.t2"]),
             Line(id="b", section="experience", kind="claim", text="50+ leads", fact_ids=["exp.alpha.r2"])]
    rep = ClaimValidator(profile).validate_lines(lines)
    assert rep.total == 2 and rep.traced == 1 and rep.factuality == 50.0 and rep.rejected_ids == ["b"] and not rep.perfect


def test_proper_nouns():
    assert "L'Oréal" in proper_noun_candidates("Prospection B2B chez L'Oréal")
    assert proper_noun_candidates("Prospection de PME") == ["PME"]
