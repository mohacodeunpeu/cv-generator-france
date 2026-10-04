"""Corpus métier : ce que demandent réellement les offres analysées, par famille de postes.

Pour chaque famille (variantes de CV : COMMERCIAL, BUSINESS_DEVELOPER…) : volume d'offres, intitulés, compétences,
outils, missions, qualités, fréquence de chaque terme (synonymes regroupés sous une forme canonique).
Un TOP 20 / TOP 40 n'est publié qu'au-delà d'un volume minimal (rules/ats_scoring.yaml → corpus) ; le volume est
toujours affiché. Les offres SYNTHETIC (tests, benchmark) sont exclues par défaut.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from ..analyzer import _SOFT_SKILLS, clean_title
from ..rules import load_rules
from ..textnorm import nb, norm, stable_hash
from .scoring import config
from .variants import select_variant


def _canonical(term: str) -> str:
    rules = load_rules()
    n = norm(term)
    for group in rules.synonyms.groups:
        if n in {norm(g) for g in group}:
            return group[0]
    return term.strip()


def build(analyses: Iterable[dict[str, Any]]) -> dict[str, Any]:
    cfg = config().get("corpus", {})
    min20, min40 = int(cfg.get("top20_min_offers", 10)), int(cfg.get("top40_min_offers", 25))
    fams: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for a in analyses:
        key = stable_hash([norm(a.get("job_title", "")), norm(a.get("company", "")), a.get("text_hash", "")], 12)
        if key in seen:
            continue
        seen.add(key)
        v = select_variant(a.get("job_title", ""), a.get("sector_id", ""))
        f = fams.setdefault(v["id"], {"label": v["label"], "offers": 0, "titles": Counter(), "skills": Counter(),
                                      "tools": Counter(), "missions": Counter(), "qualities": Counter()})
        f["offers"] += 1
        f["titles"][clean_title(a.get("job_title", "")).strip() or "?"] += 1
        terms = {_canonical(k["term"] if isinstance(k, dict) else str(k)) for k in a.get("keywords", [])}
        for t in terms:
            (f["qualities"] if norm(t) in _SOFT_SKILLS else f["skills"])[t] += 1
        for t in {_canonical(x) for x in a.get("tools", [])}:
            f["tools"][t] += 1
        for m in a.get("missions", [])[:10]:
            f["missions"][m.strip().rstrip(".")[:90]] += 1
    out: dict[str, Any] = {"families": {}, "total_offers": len(seen), "thresholds": {"top20": min20, "top40": min40}}
    for fid, f in sorted(fams.items(), key=lambda kv: -kv[1]["offers"]):
        n = f["offers"]
        top = 40 if n >= min40 else 20 if n >= min20 else 0

        def ranked(counter: Counter, limit: int, n: int = n) -> list[dict[str, Any]]:
            return [{"term": t, "count": c, "share": round(100 * c / n)} for t, c in counter.most_common(limit)]

        out["families"][fid] = {
            "label": f["label"], "offers": n, "top": top,
            "note": (f"TOP {top} publié ({n} offres analysées)." if top else
                     f"{nb(n, 'offre analysée', 'offres analysées')} : il en faut au moins {min20} pour publier un TOP 20 fiable."),
            "titles": ranked(f["titles"], 10),
            "skills": ranked(f["skills"], top) if top else [],
            "tools": ranked(f["tools"], min(top, 20)) if top else [],
            "qualities": ranked(f["qualities"], 10) if top else [],
            "missions": ranked(f["missions"], 10) if top else [],
            "sample": ranked(f["skills"], 8),   # aperçu toujours visible, présenté avec son volume
        }
    return out


def from_db(include_synthetic: bool = False) -> dict[str, Any]:
    """Analyses stockées : table `analyses` (API, pipeline) et packs du Studio (`store_documents`)."""
    from ..db.models import AnalysisRow, OfferRow, StoreDocument
    from ..db.session import session_scope

    rows: list[dict[str, Any]] = []
    with session_scope() as s:
        for a, o in s.query(AnalysisRow, OfferRow).join(OfferRow, OfferRow.id == AnalysisRow.offer_id):
            if o.deleted_at is None and (include_synthetic or not o.synthetic):
                rows.append(dict(a.analysis) | {"text_hash": o.text_hash})
        for d in s.query(StoreDocument).filter(StoreDocument.collection.like("%pack%")):
            data = d.data or {}
            stored = data.get("analysis")
            if isinstance(stored, dict) and (include_synthetic or not (data.get("offer") or {}).get("synthetic")):
                rows.append(stored | {"text_hash": (data.get("offer") or {}).get("text_hash", "")})
    return build(rows)
