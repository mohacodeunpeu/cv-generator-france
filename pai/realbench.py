"""Benchmark sur offres RÉELLES — complément du benchmark de régression (13 offres fictives, pai/benchmark.py).

Les offres réelles ne vont jamais dans Git : dossier `DATA_DIR/benchmark_real/` (ou `--dir`), une offre par fichier
(.txt, .md, .pdf, .html, .docx), et/ou `liens.txt` (une URL par ligne, lue par le serveur PAI lui-même). Facultatif :
`cv_original.pdf` (ou .docx, .txt) — le CV tel qu'il partirait sans PAI — pour comparer CV original et CV ciblé.

Mesures par offre, puis moyennes. Elles disent la qualité du système, jamais une chance d'embauche :
- factualité du CV et de la lettre (validateur de faits) ; affirmations non prouvées publiées (doit rester 0) et
  lignes retirées faute de preuve ;
- couverture des mots-clés de l'offre : brute (présents dans le CV), prouvée (présents ET prouvés par le profil),
  sémantique (correspondance possible : affichée à part, jamais comptée comme preuve) ;
- exigences obligatoires prouvées ;
- lisibilité par un ATS (scanner du PDF réel : Format & parsing) et qualité du PDF (pages, débordements) ;
- constance : deux générations de la même offre donnent le même CV et la même lettre (empreintes) ;
- temps, appels IA, réponses servies par le cache ;
- Score PAI du CV original et du CV ciblé, sur la même offre et avec la même grille.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from . import ENGINE_VERSION, paths
from .ats import requirements as rq
from .pipeline import Pipeline
from .schemas import MasterProfile, Offer
from .textnorm import stable_hash

OFFER_SUFFIXES = (".txt", ".md", ".pdf", ".html", ".htm", ".docx")
DISCLAIMER = ("Mesures de qualité du système PAI sur des offres réelles : ni le score d'un ATS réel, ni une probabilité "
              "d'embauche. La couverture sémantique (« correspondance possible ») n'est jamais une preuve.")


def default_dir() -> Path:
    return paths.DATA_DIR / "benchmark_real"


def load_offers(directory: Path) -> list[tuple[str, Offer | str]]:
    """(libellé, offre) ; une offre illisible ou un lien refusé donne (libellé, raison) : c'est un résultat."""
    from .ingest import IngestError, offer_from_file, offer_from_url

    items: list[tuple[str, Offer | str]] = []
    for f in sorted(p for p in directory.iterdir() if p.is_file()):
        if f.name.startswith(("cv_original", "_", ".")):
            continue
        if f.name == "liens.txt" or f.suffix == ".url":
            for line in f.read_text(encoding="utf-8").splitlines():
                url = line.strip()
                if not url or url.startswith("#"):
                    continue
                try:
                    items.append((url, offer_from_url(url)))
                except IngestError as exc:
                    items.append((url, f"{getattr(exc, 'code', 'unreadable')} : {getattr(exc, 'message', str(exc))}"))
            continue
        if f.suffix.lower() in OFFER_SUFFIXES:
            try:
                items.append((f.name, offer_from_file(f.name, f.read_bytes())))
            except IngestError as exc:
                items.append((f.name, f"unreadable : {exc}"))
    return items


def original_cv(directory: Path) -> tuple[str, bytes | None] | None:
    from .ats.cvimport import cv_text_from_file

    for f in sorted(directory.glob("cv_original.*")):
        text, pdf = cv_text_from_file(f.name, f.read_bytes())
        return text, pdf
    return None


def _pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 1) if d else None


def _dim(ats: dict[str, Any], dim_id: str) -> float | None:
    return next((d.get("value") for d in ats.get("dimensions", []) if d.get("id") == dim_id), None)


