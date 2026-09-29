"""Moteur ATS : classement des exigences, preuve (PROUVÉ / PLAUSIBLE / NON PROUVÉ), Score PAI en pourcentages,
lecture d'un CV, scanner PDF et relecture, variantes, corpus, changements expliqués. Sans IA, sans réseau."""

from __future__ import annotations

import pytest

from pai.analyzer import deterministic_analysis
from pai.ats import classify_requirement, cv_report, match_report, proof_status_for_texts, prove
from pai.ats import corpus, requirements as rq
from pai.ats.changes import explain
from pai.ats.lexicon import core, stem
from pai.ats.parser import parse_cv_text
from pai.ats.semantic import Embedder
from pai.ats.variants import select_variant
from pai.claims import validate_cv
from pai.cv_architect import build_cv_deterministic, cv_plain_text
from pai.ingest import benchmark_fixtures, offer_from_text
from pai.matching import compute_match
from pai.strategy import deterministic_strategy
from pai.textnorm import norm

FACTS = ["F1 : Business Developer chez Alpha Services (2025 – aujourd'hui) : prospection B2B par téléphone et LinkedIn.",
         "F2 : 25 leads qualifiés par mois grâce à LinkedIn Sales Navigator.",
         "F3 : suivi du pipeline commercial dans HubSpot.",
         "F5 : anglais courant (TOEIC 905/990).", "F6 : Bachelor Commerce."]


# ── Classement ─────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,section,expected", [
    ("Première expérience en prospection B2B indispensable", "", "MUST"),
    ("Anglais courant requis", "", "MUST"),
    ("La maîtrise de Salesforce est un plus", "", "NICE_TO_HAVE"),
    ("Connaissance du secteur industriel appréciée", "", "NICE_TO_HAVE"),
    ("Maîtrise d'un CRM (HubSpot idéalement)", "profile", "MUST"),          # le « un plus » ne vise que la parenthèse
    ("Suivre votre pipeline dans HubSpot", "", "IMPORTANT"),
    ("Qualifier les leads entrants et organiser des démonstrations", "mission", "IMPORTANT"),
    ("Télétravail 2 jours par semaine", "", "CONTEXT"),
    ("Salaire : 30 k€ annuel brut + primes", "profile", "CONTEXT"),         # « salaire » n'est pas un verbe
    ("Éditeur SaaS de 120 salariés", "", "CONTEXT"),
    ("Première expérience en recrutement ou en agence d'emploi", "profile", "IMPORTANT"),
])
def test_classify_requirement(text, section, expected):
    assert classify_requirement(text, section=section) == expected


# ── Preuve ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("requirement,expected", [
    ("Prospection B2B", "PROUVÉ"), ("HubSpot", "PROUVÉ"), ("Anglais courant", "PROUVÉ"),
    ("Prospecter", "PROUVÉ"),                         # forme proche (racine) = même notion
    ("Utilisation d'un CRM", "PLAUSIBLE"),            # déduit de HubSpot : pas une mention explicite
    ("Salesforce", "NON_PROUVÉ"), ("Immobilier", "NON_PROUVÉ"), ("Connaissance du secteur industriel", "NON_PROUVÉ"),
    ("Anglais bilingue", "PLAUSIBLE"),                # langue prouvée, niveau inférieur
    ("Espagnol", "NON_PROUVÉ"), ("France Travail", "NON_PROUVÉ"),
])
def test_proof_status(requirement, expected):
    assert proof_status_for_texts(requirement, FACTS) == expected


def test_sibling_tool_is_reported_but_never_proves():
    p = prove("Salesforce", [(f"t{i}", norm(x)) for i, x in enumerate(FACTS)])
    assert p.status == rq.UNPROVEN and p.related == ["hubspot"] and "ne pas l'écrire" in p.note


def test_semantic_similarity_is_never_proof():
    """Embeddings (modèle local simulé) : au mieux PLAUSIBLE, jamais PROUVÉ."""
    emb = Embedder(lambda texts: [[1.0, 0.0] for _ in texts], model="fake", threshold=0.5)
    p = prove("Business development international", [("t0", norm("Développement de comptes à l'export"))], embedder=emb)
    assert p.status == rq.PLAUSIBLE and p.match == "SÉMANTIQUE" and "jamais une preuve" in p.note


def test_lexicon():
    assert stem("prospecter") == stem("prospection") == stem("prospects") == "prospect"
    assert core("Maîtrise d'un CRM indispensable") == "crm"


