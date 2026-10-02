"""Correspondance sémantique : taxonomie métier (rules/taxonomy_fr.yaml), formes proches, et embeddings locaux en option.

Règle absolue : SÉMANTIQUE ≠ PREUVE. Tout ce module ne produit que des rapprochements (PLAUSIBLE au mieux) ou des
compétences voisines à signaler ; seul un fait qui dit la chose (mot exact ou synonyme déclaré) prouve.

Embeddings : optionnels (modèle local via Ollama, ex. EmbeddingGemma). Désactivés par défaut ; sans eux, la
taxonomie et les racines suffisent. Les vecteurs sont mis en cache par empreinte du texte.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import yaml

from .. import paths
from ..textnorm import contains_term, norm, stable_hash


@dataclass(frozen=True)
class Family:
    id: str
    label: str
    category: tuple[str, ...]
    members: tuple[str, ...]


@lru_cache(maxsize=1)
def families() -> tuple[Family, ...]:
    raw = yaml.safe_load((paths.RULES_DIR / "taxonomy_fr.yaml").read_text(encoding="utf-8")) or {}
    return tuple(Family(fid, f.get("label", fid), tuple(norm(x) for x in f.get("category", [])),
                        tuple(norm(x) for x in f.get("members", [])))
                 for fid, f in (raw.get("families") or {}).items())


def family_of_category(term: str) -> Family | None:
    """L'exigence désigne-t-elle une famille (« un CRM », « outils bureautiques ») ?"""
    t = norm(term)
    return next((f for f in families() if t in f.category), None)


def families_of_member(term: str) -> list[Family]:
    t = norm(term)
    return [f for f in families() if t in f.members]


def members_in(text_norm: str, family: Family, exclude: str = "") -> list[str]:
    ex = norm(exclude)
    return [m for m in family.members if m != ex and contains_term(text_norm, m)]


# ── Embeddings locaux (optionnels) ───────────────────────────────────────────────────────────────
# EmbeddingGemma attend des préfixes de tâche ; sans eux, la séparation est faible (mesuré : 0,66 vs 0,64).
QUERY_PREFIX = "task: sentence similarity | query: "
_VECTORS: dict[str, list[float]] = {}


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class Embedder:
    """Enveloppe d'un fournisseur qui sait `embed(list[str])` (OllamaProvider) : cache + préfixe + seuil calibré."""

    def __init__(self, embed: Callable[[list[str]], list[list[float]]], model: str, threshold: float = 0.72):
        self.embed_fn, self.model, self.threshold = embed, model, threshold

    def vectors(self, texts: list[str]) -> list[list[float]]:
        keys = [stable_hash(f"{self.model}|{t}", 16) for t in texts]
        todo = [t for t, k in zip(texts, keys) if k not in _VECTORS]
        if todo:
            for t, v in zip(todo, self.embed_fn([QUERY_PREFIX + t for t in todo])):
                _VECTORS[stable_hash(f"{self.model}|{t}", 16)] = v
        return [_VECTORS[k] for k in keys]

    def best(self, query: str, candidates: list[str]) -> tuple[float, int]:
        if not candidates:
            return 0.0, -1
        q, *cs = self.vectors([query, *candidates])
        scores = [cosine(q, c) for c in cs]
        i = max(range(len(scores)), key=scores.__getitem__)
        return scores[i], i


def local_embedder() -> Embedder | None:
    """Embedder local si PAI_SEMANTIC_EMBEDDINGS=1 et un modèle d'embeddings est installé ; sinon None (sans IA)."""
    import os

    if os.environ.get("PAI_SEMANTIC_EMBEDDINGS", "0") not in ("1", "true", "yes"):
        return None
    try:
        from ..providers.ollama import OllamaProvider

        p = OllamaProvider(tier="embed")
        if not p.available:
            return None
        return Embedder(p.embed, p.resolved_model(), float(os.environ.get("PAI_SEMANTIC_THRESHOLD", "0.72")))
    except Exception:  # noqa: BLE001 — l'option sémantique ne doit jamais casser l'analyse
        return None
