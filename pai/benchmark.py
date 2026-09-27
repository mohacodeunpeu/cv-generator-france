"""Benchmark déterministe « ancien générateur (legacy/) vs PAI » sur les offres du dossier benchmark/offers/.

Même instrument pour les deux sorties, appliqué au TEXTE EXTRAIT DU PDF (ce que lit un ATS) :
- factualité en texte libre : chaque ligne est vérifiée contre TOUT le profil (mesure tolérante : les noms et
  chiffres cités par l'offre sont admis) ; un terme interdit (MBA…) met la factualité du document à 0 ;
- couverture des mots-clés REQUIRED/IMPORTANT de l'offre (brute, et « honnête » : seulement ceux que le profil prouve) ;
- lisibilité ATS (texte extractible, sections trouvées, coordonnées) ; pagination ; QA PDF (débordements, tailles, contraste).
Pondérations : rules/scoring.yaml (benchmark.deterministic_weights). Les offres sont SYNTHETIC (fictives) :
on mesure la qualité documentaire, pas un taux de réponse (A5). Aucun juge IA ici (voir l'Arène de PAI Studio).
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import ENGINE_VERSION, paths
from .analyzer import clean_title, deterministic_analysis
from .claims import ClaimValidator
from .matching import compute_match
from .pdf_qa import check_pdf, extract_text
from .pipeline import Pipeline
from .providers.null import NullProvider
from .rules import RuleSet, load_rules
from .schemas import Line, MasterProfile, Offer
from .textnorm import contains_term, norm

METRICS = ("factuality", "keyword_coverage", "ats_parse", "pages", "pdf_qa")
EXTRA = ("honest_coverage", "letter_factuality", "title_match", "forbidden_terms", "unsupported_lines")
CONTACT = re.compile(r"@|\+?\d[\d .]{8,}\d|linkedin|github\.com|https?://", re.I)
SECTIONS = {"experience": ("experience", "experiences", "parcours", "experience professionnelle"),
            "formation": ("formation", "formations", "education", "diplomes"),
            "competences": ("competences", "skills", "outils", "savoir-faire")}
LEGACY_CONTRACT = {"CDI": "cdi", "ALTERNANCE": "alternance", "STAGE": "stage"}
# Éléments de mise en page d'une lettre, neutralisés pour les DEUX systèmes (ce ne sont pas des affirmations).
_MONTHS_FR = "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
_MONTHS_EN = "january|february|march|april|may|june|july|august|september|october|november|december"
DATE = re.compile(rf"\b\d{{1,2}}(?:er)?\s+(?:{_MONTHS_FR})\s+\d{{4}}\b|\b(?:{_MONTHS_EN})\s+\d{{1,2}},?\s+\d{{4}}\b"
                  r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b", re.I)
SALUTATION = re.compile(r"^(madame|monsieur|dear|bonjour|hello|to whom)\b[^.!?]{0,60}[,:]?$", re.I)
QUOTE = re.compile(r"«([^»]{1,600})»|“([^”]{1,600})”", re.S)
# Notations équivalentes (l'ancien générateur écrit en latin-1 : « KEUR » pour « K€ ») — juste envers les deux systèmes.
NOTATION = [(re.compile(r"\bKEUR\b", re.I), "K€"), (re.compile(r"(?<=\d) ?EUR\b"), " €"), (re.compile(r"\bLT\b"), "long terme")]
LANG_CODES = {"FR": "français", "EN": "anglais", "ES": "espagnol", "AR": "arabe", "DE": "allemand", "PT": "portugais"}
LEVEL_HINT = re.compile(r"natif|native|courant|fluent|bilingue|intermédiaire|intermediaire|notions|\b[ABC][12]\b", re.I)
CATEGORIES = (("forbidden", "Terme interdit"), ("number", "Nombre sans preuve"), ("degree", "Diplôme"), ("tool", "Outil"),
              ("language", "Langue"), ("level", "Niveau de langue"), ("proper_noun", "Nom propre"), ("banned", "Phrase creuse"))


def _neutralize(text: str, offer_norm: str) -> str:
    """Retire les dates et les citations exactes de l'offre (le texte entre guillemets n'est pas une affirmation
    sur le candidat) en conservant les retours à la ligne. Même traitement pour l'ancien générateur et PAI."""
    def blank(m: re.Match[str]) -> str:
        inner = m.group(1) or m.group(2) or ""
        words = [w for w in re.findall(r"[a-z0-9]+", norm(inner)) if len(w) > 2]
        if words and sum(contains_term(offer_norm, w) for w in words) / len(words) >= 0.85:
            return re.sub(r"[^\n]", " ", m.group(0))
        return m.group(0)

    text = DATE.sub(" ", QUOTE.sub(blank, text))
    for pattern, repl in NOTATION:
        text = pattern.sub(repl, text)
    lines = []
    for line in text.split("\n"):
        if LEVEL_HINT.search(line):
            line = re.sub(r"\b(FR|EN|ES|AR|DE|PT)\b", lambda m: LANG_CODES[m.group(1)], line)
        lines.append(line)
    return "\n".join(lines)


