"""NullProvider : mode dégradé (aucune IA). Chaque appel lève DegradedMode ;
le pipeline bascule alors sur ses voies déterministes et l'interface l'indique."""

from __future__ import annotations

from dataclasses import dataclass

from .base import AIProvider, DegradedMode, ProviderResult


@dataclass
class NullProvider(AIProvider):
    name: str = "null"

    @property
    def available(self) -> bool:
        return False

    def model_for(self, task: str) -> str:
        return "none"

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:
        raise DegradedMode("Mode dégradé : aucun fournisseur IA configuré")