def test_selfeval_deterministic_baseline_is_perfect_on_classification_and_matching():
    from pai.ai import selfeval

    r = selfeval.run_deterministic()
    assert r["scores"]["classification"] == 100.0 and r["scores"]["matching"] == 100.0


# ── Score PAI (CV + offre) ──────────────────────────────────────────────────────────────────────────
def _fixture(profile, oid="bd_saas_paris"):
    offer = next(o for o, meta in benchmark_fixtures() if meta["id"] == oid)
    a = deterministic_analysis(offer)
    m = compute_match(profile, a)
    return offer, a, m


def test_match_report_percentages_and_honest_requirements(profile):
    offer, a, m = _fixture(profile)
    r = match_report(profile, a, m, offer.text)
    assert r["score"]["label"] == "Score PAI" and 0 <= r["score"]["value"] <= 100
    assert r["score"]["complete"] is False and "Format & parsing" in r["score"]["missing"]   # avant CV : provisoire
    assert "ATS réel" in r["score"]["disclaimer"] and "probabilité d'embauche" in r["score"]["disclaimer"]
    ids = [d["id"] for d in r["dimensions"]]
    assert ids[:6] == ["parsing", "structure", "matching", "keywords", "experience", "factuality"]
    assert {"education", "languages"} <= set(ids)
    unproven = {x["text"] for x in r["requirements"]["unproven"]}
    assert "Pipeline" in unproven                                     # jamais transformé en preuve
    assert all(x["proof"]["status"] == "PROUVÉ" for x in r["requirements"]["proven"])
    assert all(x["class"] == "CONTEXT" for x in r["requirements"]["context"])
    for k in r["keywords"]:
        assert k["why"] and k["status"] in ("PROUVÉ", "PLAUSIBLE", "NON_PROUVÉ")


def test_match_report_with_cv_is_complete_except_pdf(profile):
    offer, a, m = _fixture(profile)
    s = deterministic_strategy(profile, a, m)
    cv = build_cv_deterministic(profile, a, m, s)
    v = validate_cv(cv, profile, offer.text, [a.job_title, a.company])
    r = match_report(profile, a, m, offer.text, cv=cv, validation=v)
    dims = {d["id"]: d for d in r["dimensions"]}
    assert dims["factuality"]["value"] == 100 and dims["structure"]["available"]
    assert r["score"]["missing"] == ["Format & parsing"]
    text = norm(cv_plain_text(cv))
    for k in r["keywords"]:
        if k["in_cv"]:
            assert k["status"] != "NON_PROUVÉ" or k["term"].lower() in text   # jamais ajouté pour gonfler
    assert r["variant"]["id"] == "BUSINESS_DEVELOPER"


def test_unproven_keyword_never_inflates_the_cv(profile):
    """Mot-clé obligatoire non prouvé : absent du CV ciblé, compté manquant, expliqué."""
    offer = offer_from_text("Commercial (H/F) — CDI — Paris\nVotre profil\n- Maîtrise de Salesforce indispensable.\n"
                            "- Prospection B2B requise.\n- Anglais courant.", title="Commercial")
    a = deterministic_analysis(offer)
    m = compute_match(profile, a)
    s = deterministic_strategy(profile, a, m)
    cv = build_cv_deterministic(profile, a, m, s)
    r = match_report(profile, a, m, offer.text, cv=cv)
    sf = next(k for k in r["keywords"] if k["term"].lower() == "salesforce")
    assert sf["status"] == "NON_PROUVÉ" and not sf["in_cv"] and "gonflerait" in sf["why"]
    assert "salesforce" not in norm(cv_plain_text(cv))


# ── CV seul, lecture, scanner PDF ───────────────────────────────────────────────────────────────────
CV_TEXT = """Camille Test
Business Developer
camille.test@example.org · 06 00 00 00 00 · Paris

PROFIL
Business Developer orienté prospection B2B.

EXPÉRIENCE PROFESSIONNELLE
Business Developer — Alpha Services
Janv. 2025 – présent
- Prospecté 40 comptes PME par téléphone et LinkedIn
- Qualifié 25 leads par mois
Sales Advisor — Maison Lumen (2024)
- Vente conseil en environnement premium, +12 % vs objectif

FORMATION
Bachelor Commerce (2023)

COMPÉTENCES
Prospection B2B, Négociation, HubSpot, LinkedIn Sales Navigator, Excel

LANGUES
Français natif, Anglais courant
"""