def reason_categories(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key, _ in CATEGORIES}
    for item in rejected:
        for key, prefix in CATEGORIES:
            if any(r.startswith(prefix) for r in item["reasons"]):
                counts[key] += 1
    return counts


# ── Profil de référence ──────────────────────────────────────────────────────
def benchmark_profile() -> tuple[MasterProfile, str]:
    """Le profil réel (data/master_profile.json) s'il existe, sinon le profil v1 reconstruit (confirmations + legacy)."""
    from .profile import load_profile, profile_path

    if profile_path().exists():
        return load_profile(), "data/master_profile.json"
    from .bootstrap import build_master_profile

    return build_master_profile(), "bootstrap (profiles/confirmations.yaml + legacy)"


# ── Instrument commun ────────────────────────────────────────────────────────
def _structural(line: str, name_norm: str) -> bool:
    t = norm(line)
    if not t or t == name_norm or CONTACT.search(line):
        return True
    letters = [c for c in line if c.isalpha()]
    if len(line) <= 45 and letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return True  # titre de section
    return len(t) < 4


def free_text_factuality(pdf_text: str, profile: MasterProfile, offer: Offer, keywords: list[str],
                         rules: RuleSet) -> dict[str, Any]:
    """Vérifie chaque ligne du texte extrait contre tout le profil (voir docstring du module)."""
    validator = ClaimValidator(profile, offer.text, rules, keywords)
    evidence_ids = [f.id for f in profile.usable_facts()]
    name_norm = norm(profile.value("id.name"))
    company_norm = norm(offer.company_hint)
    checked, rejected = 0, []
    for i, raw in enumerate(_neutralize(pdf_text, norm(offer.text)).splitlines()):
        line = raw.strip(" •▪-–—\t")
        if _structural(line, name_norm) or SALUTATION.match(line):
            continue
        if company_norm and norm(line).startswith(company_norm) and len(line) < 90:
            continue  # bloc destinataire de la lettre (« Entreprise — Service recrutement »)
        checked += 1
        verdict = validator.validate_line(Line(id=f"l{i}", section="summary", kind="projection", text=line, fact_ids=evidence_ids))
        if not verdict.ok:
            rejected.append({"line": line[:160], "reasons": verdict.reasons[:3]})
    whole = norm(pdf_text.replace("\n", " "))
    forbidden = sorted({t for t in profile.forbidden_terms() if contains_term(whole, t)})
    score = 0.0 if forbidden else round(100 * (checked - len(rejected)) / checked, 1) if checked else 0.0
    return {"score": score, "checked": checked, "rejected": rejected, "forbidden": forbidden,
            "categories": reason_categories(rejected)}


def keyword_scores(pdf_text: str, analysis_keywords: list[tuple[str, str, bool]], rules: RuleSet,
                   offer_title: str = "") -> tuple[float, float, list[str]]:
    """(couverture brute pondérée, couverture honnête, mots-clés présents que le profil NE prouve PAS).
    Pondération REQUIRED 3 / IMPORTANT 2. Un mot de l'intitulé du poste repris en titre n'est pas du bourrage."""
    text = norm(pdf_text.replace("\n", " "))
    title = norm(offer_title)
    weight = {"REQUIRED": 3.0, "IMPORTANT": 2.0}
    total = found = honest_total = honest_found = 0.0
    stuffed: list[str] = []
    for term, priority, provable in analysis_keywords:
        w = weight.get(priority)
        if not w:
            continue
        present = rules.synonyms.supported_by(term, text) is not None
        total += w
        found += w * present
        if provable:
            honest_total += w
            honest_found += w * present
        elif present and not contains_term(title, term):
            stuffed.append(term)
    raw = round(100 * found / total, 1) if total else 100.0
    honest = round(100 * honest_found / honest_total, 1) if honest_total else 100.0
    return raw, honest, stuffed


