"""Moteur : bootstrap, analyse, matching, pipeline (dégradé et IA enregistrée), rendu, pack, fournisseurs."""

from __future__ import annotations

import io
import json
import zipfile

import httpx
import pytest
import yaml

from pai import paths
from pai.analyzer import clean_title, deterministic_analysis, detect_contract, detect_degree
from pai.ingest import IngestError, benchmark_fixtures, offer_from_text
from pai.matching import compute_match
from pai.pack import export_zip
from pai.pdf_qa import check_pdf, extract_text
from pai.pipeline import Pipeline
from pai.profile import export_csv, export_markdown, import_json, set_fact_status, validate_profile
from pai.providers import CachedProvider, NullProvider, get_provider
from pai.providers.base import BudgetExceeded, ProviderError, extract_json
from pai.providers.openai_compat import local_provider, openai_provider
from pai.textnorm import extract_numbers, norm
from tests.conftest import TEST_OFFER
from tests.fake_provider import FakeProvider


# ── Texte ────────────────────────────────────────────────────────────────────
def test_norm_and_numbers():
    assert norm("Île-de-France — Négociation") == "ile-de-france - negociation"
    assert sorted(extract_numbers("+35 % en 6 mois, 1 200 clients, 915/990")) == sorted(["35", "6", "1200", "915", "990"])


# ── Bootstrap du profil réel (sans afficher de donnée personnelle) ──────────────
def test_bootstrap_rules():
    from pai.bootstrap import build_master_profile

    p = build_master_profile()
    assert p.fact("edu.mba").status == "FORBIDDEN"
    assert "mba" in [t.lower() for t in p.forbidden_terms()]
    assert not any("MBA" in f.text for f in p.usable_facts())
    assert p.fact("edu.legacy_bachelor").status == "UNVERIFIED"
    assert any(r.severity == "conflict" for r in p.review_queue)
    assert all(f.needs_confirmation for f in p.by_kind("result") if extract_numbers(f.text))
    assert p.fact("edu.bachelor_rem").status == "CONFIRMED" and p.fact("cert.toeic").text == "TOEIC 915/990"
    with pytest.raises(ValueError):
        validate_profile(p)  # conflit non résolu


def test_confirmations_have_no_contact_data():
    raw = (paths.PROFILES_DIR / "confirmations.yaml").read_text(encoding="utf-8")
    assert "@" not in raw and "+33" not in raw


# ── Analyse d'offre ─────────────────────────────────────────────────────────
def test_benchmark_sectors_all_correct():
    fixtures = benchmark_fixtures()
    assert len(fixtures) >= 12
    for offer, raw in fixtures:
        assert offer.synthetic is True
        assert deterministic_analysis(offer).sector_id == raw["expected_sector"], raw["id"]


def test_contract_and_degree_detection():
    assert detect_contract(norm("stage, alternance ou cdi"), head="Business Developer — CDI — Paris") == "CDI"
    assert detect_contract(norm("talentis interim recrute"), head="Chargé de recrutement — CDD 12 mois") == "CDD"
    assert detect_degree(norm("Bac+3 minimum (école de commerce)")) == "Bac+3"
    assert detect_degree(norm("Formation Bac+3 à Bac+5")) == "Bac+3"
    assert clean_title("Business Developer Junior (H/F) — CDI — Paris 9e") == "Business Developer Junior"


def test_hard_requirement_detected_as_missing(profile):
    offer, _ = next((o, r) for o, r in benchmark_fixtures() if r["id"] == "commercial_terrain_lyon")
    m = compute_match(profile, deterministic_analysis(offer))
    assert "permis b" in [x["requirement"] for x in m.missing if x["priority"] == "MUST"]


def test_ingest_rejects_short_text():
    with pytest.raises(IngestError):
        offer_from_text("trop court")


