"""Variantes de CV (MASTER, COMMERCIAL, BUSINESS_DEVELOPER, RECRUTEMENT, DIGITAL, CHARGE_AFFAIRES).

Le CV MAÎTRE reste la seule source de vérité ; une variante n'est qu'un angle (rules/cv_variants.yaml).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from .. import paths
from ..textnorm import contains_term, norm


@lru_cache(maxsize=1)
def variants() -> dict[str, Any]:
    return yaml.safe_load((paths.RULES_DIR / "cv_variants.yaml").read_text(encoding="utf-8")) or {}


def select_variant(title: str, sector_id: str = "") -> dict[str, Any]:
    """Variante retenue et pourquoi (intitulé d'abord, puis secteur, sinon MASTER)."""
    cfg = variants()
    t = norm(title)
    for vid in cfg.get("order", []):
        v = cfg["variants"][vid]
        hit = next((w for w in v.get("title", []) if contains_term(t, w)), "")
        if hit:
            return {"id": vid, "label": v["label"], "angle": v.get("angle", ""), "skill_groups": v.get("skill_groups", []),
                    "why": f"intitulé « {title} » (mot repère : {hit})"}
    for vid in cfg.get("order", []):
        v = cfg["variants"][vid]
        if sector_id and sector_id in v.get("sectors", []):
            return {"id": vid, "label": v["label"], "angle": v.get("angle", ""), "skill_groups": v.get("skill_groups", []),
                    "why": f"secteur de l'offre ({sector_id})"}
    m = cfg["variants"]["MASTER"]
    return {"id": "MASTER", "label": m["label"], "angle": m.get("angle", ""), "skill_groups": m.get("skill_groups", []),
            "why": "aucun repère d'intitulé ou de secteur : CV maître"}