def measure(pack: Any, pipe: Pipeline, seconds: float) -> dict[str, Any]:
    """Les mesures d'un pack généré (aucun contenu du CV, seulement des nombres)."""
    ats = pack.ats or {}
    kws = ats.get("keywords", [])
    in_cv = [k for k in kws if k.get("in_cv")]
    proven_in_cv = [k for k in in_cv if k.get("status") == rq.PROVEN]
    plausible = [k for k in kws if k.get("status") == rq.PLAUSIBLE]
    reqs = ats.get("requirements", {})
    musts = [r for key in ("proven", "plausible", "unproven") for r in reqs.get(key, []) if r.get("class") == "MUST"]
    musts_proven = [r for r in reqs.get("proven", []) if r.get("class") == "MUST"]
    cv_v, letter_v = pack.validation.get("cv"), pack.validation.get("letter")
    calls = list(getattr(pipe.provider, "calls", []))
    qa = pack.pdf_qa if isinstance(pack.pdf_qa, dict) else {}
    return {
        "status": pack.status, "score_pai": (ats.get("score") or {}).get("value"),
        "factuality_cv": cv_v.factuality if cv_v else None, "factuality_letter": letter_v.factuality if letter_v else None,
        "unsupported_published": (cv_v.total - cv_v.traced) if cv_v else None,
        "forbidden_hits": (cv_v.forbidden_hits if cv_v else 0) + (letter_v.forbidden_hits if letter_v else 0),
        "removed_for_lack_of_proof": len(pack.cv.removed_lines) if pack.cv else 0,
        "keywords": len(kws), "keyword_coverage": _pct(len(in_cv), len(kws)),
        "verified_keyword_coverage": _pct(len(proven_in_cv), len(kws)),
        "semantic_coverage": _pct(len(plausible), len(kws)),
        "must": len(musts), "must_proven": _pct(len(musts_proven), len(musts)),
        "parsing": _dim(ats, "parsing"), "structure": _dim(ats, "structure"), "matching": _dim(ats, "matching"),
        "pdf_ok": bool(qa.get("ok")) if qa else None, "pages": qa.get("pages") if qa else None,
        "seconds": round(seconds, 2), "ai_calls": sum(1 for c in calls if not c.cached),
        "ai_cache_hits": sum(1 for c in calls if c.cached),
        "fingerprint": stable_hash([[ln.text for ln in pack.cv.lines] if pack.cv else [],
                                    [ln.text for ln in pack.letter.lines] if pack.letter else []], 16),
    }


def run(directory: Path | None = None, *, provider_factory: Any = None, repeat: int = 2,
        profile: MasterProfile | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    """Génère chaque offre `repeat` fois (constance), mesure, compare au CV original s'il existe, écrit le rapport."""
    from .analyzer import deterministic_analysis
    from .ats.report import match_report
    from .ats.scanner import scan_pdf
    from .db.repo import load_current_profile
    from .db.session import session_scope
    from .matching import compute_match
    from .providers.null import NullProvider
    from .rules import load_rules

    directory = directory or default_dir()
    if not directory.is_dir():
        raise FileNotFoundError(f"Dossier d'offres réelles introuvable : {directory} (voir docs/benchmark.md)")
    if profile is None:
        with session_scope() as s:
            profile = load_current_profile(s)
    rules = load_rules()
    make = provider_factory or (lambda: NullProvider())
    original = original_cv(directory)
    rows: list[dict[str, Any]] = []
    for label, offer in load_offers(directory):
        if isinstance(offer, str):
            rows.append({"offer": label, "error": offer})
            continue
        runs = []
        for _ in range(max(1, repeat)):
            pipe = Pipeline(profile, make(), mode="STANDARD")
            t0 = time.monotonic()
            pack = pipe.run(offer)
            runs.append(measure(pack, pipe, time.monotonic() - t0))
        row = {"offer": label, "title": pack.analysis.job_title, "company": pack.analysis.company, **runs[0],
               "consistent": len({r["fingerprint"] for r in runs}) == 1, "repeat": len(runs),
               "seconds_mean": round(statistics.mean(r["seconds"] for r in runs), 2),
               "ai_cache_hits_total": sum(r["ai_cache_hits"] for r in runs)}
        if original is not None:
            text, pdf = original
            analysis = deterministic_analysis(offer, rules)
            rep = match_report(profile, analysis, compute_match(profile, analysis, rules), offer.text, cv_text=text,
                               scan=scan_pdf(pdf) if pdf else None, rules=rules)
            row["score_original"] = (rep.get("score") or {}).get("value")
            row["keyword_coverage_original"] = _pct(sum(1 for k in rep["keywords"] if k.get("in_cv")), len(rep["keywords"]))
        rows.append(row)
    summary = summarize(rows, original is not None)
    out = output_dir or directory / "results" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "report.md").write_text(report_markdown(summary, rows), encoding="utf-8")
    return {"summary": summary, "rows": rows, "output_dir": str(out)}


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return round(statistics.mean(values), 1) if values else None


