"""Fournisseurs compatibles OpenAI : OpenAI, Gemini, Mistral (API distantes) et LocalProvider (Ollama, vLLM…).

Même protocole HTTP `/chat/completions`. OpenAI et local : le nom du modèle vient de l'environnement ou des
Réglages → IA (aucun nom inventé dans le code) ; Gemini et Mistral ont un modèle par défaut documenté
(pai/config.py, config/models.yaml). Les messages d'erreur ne contiennent jamais la clé.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import GEMINI_DEFAULT_MODEL, MISTRAL_DEFAULT_MODEL
from .base import AIProvider, ProviderError, ProviderResult

OPENAI_BASE_URL = "https://api.openai.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
LOCAL_BASE_URL = "http://localhost:11434/v1"
_HTTP_HINTS = {400: "requête refusée : modèle ou paramètres ?", 401: "clé refusée", 403: "accès refusé",
               404: "modèle ou URL introuvable", 429: "limite de débit ou quota atteint"}


@dataclass
class OpenAICompatProvider(AIProvider):
    name: str = "openai"
    base_url: str = OPENAI_BASE_URL
    api_key: str = field(default="", repr=False)
    model: str = ""
    requires_key: bool = True
    timeout: float = 180.0

    @property
    def available(self) -> bool:
        return bool(self.model) and (bool(self.api_key) or not self.requires_key)

    def model_for(self, task: str) -> str:
        return self.model

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:
        content: Any = prompt_text
        if images:
            content = [{"type": "text", "text": prompt_text}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()}}
                for i in images]
        payload = {"model": self.model, "messages": [{"role": "user", "content": content}], "temperature": 0.2}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        start = time.monotonic()
        try:
            resp = httpx.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            hint = _HTTP_HINTS.get(code, "service indisponible" if code >= 500 else "réponse inattendue")
            raise ProviderError(f"{self.name} : HTTP {code} ({hint})") from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.name} : délai de réponse dépassé") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} : {exc.__class__.__name__}") from exc
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} : réponse inattendue") from exc
        usage = data.get("usage") or {}
        return ProviderResult(text=text, model=self.model, tokens_in=int(usage.get("prompt_tokens", 0)),
                              tokens_out=int(usage.get("completion_tokens", 0)), cost_eur=0.0,
                              latency_ms=int((time.monotonic() - start) * 1000))


def openai_provider(api_key: str, model: str, base_url: str = OPENAI_BASE_URL) -> OpenAICompatProvider:
    return OpenAICompatProvider(name="openai", base_url=base_url or OPENAI_BASE_URL, api_key=api_key, model=model, requires_key=True)


def gemini_provider(api_key: str, model: str = "", base_url: str = GEMINI_BASE_URL) -> OpenAICompatProvider:
    """Google Gemini par son point d'accès compatible OpenAI (clé GEMINI_API_KEY en `Bearer`)."""
    return OpenAICompatProvider(name="gemini", base_url=base_url or GEMINI_BASE_URL, api_key=api_key,
                                model=model or GEMINI_DEFAULT_MODEL, requires_key=True)


def mistral_provider(api_key: str, model: str = "", base_url: str = MISTRAL_BASE_URL) -> OpenAICompatProvider:
    """Mistral AI (API La Plateforme, compatible OpenAI ; clé MISTRAL_API_KEY en `Bearer`)."""
    return OpenAICompatProvider(name="mistral", base_url=base_url or MISTRAL_BASE_URL, api_key=api_key,
                                model=model or MISTRAL_DEFAULT_MODEL, requires_key=True)


def local_provider(model: str, base_url: str = LOCAL_BASE_URL) -> OpenAICompatProvider:
    return OpenAICompatProvider(name="local", base_url=base_url or LOCAL_BASE_URL, api_key="", model=model, requires_key=False)