def ats_parse_score(pdf_text: str) -> float:
    text = norm(pdf_text)
    score = 40.0 if len(pdf_text) >= 300 else 0.0
    score += sum(15.0 for words in SECTIONS.values() if any(contains_term(text, w) for w in words))
    score += 15.0 if "@" in pdf_text else 0.0
    return min(score, 100.0)


def pages_score(pages: int) -> float:
    return {1: 100.0, 2: 50.0}.get(pages, 0.0)


def pdf_qa_score(report: dict[str, Any]) -> float:
    penalty = sum({"high": 40, "medium": 15}.get(i["severity"], 0) for i in report.get("issues", []) if i["check"] != "pagination")
    return float(max(0, 100 - penalty))


def title_match(pdf_text: str, title: str) -> bool:
    head = norm(" ".join(pdf_text.splitlines()[:6]))
    words = [w for w in norm(clean_title(title)).split() if len(w) > 2 and w not in {"h/f", "f/h"}]
    return bool(words) and sum(contains_term(head, w) for w in words) / len(words) >= 0.6


def evaluate(cv_pdf: bytes | None, letter_pdf: bytes | None, profile: MasterProfile, offer: Offer, keywords: list[tuple[str, str, bool]],
             title: str, rules: RuleSet) -> dict[str, Any]:
    if not cv_pdf:
        return {"error": "aucun PDF produit", "total": 0.0, **{m: 0.0 for m in METRICS}}
    text = extract_text(cv_pdf)
    fact = free_text_factuality(text, profile, offer, [k[0] for k in keywords], rules)
    raw, honest, stuffed = keyword_scores(text, keywords, rules, title)
    qa = check_pdf(cv_pdf, expect_pages=1)
    row: dict[str, Any] = {
        "factuality": fact["score"], "keyword_coverage": raw, "ats_parse": ats_parse_score(text),
        "pages": pages_score(qa["pages"]), "pdf_qa": pdf_qa_score(qa),
        "honest_coverage": honest, "unprovable_keywords_used": len(stuffed), "unprovable_examples": stuffed[:5],
        "title_match": title_match(text, title), "forbidden_terms": fact["forbidden"],
        "unsupported_lines": len(fact["rejected"]), "checked_lines": fact["checked"], "n_pages": qa["pages"],
        "unsupported_by_reason": fact["categories"],
        "qa_issues": [f"{i['severity']}:{i['check']}" for i in qa["issues"]], "rejected_examples": fact["rejected"][:6],
        "arena_text": "\n".join(ln for ln in text.splitlines() if ln.strip() and not CONTACT.search(ln)
                                and norm(ln) != norm(profile.value("id.name"))),
    }
    if letter_pdf:
        row["letter_factuality"] = free_text_factuality(extract_text(letter_pdf), profile, offer, [k[0] for k in keywords], rules)["score"]
    weights = rules.scoring["benchmark"]["deterministic_weights"]
    row["total"] = round(sum(weights[m] * row[m] for m in METRICS) / sum(weights[m] for m in METRICS), 1)
    return row


# ── Générateurs ──────────────────────────────────────────────────────────────
def legacy_generator() -> Callable[[Offer, str, str], tuple[bytes | None, bytes | None]]:
    """Charge l'ancien générateur (legacy/), en lecture seule, sans le modifier."""
    legacy_dir = str(paths.LEGACY_DIR)
    if legacy_dir not in sys.path:
        sys.path.insert(0, legacy_dir)
    import cover_letter_france  # type: ignore[import-not-found]
    import cv_gen_france  # type: ignore[import-not-found]

    def generate(offer: Offer, contract: str, title: str) -> tuple[bytes | None, bytes | None]:
        data = {"titre": title, "entreprise": offer.company_hint, "description": offer.text}
        with contextlib.redirect_stdout(io.StringIO()):
            cv = cv_gen_france.generate(data, contract)
            letter = cover_letter_france.to_pdf(cover_letter_france.generate(data, contract), data)
        return bytes(cv), bytes(letter)

    return generate