def test_parse_cv_text():
    p = parse_cv_text(CV_TEXT)
    assert p.email == "camille.test@example.org" and p.phone.startswith("06") and p.city == "Paris"
    assert p.order == ["summary", "experience", "education", "skills", "languages"]
    assert [(e.title, e.company, e.start, e.end) for e in p.experiences] == [
        ("Business Developer", "Alpha Services", "2025-01", "present"), ("Sales Advisor", "Maison Lumen", "2024", "")]
    assert len(p.experiences[0].bullets) == 2 and "HubSpot" in p.skills


def test_cv_only_report_without_invented_keywords():
    r = cv_report(CV_TEXT)
    assert r["mode"] == "cv_only" and 0 <= r["score"]["value"] <= 100
    assert [d["id"] for d in r["dimensions"]] == ["parsing", "structure", "content", "readability", "factuality"]
    assert r["dimensions"][0]["measured"] is False                  # texte seul : mise en page non contrôlée
    assert r["keywords"]["top"] == [] and "Aucune offre" in r["keywords"]["note"]   # pas de faux TOP 40


def test_coherence_flags_impossible_dates_and_superlatives():
    bad = CV_TEXT.replace("Janv. 2025 – présent", "2031 – 2032").replace("Qualifié 25", "Meilleur vendeur, expert : 25")
    r = cv_report(bad)
    fact = next(d for d in r["dimensions"] if d["id"] == "factuality")
    assert fact["value"] < 80 and any(c["status"] == "ERROR" for c in fact["details"])


def test_scanner_and_roundtrip_on_real_pdf(profile, tmp_path):
    from pai.ats.scanner import roundtrip, scan_pdf
    from pai.render import render_cv_pdf

    offer, a, m = _fixture(profile)
    s = deterministic_strategy(profile, a, m)
    cv = build_cv_deterministic(profile, a, m, s)
    pdf = render_cv_pdf(cv)
    report = scan_pdf(pdf, source_lines=[ln.text for ln in cv.lines], allowed=[cv.name, *cv.contact, *cv.section_titles.values()])
    by_id = {c["id"]: c for c in report["checks"]}
    assert by_id["text"]["status"] == "OK" and by_id["encoding"]["status"] == "OK"
    assert by_id["lost"]["status"] == "OK", report["roundtrip"]["lost"]
    assert by_id["added"]["status"] != "ERROR"
    assert by_id["contact"]["status"] in ("OK", "WARNING") and report["score"] >= 60
    rt = roundtrip(["Ligne présente", "Ligne disparue du PDF"], "Ligne présente\nundefined")
    assert rt["lost"] == ["Ligne disparue du PDF"] and rt["placeholders"] == ["undefined"]


# ── Variantes, corpus, changements ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("title,sector,expected", [
    ("Business Developer Junior", "", "BUSINESS_DEVELOPER"), ("Chargé d'affaires BTP", "", "CHARGE_AFFAIRES"),
    ("Chargée de recrutement", "", "RECRUTEMENT"), ("Community Manager", "", "DIGITAL"),
    ("Conseiller de vente", "", "COMMERCIAL"), ("Assistant", "recrutement_rh", "RECRUTEMENT"), ("Assistant", "", "MASTER"),
])
def test_select_variant(title, sector, expected):
    assert select_variant(title, sector)["id"] == expected


def test_corpus_publishes_top_only_with_enough_volume():
    one = {"job_title": "Business Developer", "company": "A", "keywords": [{"term": "prospection"}, {"term": "CRM"}],
           "tools": ["hubspot"], "missions": ["Prospecter"], "sector_id": "business_development"}
    few = corpus.build([one | {"company": f"C{i}"} for i in range(3)])
    fam = few["families"]["BUSINESS_DEVELOPER"]
    assert fam["offers"] == 3 and fam["top"] == 0 and fam["skills"] == [] and "au moins 10" in fam["note"]
    many = corpus.build([one | {"company": f"C{i}"} for i in range(12)] + [one | {"company": "C0"}])  # doublon ignoré
    fam = many["families"]["BUSINESS_DEVELOPER"]
    assert fam["offers"] == 12 and fam["top"] == 20 and fam["skills"][0]["share"] == 100


def test_changes_explain_before_after_reason_proof(profile):
    offer, a, m = _fixture(profile)
    s = deterministic_strategy(profile, a, m)
    cv = build_cv_deterministic(profile, a, m, s)
    out = explain(cv, profile)
    assert out["changes"], "le titre au moins change"
    for c in out["changes"]:
        assert c["after"] and c["reason"]
        assert c["proof"] or c["section"] == "Titre"
