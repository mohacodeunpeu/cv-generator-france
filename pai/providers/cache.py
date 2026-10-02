"""Cache et enregistrement/rejeu des appels IA.

Clé = hash(fournisseur + modèle + version du prompt + entrée). Modes :
  on          — lit le cache, sinon appelle et enregistre ;
  off         — appelle toujours ;
  replay_only — lit le cache, sinon échec (tests déterministes, gratuits, hors ligne).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..textnorm import stable_hash
from .base import AIProvider, DegradedMode, ProviderResult


@dataclass
class CachedProvider(AIProvider):
    inner: AIProvider = field(default_factory=lambda: AIProvider())
    cache_dir: Path = Path("data/cache")
    mode: str = "on"
    _current_tag: str = ""

    def __post_init__(self) -> None:
        self.name = self.inner.name
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:  # cache indisponible (disque plein, droits) : PAI continue sans cache
            self.mode = "off" if self.mode == "on" else self.mode

    @property
    def available(self) -> bool:
        return self.inner.available or self.mode == "replay_only"

    def model_for(self, task: str) -> str:
        return self.inner.model_for(task)

    def key(self, task: str, prompt_text: str) -> str:
        """Hash de l'entrée complète : fournisseur, modèle, tâche, prompt rendu (versionné, contient l'offre et le
        profil utiles) et paramètres de génération. Changer l'un d'eux = nouvelle clé = nouvel appel."""
        fp = getattr(self.inner, "config_fingerprint", None)
        return stable_hash([self.inner.name, self.model_for(task), task, prompt_text, fp(task) if callable(fp) else ""], 24)

    def complete(self, task: str, prompt_text: str, prompt_tag: str = "", images: list[bytes] | None = None) -> ProviderResult:
        self._current_tag = prompt_tag
        return super().complete(task, prompt_text, prompt_tag, images)

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:
        img_key = stable_hash(b"".join(images), 12) if images else ""
        path = self.cache_dir / f"{task}-{self.key(task, prompt_text + img_key)}.json"
        if self.mode in ("on", "replay_only"):
            try:
                data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            except (OSError, ValueError):  # entrée illisible : ignorée, l'appel est refait
                data = None
            if data is not None:
                return ProviderResult(text=data["text"], model=data["model"], tokens_in=data.get("tokens_in", 0),
                                      tokens_out=data.get("tokens_out", 0), cost_eur=0.0, cached=True)
        if self.mode == "replay_only":
            raise DegradedMode(f"Rejeu hors ligne : aucune réponse enregistrée pour {task} ({path.name})")
        result = self.inner._complete(task, prompt_text, images)
        if self.mode == "on":
            try:
                path.write_text(json.dumps({"task": task, "prompt_tag": self._current_tag, "model": result.model,
                                            "text": result.text, "tokens_in": result.tokens_in,
                                            "tokens_out": result.tokens_out}, ensure_ascii=False, indent=1), encoding="utf-8")
            except OSError:  # écriture impossible : le résultat est rendu quand même
                pass
        return result