# ── Pipeline ────────────────────────────────────────────────────────────────
def test_degraded_pipeline_is_fully_traced(profile):
    offer = offer_from_text(TEST_OFFER, title="Business Developer Junior", company="Acme SaaS")
    pipe = Pipeline(profile, NullProvider())
    pack = pipe.run(offer, questions="Quelle est votre disponibilité ?\nQuelles sont vos prétentions salariales ?")
    assert pack.validation["cv"].factuality == 100.0 and pack.validation["letter"].factuality == 100.0
    assert pack.status == "DRAFT"  # profil non validé
    assert pack.pdf_qa["ok"] and pack.pdf_qa["pages"] == 1
    salary = next(a for a in pack.answers if "salari" in a.question)
    assert salary.confidence == "BLOCKED" and not salary.answer
    text = extract_text(pipe.files["cv.pdf"])
    assert "Camille Test" in text and "BROUILLON" in text
    z = zipfile.ZipFile(io.BytesIO(export_zip(pack, pipe.files)))
    names = z.namelist()
    assert any(n.startswith("CV_") for n in names) and "pack.json" in names and "pack.md" in names
    versions = json.loads(z.read("versions.json"))
    assert {"offer_v", "profile_v", "cv_v", "letter_v", "engine_v", "prompt_v", "rules_v"} <= set(versions)


def test_ai_pipeline_removes_traps(profile):
    offer = offer_from_text(TEST_OFFER, title="Business Developer Junior", company="Acme SaaS")
    fake = FakeProvider()
    pipe = Pipeline(profile, fake)
    pack = pipe.run(offer, questions="Quelles sont vos prétentions salariales ?")
    cv_text = " ".join(ln.text for ln in pack.cv.lines)
    assert "MBA" not in cv_text and "40+" not in cv_text and "Licence de gestion" not in cv_text
    assert any("MBA" in r["text"] for r in pack.cv.removed_lines)
    assert "25+ leads qualifiés par mois." in cv_text  # faux chiffre corrigé par la réécriture
    letter_text = " ".join(ln.text for ln in pack.letter.lines)
    assert "dirigé une équipe" not in letter_text
    assert pack.validation["cv"].factuality == 100.0 and pack.validation["letter"].factuality == 100.0
    assert pack.strategy.best.photo_mode == "OFF" and "exp.inconnue" not in pack.strategy.best.experiences_up
    assert pack.answers[0].confidence == "BLOCKED"
    assert pack.cost_eur > 0 and pack.provider == "fake"
    assert pack.scores["points"]["total"] >= 0


def test_validated_profile_gives_final(profile):
    profile.validated = True
    offer = offer_from_text(TEST_OFFER, title="Business Developer Junior", company="Acme SaaS")
    pipe = Pipeline(profile, NullProvider())
    pack = pipe.run(offer)
    assert pack.status == "FINAL"
    assert "BROUILLON" not in extract_text(pipe.files["cv.pdf"])


def test_quick_mode_has_no_documents(profile):
    offer = offer_from_text(TEST_OFFER)
    pack = Pipeline(profile, NullProvider(), mode="QUICK").run(offer)
    assert pack.cv is None and pack.strategy.best.title


# ── Profil ──────────────────────────────────────────────────────────────────
def test_profile_versioning_and_exports(profile):
    v2 = set_fact_status(profile, "exp.alpha.r1", "CONFIRMED")
    assert v2.version == profile.version + 1 and not v2.validated
    v3 = validate_profile(v2)
    assert v3.validated and v3.validated_at
    again = import_json(v3.model_dump_json(by_alias=True))
    assert again.fact("exp.alpha.r1").status == "CONFIRMED"
    assert "exp.alpha.r1" in export_csv(v3) and "Master Profile" in export_markdown(v3)


