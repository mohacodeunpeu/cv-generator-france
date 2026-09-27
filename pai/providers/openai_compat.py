"""Fournisseurs compatibles OpenAI : OpenAIProvider (API OpenAI) et LocalProvider (Ollama, vLLM…).

Même protocole HTTP `/chat/completions`. Le nom du modèle vient de l'environnement :
aucun nom de modèle n'est inventé dans le code.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .base import AIProvider, ProviderError, ProviderResult


@dataclass
class OpenAICompatProvider(AIProvider):
    name: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
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


def openai_provider(api_key: str, model: str, base_url: str = "https://api.openai.com/v1") -> OpenAICompatProvider:
    return OpenAICompatProvider(name="openai", base_url=base_url, api_key=api_key, model=model, requires_key=True)


def local_provider(model: str, base_url: str = "http://localhost:11434/v1") -> OpenAICompatProvider:
    return OpenAICompatProvider(name="local", base_url=base_url, api_key="", model=model, requires_key=False)
