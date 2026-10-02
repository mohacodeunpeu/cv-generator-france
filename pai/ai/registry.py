"""Registre des modèles locaux (config/local_models.yaml) : quels candidats tiennent sur CETTE machine, dans quel ordre.

Aucun choix n'est figé ici : `recommend()` filtre par mémoire, cœurs et architecture, puis `pai.ai.selfeval` mesure
les candidats installés et `pai.ai.setup` enregistre le meilleur compromis mesuré.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from .. import paths
from .hardware import Hardware

TIERS = ("small", "large", "embed")


@dataclass
class Candidate:
    id: str
    ollama: str
    docker_hub: str = ""
    params_b: float = 0.0
    file_gb: float = 0.0
    ram_gb: float = 0.0
    tiers: list[str] = field(default_factory=list)
    prior: int = 9
    think: bool | None = None
    min_cpus: float = 0.0
    license: str = ""
    notes: str = ""

    def names(self) -> set[str]:
        """Noms sous lesquels le modèle peut être installé (bibliothèque Ollama ou import hors ligne)."""
        base = self.ollama.split(":")[0]
        out = {self.id, self.ollama, f"{self.id}:latest"}
        if ":" not in self.ollama:
            out |= {base, f"{base}:latest"}
        return out


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    path = paths.ROOT / "config" / "local_models.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"candidates": [], "tasks": {}}


def candidates() -> list[Candidate]:
    return [Candidate(**{k: v for k, v in c.items() if k in Candidate.__dataclass_fields__}) for c in load_registry().get("candidates", [])]


def task_params(task: str) -> dict[str, Any]:
    tasks = load_registry().get("tasks", {})
    return {**tasks.get("default", {}), **tasks.get(task, {})}


def by_installed_name(name: str) -> Candidate | None:
    for c in candidates():
        if name in c.names():
            return c
    return None


def fits(c: Candidate, hw: Hardware) -> tuple[bool, str]:
    """Le modèle tient-il sur la machine ? (raison lisible si non)."""
    reserve = float(load_registry().get("reserve_ram_gb", 3.0))
    budget = (hw.ram_total_gb - reserve) if hw.ram_total_gb else 0.0
    if hw.vram_gb >= c.ram_gb:
        return True, f"GPU {hw.vram_gb:.0f} Go de VRAM"
    if budget and c.ram_gb > budget:
        return False, f"{c.ram_gb:.1f} Go nécessaires, {budget:.1f} Go disponibles pour un modèle"
    if c.min_cpus and hw.cpus and hw.cpus < c.min_cpus and not hw.gpus:
        return False, f"{c.min_cpus:.0f} cœurs conseillés sans GPU ({hw.cpus:.0f} ici) : trop lent"
    return True, "tient en mémoire"


def recommend(hw: Hardware) -> dict[str, list[dict[str, Any]]]:
    """Candidats par niveau, du plus prometteur au moins prometteur, avec la raison d'exclusion éventuelle."""
    out: dict[str, list[dict[str, Any]]] = {t: [] for t in TIERS}
    for c in candidates():
        ok, why = fits(c, hw)
        for tier in c.tiers:
            out[tier].append({"id": c.id, "ollama": c.ollama, "fits": ok, "why": why, "prior": c.prior, "ram_gb": c.ram_gb})
    for tier in out:
        out[tier].sort(key=lambda x: (not x["fits"], x["prior"]))
    return out
