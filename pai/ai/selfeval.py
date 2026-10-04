"""Auto-évaluation des modèles d'IA sur les tâches PAI (données fictives : benchmark/selfeval/cases.yaml).

Sept mesures, chacune de 0 à 100 :
  1 extraction      — poste, entreprise, contrat, lieu, salaire, langues, outils
  2 classification  — exigences en MUST / IMPORTANT / NICE_TO_HAVE / CONTEXT
  3 matching        — PROUVÉ / PLAUSIBLE / NON_PROUVÉ (une sur-déclaration coûte cher)
  4 reformulation   — reprendre le vocabulaire de l'offre sans rien inventer
  5 factualité      — repérer les phrases inventées ou gonflées
  6 lettre          — courte, nomme l'entreprise, n'invente ni chiffre, ni outil, ni diplôme
  7 JSON            — part des réponses en JSON valide du premier coup
et, par modèle : vitesse (jetons générés / s), mémoire chargée (Ollama /api/ps), latence.

La qualité globale pondère davantage ce qui touche à la vérité (matching, factualité, reformulation, lettre).
Le choix du modèle (`choose`) garde le meilleur compromis qualité / vitesse qui tient dans la machine ;
le mode « sans IA » est mesuré avec les mêmes cas quand une voie déterministe existe.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from functools import lru_cache
from typing import Any, Callable

import yaml

from .. import paths
from ..providers.base import AIProvider, ProviderError, extract_json

WEIGHTS = {"extraction": 1.0, "classification": 1.0, "matching": 1.5, "reformulation": 1.5, "factuality": 1.5, "letter": 1.5}
TASK_FOR = {"extraction": "extract", "classification": "classify", "matching": "classify", "reformulation": "cv_fix",
            "factuality": "classify", "letter": "letter"}


@lru_cache(maxsize=1)
def cases() -> dict[str, Any]:
    return yaml.safe_load((paths.BENCHMARK_DIR / "selfeval" / "cases.yaml").read_text(encoding="utf-8"))


def norm(text: Any) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


# ── Prompts compacts (contexte minimal, JSON imposé) ─────────────────────────────────────────────
def _facts() -> str:
    return "\n".join(cases()["facts"])


def prompts() -> dict[str, str]:
    c = cases()
    reqs = "\n".join(f"{i + 1}. {x['text']}" for i, x in enumerate(c["classification"]))
    match = "\n".join(f"{i + 1}. {x['requirement']}" for i, x in enumerate(c["matching"]))
    sents = "\n".join(f"{i + 1}. {x['sentence']}" for i, x in enumerate(c["factuality"]))
    return {
        "extraction": ("Offre d'emploi :\n" + c["offer"] + "\nExtrais ces champs. Réponds UNIQUEMENT en JSON : "
                       '{"title": "", "company": "", "contract": "", "location": "", "salary": "", "languages": [], "tools": []}'),
        "classification": ("Classe chaque élément de l'offre : MUST (obligatoire), IMPORTANT (mission ou compétence clé), "
                           "NICE_TO_HAVE (un plus), CONTEXT (information sur le poste ou l'entreprise).\n" + reqs +
                           f'\nRéponds UNIQUEMENT en JSON : {{"labels": ["MUST", "CONTEXT", …]}} : exactement {len(c["classification"])} '
                           "libellés, dans l'ordre, chacun parmi MUST, IMPORTANT, NICE_TO_HAVE, CONTEXT ; ne recopie pas les phrases."),
        "matching": ("Faits prouvés du candidat (seule source de vérité) :\n" + _facts() + "\n\nPour chaque exigence, réponds "
                     "PROUVÉ si un fait la démontre, PLAUSIBLE si un fait s'en approche sans la démontrer, NON_PROUVÉ sinon. "
                     "Ne suppose rien.\n" + match + f'\nRéponds UNIQUEMENT en JSON : {{"labels": ["PROUVÉ", "NON_PROUVÉ", …]}} : '
                     f"exactement {len(c['matching'])} libellés, dans l'ordre, chacun parmi PROUVÉ, PLAUSIBLE, NON_PROUVÉ ; "
                     "ne recopie pas les exigences."),
        "reformulation": ("Faits prouvés :\n" + _facts() + "\n\nReformule cette ligne de CV pour reprendre le vocabulaire de "
                          f"l'offre (« {c['reformulation']['keyword']} ») SANS ajouter aucun fait, chiffre, outil ni diplôme : "
                          f"« {c['reformulation']['bullet']} ».\n" + 'Réponds UNIQUEMENT en JSON : {"text": ""}.'),
        "factuality": ("Faits prouvés :\n" + _facts() + "\n\nPour chaque phrase, réponds true si elle est entièrement prouvée "
                       "par les faits, false si elle invente ou gonfle quelque chose.\n" + sents +
                       '\nRéponds UNIQUEMENT en JSON : {"supported": [true, …]}.'),
        "letter": ("Faits prouvés (n'utilise RIEN d'autre) :\n" + _facts() + f"\n\nOffre :\n{c['offer']}\n"
                   f"Écris le corps d'une lettre de motivation courte (3 paragraphes, {c['letter']['min_words']} à "
                   f"{c['letter']['max_words']} mots) pour {c['letter']['company']}. Aucun chiffre, outil ou diplôme absent "
                   'des faits.\nRéponds UNIQUEMENT en JSON : {"text": ""}.'),
    }


# ── Notation ───────────────────────────────────────────────────────────────────────────────────
def _labels(out: Any, key: str, n: int) -> list[str]:
    items = out.get(key) if isinstance(out, dict) else out
    items = [norm(x).upper().replace(" ", "_").replace("PROUVE", "PROUVE") for x in (items or [])][:n]
    return items + [""] * (n - len(items))


def score_extraction(out: Any) -> float:
    gold = cases()["extraction_gold"]
    if not isinstance(out, dict):
        return 0.0
    parts = []
    for k, g in gold.items():
        v = out.get(k)
        if isinstance(g, list):
            got = " ".join(norm(x) for x in (v or [])) if isinstance(v, list) else norm(v)
            parts.append(sum(1 for x in g if norm(x) in got) / len(g))
        else:
            parts.append(1.0 if norm(g) in norm(v) else 0.0)
    return round(100 * sum(parts) / len(parts), 1)


def score_classification(out: Any) -> float:
    gold = [x["gold"] for x in cases()["classification"]]
    got = _labels(out, "labels", len(gold))
    return round(100 * sum(1 for a, b in zip(got, gold) if a == b) / len(gold), 1)


def score_matching(out: Any) -> tuple[float, int]:
    gold = [norm(x["gold"]).upper() for x in cases()["matching"]]
    got = _labels(out, "labels", len(gold))
    ok = sum(1 for a, b in zip(got, gold) if a == b)
    overclaims = sum(1 for a, b in zip(got, gold) if b == "NON_PROUVE" and a == "PROUVE")
    return max(0.0, round(100 * ok / len(gold) - 25 * overclaims, 1)), overclaims


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text or ""))


def _fact_numbers() -> set[str]:
    return _numbers(_facts() + cases()["offer"])


def score_reformulation(out: Any) -> float:
    c = cases()["reformulation"]
    text = norm(out.get("text") if isinstance(out, dict) else out)
    if not text:
        return 0.0
    score = 100.0
    kw = norm(c["keyword"])
    if kw not in text and not all(w in text for w in kw.split()):
        score -= 40
    if any(norm(f) in text for f in c["forbidden"]):
        score -= 60
    if _numbers(text) - _numbers(c["bullet"]):
        score -= 60
    return max(0.0, score)


def score_factuality(out: Any) -> tuple[float, int]:
    gold = [bool(x["gold"]) for x in cases()["factuality"]]
    items = out.get("supported") if isinstance(out, dict) else out
    got = [(str(x).strip().lower() in ("true", "1", "oui", "vrai")) if not isinstance(x, bool) else x for x in (items or [])][:len(gold)]
    got += [None] * (len(gold) - len(got))
    ok = sum(1 for a, b in zip(got, gold) if a == b)
    accepted_lies = sum(1 for a, b in zip(got, gold) if b is False and a is True)
    return max(0.0, round(100 * ok / len(gold) - 20 * accepted_lies, 1)), accepted_lies


def score_letter(out: Any) -> tuple[float, list[str]]:
    c = cases()["letter"]
    raw = out.get("text") if isinstance(out, dict) else out
    text = norm(raw)
    problems = []
    words = len(text.split())
    if norm(c["company"]) not in text:
        problems.append("entreprise absente")
    if not c["min_words"] <= words <= c["max_words"] * 1.3:
        problems.append(f"{words} mots")
    hits = [f for f in c["forbidden"] if norm(f) in text]
    if hits:
        problems.append("invente : " + ", ".join(hits))
    extra = _numbers(str(raw or "")) - _fact_numbers()
    if extra:
        problems.append("chiffres absents des faits : " + ", ".join(sorted(extra)))
    penalty = {"entreprise absente": 25}
    score = 100.0
    for p in problems:
        score -= penalty.get(p, 50 if p.startswith(("invente", "chiffres")) else 20)
    return max(0.0, score), problems


SCORERS: dict[str, Callable[[Any], Any]] = {"extraction": score_extraction, "classification": score_classification,
                                            "matching": score_matching, "reformulation": score_reformulation,
                                            "factuality": score_factuality, "letter": score_letter}


def _unpack(v: Any) -> tuple[float, dict[str, Any]]:
    if isinstance(v, tuple):
        extra = v[1]
        return float(v[0]), ({"overclaims": extra} if isinstance(extra, int) else {"problems": extra})
    return float(v), {}


def quality(scores: dict[str, float]) -> float:
    total = sum(WEIGHTS[t] for t in scores)
    return round(sum(scores[t] * WEIGHTS[t] for t in scores) / total, 1) if total else 0.0


# ── Exécution ──────────────────────────────────────────────────────────────────────────────────
def run_provider(provider: AIProvider, *, tasks: list[str] | None = None) -> dict[str, Any]:
    """Mesure un fournisseur (modèle) sur les tâches ; aucune exception : un échec vaut 0 et est noté."""
    out: dict[str, Any] = {"model": provider.model_for("extract"), "scores": {}, "details": {}, "latency_s": {}, "json_ok": 0,
                           "tokens_out": 0, "gen_seconds": 0.0}
    for task in tasks or list(SCORERS):
        prompt = prompts()[task]
        t0 = time.monotonic()
        try:
            res = provider.complete(TASK_FOR[task], prompt, prompt_tag=f"selfeval:{task}")
            try:
                parsed = extract_json(res.text)
                out["json_ok"] += 1
            except ValueError:
                parsed = res.text
            score, detail = _unpack(SCORERS[task](parsed))
            out["tokens_out"] += res.tokens_out
            out["gen_seconds"] += max(0.001, res.latency_ms / 1000)
        except ProviderError as exc:
            score, detail = 0.0, {"error": str(exc)[:160]}
        out["latency_s"][task] = round(time.monotonic() - t0, 1)
        out["scores"][task] = score
        if detail:
            out["details"][task] = detail
    n = len(out["scores"]) or 1
    out["scores"]["json"] = round(100 * out["json_ok"] / n, 1)
    out["quality"] = quality({k: v for k, v in out["scores"].items() if k in WEIGHTS})
    out["tokens_per_s"] = round(out["tokens_out"] / out["gen_seconds"], 1) if out["gen_seconds"] else 0.0
    out["total_s"] = round(sum(out["latency_s"].values()), 1)
    return out


def run_deterministic() -> dict[str, Any]:
    """Même mesure pour le mode SANS IA, là où une voie déterministe existe (extraction, classement, correspondance)."""
    from ..analyzer import deterministic_analysis
    from ..rules import load_rules
    from ..ingest import offer_from_text

    c = cases()
    scores: dict[str, float] = {}
    a = deterministic_analysis(offer_from_text(c["offer"]), load_rules())
    scores["extraction"] = score_extraction({
        "title": a.job_title, "company": a.company, "contract": a.contract, "location": a.location,
        "salary": " ".join(str(v) for v in (a.salary or {}).values()),
        "languages": [str(x.get("language") or x.get("name") or x) for x in a.languages],
        "tools": list(a.tools)})
    try:
        from ..ats.requirements import classify_requirement, proof_status_for_texts

        scores["classification"] = score_classification({"labels": [classify_requirement(x["text"]) for x in c["classification"]]})
        scores["matching"] = score_matching({"labels": [proof_status_for_texts(x["requirement"], c["facts"]) for x in c["matching"]]})[0]
    except ImportError:
        pass
    return {"model": "sans IA", "scores": scores, "quality": quality(scores), "tokens_per_s": 0.0, "total_s": 0.0}


def loaded_memory_gb(base_url: str, model: str) -> float:
    import httpx

    try:
        for m in httpx.get(f"{base_url}/api/ps", timeout=5).json().get("models", []):
            if m.get("name", "").split(":")[0] == model.split(":")[0]:
                return round(int(m.get("size", 0)) / 1e9, 2)
    except (httpx.HTTPError, ValueError):
        return 0.0
    return 0.0


def truthful(r: dict[str, Any]) -> bool:
    """Barrière de vérité (FACTUALITÉ avant tout) : aucun « prouvé » accordé à tort, aucune phrase inventée acceptée,
    aucun terme inventé dans la lettre, JSON exploitable. Un modèle qui échoue ici n'est jamais choisi, quel que soit
    son score ou sa vitesse."""
    d = r.get("details") or {}
    return (not (d.get("matching") or {}).get("overclaims") and not (d.get("factuality") or {}).get("overclaims")
            and not any("invente" in x for x in (d.get("letter") or {}).get("problems", []))
            and (r.get("scores") or {}).get("json", 0) >= 80)


def choose(results: list[dict[str, Any]], min_tps: dict[str, float]) -> dict[str, str]:
    """Parmi les modèles qui passent la barrière de vérité et tiennent la vitesse minimale du niveau
    (min_tps['large'] / min_tps['small']) : la meilleure qualité ; à égalité, le plus rapide."""
    from .registry import by_installed_name

    def tiers(r):
        c = by_installed_name(r["model"]) or by_installed_name(r["model"].removesuffix(":latest"))
        return set(c.tiers) if c else {"small", "large"}

    out: dict[str, str] = {}
    for tier, default in (("large", 3), ("small", 8)):
        ok = [r for r in results if tier in tiers(r) and truthful(r) and r.get("tokens_per_s", 0) >= min_tps.get(tier, default)]
        if ok:
            out[tier] = max(ok, key=lambda r: (r["quality"], r["tokens_per_s"]))["model"]
    return out


ECO_BELOW_TPS = 8.0   # grand modèle plus lent que ça (CPU sans GPU) : l'IA ne sert qu'aux tâches qui en valent la peine


def recommend_profile(selection: dict[str, str], report: dict[str, Any]) -> str:
    """`eco` quand le grand modèle choisi génère moins de 8 jetons/s (une lettre ≈ 3 à 6 min sur CPU) : seules la
    lettre et l'extraction passent par l'IA ; sinon `balanced`. Mesuré, jamais supposé."""
    large = selection.get("large", "")
    tps = next((float(r.get("tokens_per_s") or 0) for r in report.get("results", []) if r.get("model") == large), 0.0)
    return "eco" if large and tps < ECO_BELOW_TPS else "balanced"


def save_selection(selection: dict[str, str], report: dict[str, Any]) -> str:
    target = paths.DATA_DIR / "ai"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "local_selection.json"
    path.write_text(json.dumps({"selection": selection, "recommended_profile": recommend_profile(selection, report),
                                "report": report, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)
