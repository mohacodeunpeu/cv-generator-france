"""ClaudeProvider (fournisseur par défaut) — SDK officiel `anthropic`.

Modèles par tâche : config/models.yaml. Opus 5.5 et Sonnet 5 n'acceptent ni `temperature`
ni la désactivation de la réflexion : on règle `output_config.effort` à la place.
Streaming systématique (sorties longues sans délai d'expiration HTTP).
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

from ..rules import load_rules
from .base import AIProvider, ProviderError, ProviderResult


@dataclass
class ClaudeProvider(AIProvider):
    name: str = "claude"
    api_key: str = field(default="", repr=False)
    model: str = ""   # modèle unique imposé depuis Réglages → IA ; vide = modèle par tâche (config/models.yaml)
    _client: Any = field(default=None, repr=False)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _cfg(self) -> dict[str, Any]:
        return load_rules().models.get("providers", {}).get("claude", {})

    def model_for(self, task: str) -> str:
        if self.model:
            return self.model
        tasks = self._cfg().get("tasks", {})
        return tasks.get(task) or tasks.get("cv_content") or "claude-sonnet-5"

    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key, max_retries=2, timeout=300.0)
        return self._client

    def _price(self, model: str, tokens_in: int, tokens_out: int) -> float:
        cfg = load_rules().models
        pricing = self._cfg().get("pricing_usd_per_mtok", {}).get(model, {"input": 5.0, "output": 25.0})
        usd = tokens_in / 1e6 * pricing["input"] + tokens_out / 1e6 * pricing["output"]
        return round(usd * float(cfg.get("cost_guard", {}).get("usd_to_eur", 0.92)), 5)

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:
        import anthropic

        model = self.model_for(task)
        caps = self._cfg().get("capabilities", {}).get(model, {})
        gen = load_rules().models.get("generation", {})
        max_tokens = int(gen.get("max_tokens", {}).get(task, gen.get("max_tokens", {}).get("default", 4000)))
        content: list[dict[str, Any]] = []
        for img in images or []:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.b64encode(img).decode("ascii")}})
        content.append({"type": "text", "text": prompt_text})
        params: dict[str, Any] = {"model": model, "max_tokens": max(max_tokens, 32000),
                                  "messages": [{"role": "user", "content": content}]}
        if caps.get("thinking") == "adaptive":
            params["thinking"] = {"type": "adaptive"}
        if caps.get("effort"):
            effort = self._cfg().get("effort_by_task", {}).get(task, "medium")
            params["output_config"] = {"effort": effort}
        if caps.get("temperature"):
            params["temperature"] = float(gen.get("temperature", 0.2))
        start = time.monotonic()
        try:
            with self.client().messages.stream(**params) as stream:
                message = stream.get_final_message()
        except anthropic.RateLimitError as exc:
            raise ProviderError(f"Limite de débit Anthropic atteinte : {exc.message}") from exc
        except anthropic.AuthenticationError as exc:
            raise ProviderError("Clé d'API Anthropic refusée (ANTHROPIC_API_KEY ou Réglages → IA)") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Erreur API Anthropic {exc.status_code} : {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Connexion à l'API Anthropic impossible") from exc
        if message.stop_reason == "refusal":
            raise ProviderError("Requête refusée par le modèle (stop_reason=refusal)")
        if message.stop_reason == "max_tokens":
            raise ProviderError("Réponse tronquée (max_tokens)")
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        return ProviderResult(text=text, model=model, tokens_in=usage.input_tokens, tokens_out=usage.output_tokens,
                              cost_eur=self._price(model, usage.input_tokens, usage.output_tokens),
                              latency_ms=int((time.monotonic() - start) * 1000))