def _stats(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(r[key]) for r in rows if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)]
    if not values:
        return {"mean": 0.0, "stdev": 0.0, "n": 0}
    return {"mean": round(statistics.fmean(values), 1), "stdev": round(statistics.pstdev(values), 1), "n": len(values)}


def _reason_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals = {key: 0 for key, _ in CATEGORIES}
    for r in rows:
        for key, n in (r.get("unsupported_by_reason") or {}).items():
            totals[key] += n
    return totals


def summarize(rows: list[dict[str, Any]], include_legacy: bool, profile_source: str) -> dict[str, Any]:
    pai_rows = [r["pai"] for r in rows]
    summary: dict[str, Any] = {
        "engine_v": ENGINE_VERSION, "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "n_offers": len(rows),
        "offers_synthetic": all(r["synthetic"] for r in rows), "profile_source": profile_source,
        "sector_accuracy": round(100 * sum(r["sector_ok"] for r in rows) / len(rows), 1) if rows else 0.0,
        "pai": {k: _stats(pai_rows, k) for k in ("total", *METRICS, "honest_coverage", "letter_factuality", "unsupported_lines",
                                                 "unprovable_keywords_used")},
    }
    summary["pai"]["forbidden_docs"] = sum(bool(r.get("forbidden_terms")) for r in pai_rows)
    summary["pai"]["unsupported_by_reason"] = _reason_totals(pai_rows)
    summary["pai"]["title_match_rate"] = round(100 * sum(bool(r.get("title_match")) for r in pai_rows) / len(pai_rows), 1) if pai_rows else 0.0
    if include_legacy:
        legacy_rows = [r["legacy"] for r in rows]
        summary["legacy"] = {k: _stats(legacy_rows, k) for k in ("total", *METRICS, "honest_coverage", "letter_factuality",
                                                               "unsupported_lines", "unprovable_keywords_used")}
        summary["legacy"]["forbidden_docs"] = sum(bool(r.get("forbidden_terms")) for r in legacy_rows)
        summary["legacy"]["unsupported_by_reason"] = _reason_totals(legacy_rows)
        summary["legacy"]["title_match_rate"] = round(100 * sum(bool(r.get("title_match")) for r in legacy_rows) / len(legacy_rows), 1) if legacy_rows else 0.0
        better, worse, same = [], [], []
        verdicts: dict[str, dict[str, Any]] = {}
        for key in ("total", *METRICS, "honest_coverage", "letter_factuality"):
            a, b = summary["pai"][key], summary["legacy"][key]
            delta = round(a["mean"] - b["mean"], 1)
            significant = abs(delta) > 3 and abs(delta) > 2 * max(a["stdev"], b["stdev"]) / max(1.0, len(rows) ** 0.5)
            verdicts[key] = {"pai": a["mean"], "legacy": b["mean"], "delta": delta, "significant": significant}
            (better if delta > 3 else worse if delta < -3 else same).append(key)
        summary["comparison"] = verdicts
        summary["conclusion"] = {
            "pai_better_on": better, "legacy_better_on": worse, "equivalent_on": same,
            "text": _conclusion(better, worse, same, summary),
        }
    summary["caveats"] = [
        "Offres SYNTHETIC (fictives) : mesure de la qualité documentaire, aucune conclusion sur les taux de réponse (A5).",
        "PAI mesuré en mode déterministe (sans IA) : c'est son plancher ; l'IA ajoute personnalisation et critique.",
        "Factualité mesurée en texte libre et de façon tolérante (chiffres et noms de l'offre admis) pour les deux systèmes.",
        "Aucun juge IA dans ce benchmark (pas de clé API ici) : l'Arène de PAI Studio fait les duels à l'aveugle avec Claude.",
    ]
    return summary


LABELS = {"total": "score global", "factuality": "factualité", "keyword_coverage": "couverture brute des mots-clés",
          "ats_parse": "lisibilité ATS", "pages": "pagination", "pdf_qa": "qualité PDF", "honest_coverage": "couverture honnête",
          "letter_factuality": "factualité de la lettre"}


