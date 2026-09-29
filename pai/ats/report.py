"""Rapports ATS : ce que l'interface affiche (pourcentages d'abord, détails sur demande).

  match_report(...)  mode B — CV + offre (ou profil + offre avant génération du CV)
  cv_report(...)     mode A — CV seul (texte ou PDF), sans offre

Chaque élément textuel est typé : « fait » (constaté), « interpretation » (lecture de PAI), « suggestion » (action).
"""

from __future__ import annotations

from typing import Any

from ..rules import RuleSet, load_rules
from ..schemas import Analysis, CvDocument, MasterProfile, Match, ValidationReport
from . import requirements as rq
from . import scoring as sc
from .parser import parse_cv_text
from .variants import select_variant

ENGINE_VERSION = "ats-1"


def _item(kind: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"kind": kind, "text": text} | extra


def _requirements_view(reqs: list[rq.Requirement]) -> dict[str, list[dict[str, Any]]]:
    view: dict[str, list[dict[str, Any]]] = {"proven": [], "plausible": [], "unproven": [], "context": []}
    order = {"MUST": 0, "IMPORTANT": 1, "NICE_TO_HAVE": 2, "CONTEXT": 3}
    for r in sorted(reqs, key=lambda r: order[r.klass]):
        key = "context" if r.klass == "CONTEXT" else {rq.PROVEN: "proven", rq.PLAUSIBLE: "plausible", rq.UNPROVEN: "unproven"}[r.proof.status]
        view[key].append(r.as_dict())
    return view


def _strengths_and_gaps(reqs: list[rq.Requirement], keywords: list[dict[str, Any]], dims: list[dict[str, Any]]):
    strengths, improve = [], []
    for r in reqs:
        if r.klass == "CONTEXT":
            continue
        label = rq.LABELS[r.klass].lower()
        if r.proof.status == rq.PROVEN and r.klass in ("MUST", "IMPORTANT") and r.kind in ("keyword", "language", "degree", "experience"):
            strengths.append(_item("fait", f"{r.text} : prouvé ({label})", fact_ids=r.proof.fact_ids[:3]))
        elif r.proof.status == rq.UNPROVEN and r.klass == "MUST":
            improve.append(_item("fait", f"{r.text} : exigence obligatoire non prouvée", note=r.proof.note))
        elif r.proof.status == rq.PLAUSIBLE and r.klass == "MUST":
            improve.append(_item("interpretation", f"{r.text} : correspondance possible seulement ({r.proof.via})", note=r.proof.note))
    for k in keywords:
        if k["status"] == rq.PROVEN and not k["in_cv"] and k["priority"] != "NICE":
            improve.append(_item("suggestion", f"Placer « {k['term']} » dans le CV : c'est prouvé ({', '.join(k['fact_ids'][:2])})."))
    for d in dims:
        if d["available"] and d["value"] is not None and d["value"] < 60 and d["id"] in ("parsing", "structure"):
            bad = [c for c in d["details"] if c["status"] != "OK"][:2]
            for c in bad:
                improve.append(_item("suggestion", f"{d['label']} — {c['label']} : {c['detail']}"))
    return strengths[:8], improve[:10]


def match_report(profile: MasterProfile, analysis: Analysis, match: Match, offer_text: str = "", *,
                 cv: CvDocument | None = None, validation: ValidationReport | None = None,
                 scan: dict[str, Any] | None = None, cv_text: str | None = None,
                 rules: RuleSet | None = None, embedder: Any = None) -> dict[str, Any]:
    """Mode B. `cv` (CV ciblé) et `scan` (PDF relu) sont optionnels : sans eux, les dimensions du document
    ne sont pas mesurées et le score est marqué provisoire."""
    rules = rules or load_rules()
    reqs = rq.prove_all(rq.extract(analysis, offer_text), profile, analysis, rules, embedder=embedder)
    if cv is not None and cv_text is None:
        from ..cv_architect import cv_plain_text

        cv_text = cv_plain_text(cv)
    keywords = sc.keyword_entries(analysis, reqs, cv_text, rules)
    dims = []
    v, d, s = sc.matching_dim(reqs)
    dims.append(sc.dimension("match", "matching", v, d, s))
    v, d, s = sc.keywords_dim(keywords, has_cv=cv_text is not None)
    dims.append(sc.dimension("match", "keywords", v, d, s, measured=cv_text is not None))
    v, d, s = sc.experience_dim(match, reqs)
    dims.append(sc.dimension("match", "experience", v, d, s))
    if scan is not None:
        dims.append(sc.dimension("match", "parsing", scan["score"], [sc.crit(c["label"], c["status"], c["detail"]) for c in scan["checks"]],
                                 f"{sum(c['status'] == 'OK' for c in scan['checks'])}/{len(scan['checks'])} contrôles OK sur le PDF réel"))
    else:
        dims.append(sc.dimension("match", "parsing", None, [], "mesuré sur le PDF généré"))
    v, d, s = sc.factuality_dim(validation)
    dims.append(sc.dimension("match", "factuality", v, d, s))
    if cv is not None:
        v, d = sc.structure_from_doc(cv)
        dims.append(sc.dimension("match", "structure", v, d, f"{sum(c['status'] == 'OK' for c in d)}/{len(d)} critères"))
    elif cv_text:
        v, d = sc.structure_from_parsed(parse_cv_text(cv_text))
        dims.append(sc.dimension("match", "structure", v, d, f"{sum(c['status'] == 'OK' for c in d)}/{len(d)} critères"))
    else:
        dims.append(sc.dimension("match", "structure", None, [], "mesurée sur le CV généré"))
    v, d, s = sc.education_dim(match, reqs, analysis)
    dims.append(sc.dimension("match", "education", v, d, s))
    v, d, s = sc.languages_dim(match, reqs)
    dims.append(sc.dimension("match", "languages", v, d, s))
    main = ["parsing", "structure", "matching", "keywords", "experience", "factuality"]
    dims.sort(key=lambda x: main.index(x["id"]) if x["id"] in main else 99)
    strengths, improve = _strengths_and_gaps(reqs, keywords, dims)
    return {
        "mode": "cv_offer" if cv is not None or cv_text else "profile_offer",
        "engine": {"version": ENGINE_VERSION, "rules": rules.version},
        "offer": {"title": analysis.job_title, "company": analysis.company, "location": analysis.location,
                  "contract": analysis.contract, "remote": analysis.remote},
        "score": sc.global_score(dims) | {"label": "Score PAI"},
        "dimensions": dims,
        "main": main,
        "strengths": strengths,
        "improvements": improve,
        "requirements": _requirements_view(reqs),
        "keywords": keywords,
        "variant": select_variant(analysis.job_title, analysis.sector_id),
    }