def summarize(rows: list[dict[str, Any]], with_original: bool) -> dict[str, Any]:
    ok = [r for r in rows if "error" not in r]
    summary: dict[str, Any] = {
        "engine": ENGINE_VERSION, "offers": len(rows), "measured": len(ok), "unreadable": len(rows) - len(ok),
        "factuality_cv_min": min((r["factuality_cv"] for r in ok if r.get("factuality_cv") is not None), default=None),
        "factuality_letter_min": min((r["factuality_letter"] for r in ok if r.get("factuality_letter") is not None), default=None),
        "unsupported_published_total": sum(r.get("unsupported_published") or 0 for r in ok),
        "forbidden_hits_total": sum(r.get("forbidden_hits") or 0 for r in ok),
        "consistency_rate": _pct(sum(1 for r in ok if r.get("consistent")), len(ok)),
        "ai_calls_total": sum(r.get("ai_calls") or 0 for r in ok),
        "ai_cache_hits_total": sum(r.get("ai_cache_hits_total") or 0 for r in ok),
        "disclaimer": DISCLAIMER,
    }
    for key in ("score_pai", "keyword_coverage", "verified_keyword_coverage", "semantic_coverage", "must_proven",
                "parsing", "structure", "matching", "seconds_mean"):
        summary[f"{key}_mean"] = _mean(ok, key)
    if with_original:
        summary["score_original_mean"] = _mean(ok, "score_original")
        summary["keyword_coverage_original_mean"] = _mean(ok, "keyword_coverage_original")
    return summary


def _f(x: Any, unit: str = "") -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "oui" if x else "non"
    if isinstance(x, float):
        return f"{x:.1f}".replace(".", ",").replace(",0", "") + unit
    return f"{x}{unit}"


def report_markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    s = summary
    out = ["# Benchmark sur offres réelles", "", f"> {DISCLAIMER}", "",
           f"Offres : {s['offers']} (mesurées : {s['measured']}, illisibles : {s['unreadable']}) · moteur {s['engine']}", "",
           "| Mesure | Valeur |", "|---|---|",
           f"| Factualité minimale (CV / lettre) | {_f(s['factuality_cv_min'], ' %')} / {_f(s['factuality_letter_min'], ' %')} |",
           f"| Affirmations non prouvées publiées | {s['unsupported_published_total']} |",
           f"| Termes interdits | {s['forbidden_hits_total']} |",
           f"| Score PAI moyen (CV ciblé) | {_f(s['score_pai_mean'], ' %')} |"]
    if "score_original_mean" in s:
        out.append(f"| Score PAI moyen (CV original, même grille) | {_f(s['score_original_mean'], ' %')} |")
        out.append(f"| Couverture des mots-clés (CV original) | {_f(s['keyword_coverage_original_mean'], ' %')} |")
    out += [f"| Couverture des mots-clés : brute / prouvée / sémantique | {_f(s['keyword_coverage_mean'], ' %')} / "
            f"{_f(s['verified_keyword_coverage_mean'], ' %')} / {_f(s['semantic_coverage_mean'], ' %')} |",
            f"| Exigences obligatoires prouvées | {_f(s['must_proven_mean'], ' %')} |",
            f"| Format & parsing (PDF réel relu) | {_f(s['parsing_mean'], ' %')} |",
            f"| Constance (même offre → même CV et même lettre) | {_f(s['consistency_rate'], ' %')} |",
            f"| Temps moyen par pack | {_f(s['seconds_mean_mean'], ' s')} |",
            f"| Appels IA / réponses servies par le cache | {s['ai_calls_total']} / {s['ai_cache_hits_total']} |", "",
            "| Offre | Poste | Score PAI | Original | Mots-clés brute / prouvée / sémantique | Obligatoires prouvées "
            "| Parsing | Factualité | Constance | Temps |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            out.append(f"| {r['offer']} | illisible : {r['error']} | — | — | — | — | — | — | — | — |")
            continue
        out.append(f"| {r['offer']} | {r['title']} | {_f(r['score_pai'], ' %')} | {_f(r.get('score_original'), ' %')} "
                   f"| {_f(r['keyword_coverage'], ' %')} / {_f(r['verified_keyword_coverage'], ' %')} / "
                   f"{_f(r['semantic_coverage'], ' %')} | {_f(r['must_proven'], ' %')} | {_f(r['parsing'], ' %')} "
                   f"| {_f(r['factuality_cv'], ' %')} | {_f(r['consistent'])} | {_f(r['seconds_mean'], ' s')} |")
    return "\n".join(out) + "\n"


def ai_factory(mode: str) -> Any:
    """none : voies déterministes ; configured : le fournisseur configuré (IA locale par défaut, externe si choisi)."""
    from .providers import get_provider
    from .providers.null import NullProvider

    if mode == "none":
        return lambda: NullProvider()
    return lambda: get_provider()