def _fr(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _conclusion(better: list[str], worse: list[str], same: list[str], summary: dict[str, Any]) -> str:
    parts = []
    if better:
        parts.append("Le nouveau (PAI) est meilleur sur : " + ", ".join(LABELS.get(k, k) for k in better) + ".")
    if worse:
        parts.append("L'ancien était meilleur sur : " + ", ".join(LABELS.get(k, k) for k in worse) + ".")
    else:
        parts.append("L'ancien n'est meilleur sur aucun critère mesuré.")
    if same:
        parts.append("Équivalents (écart ≤ 3 points) : " + ", ".join(LABELS.get(k, k) for k in same) + ".")
    legacy = summary.get("legacy", {})
    if "keyword_coverage" in worse and legacy:
        parts.append(f"Sa couverture brute plus élevée vient en partie de mots-clés que le profil ne prouve pas "
                     f"({_fr(legacy['unprovable_keywords_used']['mean'])} par CV en moyenne, contre "
                     f"{_fr(summary['pai']['unprovable_keywords_used']['mean'])} pour PAI) : c'est du bourrage, que PAI refuse (A1).")
    if legacy.get("forbidden_docs"):
        parts.append(f"L'ancien affiche un terme interdit (MBA…) dans {legacy['forbidden_docs']}/{summary['n_offers']} CV "
                     f"et en moyenne {_fr(legacy['unsupported_lines']['mean'])} lignes non prouvées par CV (PAI : "
                     f"{_fr(summary['pai']['unsupported_lines']['mean'])}).")
    return " ".join(parts)


# ── Exécution ────────────────────────────────────────────────────────────────
def run_benchmark(include_legacy: bool = True, output_dir: Path | None = None, persist: bool = False,
                  profile: MasterProfile | None = None, only: list[str] | None = None) -> dict[str, Any]:
    from .ingest import benchmark_fixtures

    rules = load_rules()
    source = "fourni"
    if profile is None:
        profile, source = benchmark_profile()
    out = output_dir or paths.DATA_DIR / "benchmark" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    legacy = legacy_generator() if include_legacy else None
    rows: list[dict[str, Any]] = []
    for offer, meta in benchmark_fixtures():
        if only and meta.get("id") not in only:
            continue
        analysis = deterministic_analysis(offer, rules)
        match = compute_match(profile, analysis, rules)
        provable = {norm(c.term) for c in match.coverage if c.covered}
        keywords = [(k.term, k.priority, norm(k.term) in provable) for k in analysis.keywords]
        title = meta.get("title") or analysis.job_title
        pipe = Pipeline(profile, NullProvider(), mode="STANDARD")
        pack = pipe.run(offer)
        row: dict[str, Any] = {"offer": meta.get("id", offer.id), "company": offer.company_hint, "title": title,
                               "synthetic": offer.synthetic, "expected_sector": meta.get("expected_sector"),
                               "sector": analysis.sector_id, "sector_ok": analysis.sector_id == meta.get("expected_sector"),
                               "pai_status": pack.status,
                               "pai_internal_factuality": pack.scores.get("factuality_cv")}
        row["pai"] = evaluate(pipe.files.get("cv.pdf"), pipe.files.get("lettre.pdf"), profile, offer, keywords, title, rules)
        (out / f"{row['offer']}_pai_cv.pdf").write_bytes(pipe.files.get("cv.pdf", b""))
        if legacy is not None:
            try:
                cv, letter = legacy(offer, LEGACY_CONTRACT.get(analysis.contract.upper(), "cdi"), title)
                row["legacy"] = evaluate(cv, letter, profile, offer, keywords, title, rules)
                (out / f"{row['offer']}_legacy_cv.pdf").write_bytes(cv or b"")
            except Exception as exc:  # noqa: BLE001 — un échec de l'ancien générateur est un résultat, pas un crash
                row["legacy"] = {"error": f"{exc.__class__.__name__}: {exc}"[:300], "total": 0.0, **{m: 0.0 for m in METRICS}}
        rows.append(row)
    summary = summarize(rows, include_legacy, source)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(report_markdown(summary, rows), encoding="utf-8")
    studio = studio_payload(summary, rows)
    (out / "studio.json").write_text(json.dumps(studio, ensure_ascii=False, indent=1), encoding="utf-8")
    if persist:
        from .db.models import BenchmarkRun, StoreDocument, utcnow
        from .db.session import init_db, session_scope

        init_db()
        with session_scope() as s:
            s.add(BenchmarkRun(engine_v=ENGINE_VERSION, summary=summary, rows=public_rows(rows)))
            for path, data in studio.items():  # interface PAI Studio en mode serveur (même documents que l'artefact)
                doc = s.get(StoreDocument, path)
                if doc is None:
                    s.add(StoreDocument(path=path, collection=path.rsplit("/", 1)[0], data=data))
                else:
                    doc.data, doc.version, doc.updated_at = data, doc.version + 1, utcnow()
    return {"summary": summary, "rows": rows, "output_dir": str(out), "studio": studio}


def studio_payload(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Documents pour PAI Studio : `bench/summary` (tableau + conclusion) et `bench_pairs/*` (arène à l'aveugle).
    Les paires contiennent le texte des CV sans coordonnées ; elles restent dans la base privée du propriétaire."""
    legacy = "legacy" in summary
    docs: dict[str, dict[str, Any]] = {"bench/summary": {
        "engine_v": summary["engine_v"], "created_at": summary["run_at"], "n": summary["n_offers"], "synthetic": summary["offers_synthetic"],
        "new_avg": summary["pai"]["total"]["mean"], "legacy_avg": summary["legacy"]["total"]["mean"] if legacy else None,
        "conclusion": summary.get("conclusion", {}).get("text", ""), "comparison": summary.get("comparison", {}),
        "caveats": summary["caveats"],
        "rows": [{"title": f"{r['title']} · {r['company']}", "pai_score": r["pai"]["total"], "pai_factuality": r["pai"]["factuality"],
                  "pai_kw": r["pai"]["keyword_coverage"],
                  **({"legacy_score": r["legacy"]["total"], "legacy_factuality": r["legacy"]["factuality"],
                      "legacy_kw": r["legacy"]["keyword_coverage"], "legacy_forbidden": len(r["legacy"].get("forbidden_terms", []))}
                     if legacy and "legacy" in r else {})} for r in rows],
    }}
    if legacy:
        for r in rows:
            if r.get("legacy", {}).get("arena_text") and r["pai"].get("arena_text"):
                docs[f"bench_pairs/{r['offer']}"] = {"id": r["offer"], "title": f"{r['title']} · {r['company']}",
                                                     "legacy_text": r["legacy"]["arena_text"][:12000], "pai_text": r["pai"]["arena_text"][:12000]}
    return docs


def public_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lignes sans extraits de CV (publiables : scores seulement, offres fictives)."""
    keep = ("total", *METRICS, "honest_coverage", "letter_factuality", "title_match", "unsupported_lines", "checked_lines",
            "unsupported_by_reason", "unprovable_keywords_used", "n_pages", "qa_issues", "error")
    out = []
    for r in rows:
        item = {k: r[k] for k in ("offer", "company", "title", "expected_sector", "sector", "sector_ok", "pai_status")}
        for side in ("pai", "legacy"):
            if side in r:
                item[side] = {k: r[side][k] for k in keep if k in r[side]}
                item[side]["forbidden"] = bool(r[side].get("forbidden_terms"))
        out.append(item)
    return out


def report_markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [f"# Benchmark PAI {summary['engine_v']} — {summary['run_at']}", "",
             f"{summary['n_offers']} offres ({'SYNTHETIC' if summary['offers_synthetic'] else 'réelles'}), profil : {summary['profile_source']}.",
             f"Secteur détecté correct : {_fr(summary['sector_accuracy'])} %.", ""]
    if "legacy" in summary:
        lines += ["| Critère | Ancien | PAI | Écart |", "|---|---:|---:|---:|"]
        for key, v in summary["comparison"].items():
            lines.append(f"| {LABELS.get(key, key)} | {_fr(v['legacy'])} | {_fr(v['pai'])} | {'+' if v['delta'] >= 0 else ''}{_fr(v['delta'])} |")
        lines += ["", f"**Conclusion.** {summary['conclusion']['text']}", ""]
        lines += ["| Offre | Ancien | PAI | Lignes non prouvées (ancien → PAI) | Terme interdit (ancien) |", "|---|---:|---:|---:|---|"]
        for r in rows:
            lg = r.get("legacy", {})
            lines.append(f"| {r['offer']} | {_fr(lg['total']) if 'total' in lg else '—'} | {_fr(r['pai']['total'])} | "
                         f"{lg.get('unsupported_lines', '—')} → {r['pai'].get('unsupported_lines', '—')} | "
                         f"{', '.join(lg.get('forbidden_terms', [])) or 'non'} |")
    lines += ["", "Limites : " + " ".join(summary["caveats"])]
    return "\n".join(lines) + "\n"