def cv_report(text: str | None = None, pdf: bytes | None = None, *, rules: RuleSet | None = None) -> dict[str, Any]:
    """Mode A : un CV seul (texte collé ou PDF). Aucune liste de mots-clés inventée : un TOP n'apparaît que si le
    corpus métier a assez d'offres pour la famille détectée."""
    rules = rules or load_rules()
    scan = None
    if pdf is not None:
        from .scanner import scan_pdf

        scan = scan_pdf(pdf)
        from ..pdf_qa import extract_text

        text = extract_text(pdf)
    parsed = parse_cv_text(text or "")
    dims = []
    if scan:
        dims.append(sc.dimension("cv", "parsing", scan["score"], [sc.crit(c["label"], c["status"], c["detail"]) for c in scan["checks"]],
                                 f"{sum(c['status'] == 'OK' for c in scan['checks'])}/{len(scan['checks'])} contrôles OK"))
    else:
        # Texte collé : seuls les contrôles de lecture sont possibles (pas de mise en page à inspecter).
        checks = [sc.crit("Coordonnées", "OK" if parsed.email and parsed.phone else "ERROR" if not parsed.email else "WARNING",
                          ", ".join(x for x, ok in (("e-mail", parsed.email), ("téléphone", parsed.phone)) if ok) or "absentes"),
                  sc.crit("Sections reconnues", "OK" if len(parsed.order) >= 3 else "WARNING", ", ".join(parsed.order) or "aucune"),
                  sc.crit("Dates lisibles", "OK" if parsed.dates else "WARNING", f"{len(parsed.dates)} date(s)")]
        v = 100 - sum(sc_pen(c["status"]) for c in checks)
        dims.append(sc.dimension("cv", "parsing", v, checks, "texte seul : la mise en page n'est pas contrôlée", measured=False))
    v, d = sc.structure_from_parsed(parsed)
    dims.append(sc.dimension("cv", "structure", v, d, f"{sum(c['status'] == 'OK' for c in d)}/{len(d)} critères"))
    v, d, s = sc.content_dim(parsed, rules)
    dims.append(sc.dimension("cv", "content", v, d, s))
    v, d, s = sc.readability_dim(parsed, scan["pages"] if scan else None)
    dims.append(sc.dimension("cv", "readability", v, d, s))
    v, d, s = sc.coherence_dim(parsed)
    dims.append(sc.dimension("cv", "factuality", v, d, s))
    title = next((ln for ln in parsed.lines[:6] if ln != parsed.name and 2 <= len(ln.split()) <= 8 and "@" not in ln), "")
    variant = select_variant(title)
    try:
        from .corpus import from_db

        fam = from_db()["families"].get(variant["id"])
    except Exception:  # noqa: BLE001 — sans base (outil en ligne de commande) : pas de corpus
        fam = None
    keywords = {"family": variant, "offers": fam["offers"] if fam else 0,
                "top": fam["skills"] if fam and fam["top"] else [],
                "note": fam["note"] if fam else "Aucune offre analysée pour cette famille : pas de liste de mots-clés génériques."}
    if keywords["top"]:
        from ..textnorm import contains_term, norm

        t = norm(text or "")
        for k in keywords["top"]:
            k["in_cv"] = contains_term(t, k["term"])
    strengths = [_item("fait", f"{c['label']} : {c['detail']}") for d in dims for c in d["details"] if c["status"] == "OK"][:6]
    improve = [_item("suggestion", f"{d['label']} — {c['label']} : {c['detail']}") for d in dims for c in d["details"]
               if c["status"] != "OK"][:10]
    return {"mode": "cv_only", "engine": {"version": ENGINE_VERSION, "rules": rules.version},
            "score": sc.global_score(dims) | {"label": "Score PAI (CV seul)"}, "dimensions": dims,
            "main": [d["id"] for d in dims], "strengths": strengths, "improvements": improve,
            "parsed": parsed.as_dict(), "scan": scan, "keywords": keywords}


def sc_pen(status: str) -> int:
    return {"OK": 0, "WARNING": 10, "ERROR": 30}[status]
