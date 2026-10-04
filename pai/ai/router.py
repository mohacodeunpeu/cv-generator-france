"""AI ROUTER : pour chaque tâche, AUCUNE IA, petit modèle local, grand modèle local, ou fournisseur externe.

Règles (config/models.yaml → `router`) :
  * les tâches déterministes n'appellent JAMAIS d'IA (parsing, coordonnées, dates, sections, mots-clés exacts,
    factualité, PDF, scores) : elles ne passent même pas par ici ;
  * chaque tâche IA a un niveau par profil (eco · balanced · quality) : none | small | large ;
  * `small` → petit modèle local, sinon grand modèle local, sinon externe (si configuré) ;
    `large` → externe s'il est le fournisseur actif, sinon grand modèle local, sinon petit ;
  * tout appel passe par le cache (hash : fournisseur, modèle, tâche, prompt versionné, paramètres) ;
  * une panne (Ollama éteint, quota, délai) lève ProviderError : le pipeline garde sa voie déterministe.

Le routeur est lui-même un AIProvider : le pipeline et l'API ne changent pas d'interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..providers.base import AIProvider, DegradedMode, ProviderResult
from ..rules import load_rules

PROFILES = ("eco", "balanced", "quality")
LEVELS = ("none", "small", "large")


def router_config() -> dict[str, Any]:
    return load_rules().models.get("router") or {}


def task_level(task: str, profile: str) -> str:
    """Niveau d'une tâche pour un profil ; tâche inconnue → niveau `default` du profil (prudent)."""
    cfg = router_config()
    tasks = cfg.get("tasks") or {}
    entry = tasks.get(task) or tasks.get(task.split(":")[0]) or tasks.get("default") or {}
    level = str(entry.get(profile) or entry.get("balanced") or "none")
    return level if level in LEVELS else "none"


@dataclass
class AIRouter(AIProvider):
    """Aiguillage par tâche entre les fournisseurs disponibles (chacun déjà enveloppé par le cache)."""

    name: str = "router"
    small: AIProvider | None = None        # petit modèle local
    large: AIProvider | None = None        # grand modèle local
    external: AIProvider | None = None     # fournisseur distant (Claude, OpenAI, Gemini, Mistral…) si actif
    active: str = "null"                   # identifiant du fournisseur actif (réglages)
    profile: str = "balanced"
    last_route: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            self.profile = "balanced"
        self.name = self.active or "null"   # les packs et le journal nomment le fournisseur actif, pas le routeur

    # -- aiguillage -----------------------------------------------------------------
    def _usable(self, p: AIProvider | None) -> AIProvider | None:
        return p if p is not None and p.available else None

    def route(self, task: str) -> tuple[str, AIProvider | None]:
        """(niveau retenu, fournisseur) ; (« none », None) = voie déterministe."""
        level = task_level(task, self.profile)
        if level == "none":
            return "none", None
        ext = self._usable(self.external)
        small, large = self._usable(self.small), self._usable(self.large)
        order = [("small", small), ("large", large), ("external", ext)] if level == "small" else \
                [("external", ext), ("large", large), ("small", small)]
        for tier, provider in order:
            if provider is not None:
                return tier, provider
        return "none", None

    def plan(self) -> dict[str, str]:
        """Tâche → niveau réellement servi avec la configuration actuelle (page Réglages / System Status)."""
        tasks = (router_config().get("tasks") or {}).keys()
        return {t: self.route(t)[0] for t in tasks if t != "default"}

    @property
    def available(self) -> bool:
        return any(self._usable(p) for p in (self.small, self.large, self.external))

    def model_for(self, task: str) -> str:
        tier, provider = self.route(task)
        return provider.model_for(task) if provider is not None else "none"

    def mode(self) -> str:
        """REMOTE (externe actif), LOCAL (modèle local), DEGRADED (sans IA)."""
        if self._usable(self.external):
            return "REMOTE"
        if self._usable(self.small) or self._usable(self.large):
            return "LOCAL"
        return "DEGRADED"

    # -- appels -----------------------------------------------------------------------
    def complete(self, task: str, prompt_text: str, prompt_tag: str = "", images: list[bytes] | None = None) -> ProviderResult:
        tier, provider = self.route(task)
        if provider is None:
            reason = "tâche traitée sans IA (profil « %s »)" % self.profile if task_level(task, self.profile) == "none" \
                else "aucun modèle disponible pour cette tâche"
            raise DegradedMode(f"{task} : {reason}")
        self.last_route = {"task": task, "tier": tier, "provider": provider.name, "model": provider.model_for(task)}
        before = len(provider.calls)
        from ..obs import tier_var

        token = tier_var.set(tier)
        try:
            return provider.complete(task, prompt_text, prompt_tag, images)
        finally:
            tier_var.reset(token)
            for rec in provider.calls[before:]:
                rec.tier = tier
                self.calls.append(rec)
                if self.on_call:
                    self.on_call(rec)

    def discard(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> None:
        provider = self.route(task)[1]
        if provider is not None:
            provider.discard(task, prompt_text, images)

    def remember(self, task: str, prompt_text: str, result: ProviderResult, images: list[bytes] | None = None) -> None:
        provider = self.route(task)[1]
        if provider is not None:
            provider.remember(task, prompt_text, result, images)

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError("AIRouter.complete aiguille directement vers le fournisseur choisi")

    @property
    def spent_eur(self) -> float:
        return round(sum(c.cost_eur for c in self.calls), 4)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeddings locaux uniquement (jamais de service payant pour la sémantique)."""
        for p in (self.small, self.large):
            inner = getattr(p, "inner", p)
            if inner is not None and hasattr(inner, "embed") and getattr(inner, "available", False):
                return inner.embed(texts)
        raise DegradedMode("aucun modèle d'embeddings local")