# ── Fournisseurs ────────────────────────────────────────────────────────────
def test_extract_json_tolerant():
    assert extract_json('Voici : ```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Réponse {"b": [1, 2]} fin') == {"b": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("pas de json")


def test_provider_switch_and_degraded_default(monkeypatch):
    from pai.config import reset_settings_cache

    monkeypatch.setenv("PAI_AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    reset_settings_cache()
    assert isinstance(get_provider(), NullProvider)  # pas de clé → mode dégradé
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    reset_settings_cache()
    prov = get_provider()
    assert prov.available and prov.name == "claude" and prov.model_for("strategy") == "claude-opus-5-5"
    assert get_provider("local").name == "null"  # LOCAL_MODEL absent


def test_openai_compat_provider(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        assert url.endswith("/chat/completions") and json["model"] == "mon-modele"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    prov = local_provider("mon-modele")
    assert prov.available and prov.json("chat", "chat", {"candidate_name": "X", "facts_table": "", "offer_context": "", "truth_rules": ""}) == {"ok": True}
    assert not openai_provider("", "gpt").available


def test_cache_record_and_replay(tmp_path):
    fake = FakeProvider()
    rec = CachedProvider(inner=fake, cache_dir=tmp_path, mode="on")
    first = rec.json("analyze_offer", "analyze_offer", {"offer_text": "x", "job_title_hint": "", "company_hint": "", "deterministic_json": "{}"})
    offline = FakeProvider()  # même identité (fournisseur + modèle) que l'enregistrement
    replay = CachedProvider(inner=offline, cache_dir=tmp_path, mode="replay_only")
    second = replay.json("analyze_offer", "analyze_offer", {"offer_text": "x", "job_title_hint": "", "company_hint": "", "deterministic_json": "{}"})
    assert first == second and replay.calls[-1].cached
    assert fake.seen == ["analyze_offer"] and offline.seen == []  # rejeu : aucun appel réel
    with pytest.raises(ProviderError):  # entrée jamais enregistrée → échec propre, pas d'appel
        replay.json("analyze_offer", "analyze_offer", {"offer_text": "autre", "job_title_hint": "", "company_hint": "", "deterministic_json": "{}"})


def test_budget_cap_falls_back(profile):
    fake = FakeProvider(price_per_call=0.5)
    fake.budget_eur = 0.6
    offer = offer_from_text(TEST_OFFER, title="Business Developer Junior", company="Acme SaaS")
    pack = Pipeline(profile, fake).run(offer)
    assert pack.validation["cv"].factuality == 100.0  # le repli déterministe prend le relais
    assert any("IA indisponible" in e["detail"] for e in pack.log)
    with pytest.raises(BudgetExceeded):
        fake.complete("x", "y")


def test_provider_error_is_clean():
    class Broken(FakeProvider):
        def _complete(self, task, prompt_text, images=None):
            raise RuntimeError("boom")

    with pytest.raises(ProviderError):
        Broken().complete("t", "p")


# ── Règles versionnées ──────────────────────────────────────────────────────
def test_every_yaml_parses_and_prompts_render():
    from pai.rules import load_prompts, load_rules

    for p in paths.ROOT.glob("**/*.yaml"):
        if ".venv" not in p.parts:
            yaml.safe_load(p.read_text(encoding="utf-8"))
    rules = load_rules()
    assert len(rules.sectors) == 11 and len(rules.countries) >= 12 and set(rules.designs) == {"ats_classic", "hybrid_modern", "human_premium"}
    assert all(p.version >= 1 for p in load_prompts().values())


def test_pdf_quality_checks(profile):
    offer = offer_from_text(TEST_OFFER, title="Business Developer Junior", company="Acme SaaS")
    pipe = Pipeline(profile, NullProvider())
    pack = pipe.run(offer)
    qa = check_pdf(pipe.files["cv.pdf"], expect_pages=1, reading_order=["Camille Test", "Expérience professionnelle", "Formation"])
    assert qa["ok"], qa["issues"]
    assert all("Fira" in f or "PAI" in f for f in qa["fonts"]), qa["fonts"]
