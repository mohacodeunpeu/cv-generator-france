"""Fournisseur local Ollama (API native) : gratuit, hors ligne, aucune clé.

Pourquoi l'API native plutôt que /v1/chat/completions : `format: "json"` contraint la sortie (les petits modèles
rendent enfin un JSON valide), les compteurs de jetons et les durées sont exacts, `think: false` coupe le
raisonnement caché des modèles hybrides, et `/api/embed` donne les embeddings de la correspondance sémantique.

Choix du modèle (du plus prioritaire au moins prioritaire) : réglage explicite (AI_MODEL / LOCAL_MODEL /
Réglages → IA) → choix mesuré par `python -m pai ai setup` (data/ai/local_selection.json) → meilleur candidat
installé du registre (config/local_models.yaml). Si Ollama est éteint ou si aucun modèle n'est installé,
`available` est faux : PAI passe en mode « sans IA », jamais en erreur.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .. import paths
from .base import AIProvider, ProviderError, ProviderResult

DEFAULT_BASE_URL = "http://localhost:11434"
_THINK = re.compile(r"<think>.*?</think>\s*", re.S)
_probe_lock = threading.Lock()
_probe_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def normalize_base_url(url: str) -> str:
    """Accepte l'ancienne forme compatible OpenAI (…:11434/v1) et rend la racine de l'API native."""
    url = (url or DEFAULT_BASE_URL).strip().rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def probe(base_url: str, ttl: float = 30.0, timeout: float = 2.0) -> dict[str, Any]:
    """État d'Ollama (joignable, version, modèles installés), mis en cache `ttl` secondes : une panne coûte
    au plus un délai court, puis PAI continue sans IA."""
    base_url = normalize_base_url(base_url)
    now = time.monotonic()
    with _probe_lock:
        hit = _probe_cache.get(base_url)
        if hit and now - hit[0] < ttl:
            return hit[1]
    state: dict[str, Any] = {"reachable": False, "version": "", "models": [], "error": ""}
    try:
        with httpx.Client(timeout=timeout) as c:
            state["version"] = c.get(f"{base_url}/api/version").json().get("version", "")
            tags = c.get(f"{base_url}/api/tags").json().get("models", [])
        state["models"] = [{"name": m.get("name", ""), "size_gb": round(int(m.get("size", 0)) / 1e9, 2),
                            "family": (m.get("details") or {}).get("family", ""),
                            "quantization": (m.get("details") or {}).get("quantization_level", "")} for m in tags]
        state["reachable"] = True
    except (httpx.HTTPError, ValueError) as exc:
        state["error"] = f"Ollama injoignable ({exc.__class__.__name__})"
    with _probe_lock:
        _probe_cache[base_url] = (now, state)
    return state


def reset_probe_cache() -> None:
    with _probe_lock:
        _probe_cache.clear()


def load_selection() -> dict[str, str]:
    """Choix mesuré par `python -m pai ai setup` : {"small": nom, "large": nom, "embed": nom}."""
    path = paths.DATA_DIR / "ai" / "local_selection.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in (data.get("selection") or {}).items() if v}
    except (OSError, ValueError):
        return {}


def installed_names(state: dict[str, Any]) -> set[str]:
    names = set()
    for m in state.get("models", []):
        n = m.get("name", "")
        names.add(n)
        if n.endswith(":latest"):
            names.add(n[: -len(":latest")])
    return names


def resolve_model(tier: str, explicit: str, state: dict[str, Any]) -> str:
    """Nom du modèle à utiliser pour un niveau, parmi ceux réellement installés ('' si aucun)."""
    from ..ai.registry import candidates

    names = installed_names(state)
    if explicit:
        return explicit if (explicit in names or not state.get("reachable")) else ""
    chosen = load_selection().get(tier, "")
    if chosen and chosen in names:
        return chosen
    ranked = sorted((c for c in candidates() if tier in c.tiers), key=lambda c: c.prior)
    for c in ranked:
        for name in (c.ollama, c.id, c.ollama.split(":")[0]):
            if name in names:
                return name
    return ""


@dataclass
class OllamaProvider(AIProvider):
    name: str = "local"
    base_url: str = DEFAULT_BASE_URL
    model: str = ""            # modèle explicite (vide = choix automatique)
    tier: str = "large"        # small | large (une instance par niveau, voir pai.ai.router)
    keep_alive: str = "15m"
    timeout_scale: float = 1.0
    _resolved: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self.base_url = normalize_base_url(self.base_url)

    # -- état -------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        return probe(self.base_url)

    @property
    def available(self) -> bool:
        return bool(self.state().get("reachable")) and bool(self.resolved_model())

    def resolved_model(self) -> str:
        self._resolved = resolve_model(self.tier, self.model, self.state())
        return self._resolved

    def model_for(self, task: str) -> str:
        return self._resolved or self.resolved_model() or self.model or "local"

    def config_fingerprint(self, task: str) -> str:
        from ..ai.registry import task_params

        p = task_params(task)
        return f"ctx{p.get('num_ctx')}-t{p.get('temperature')}-n{p.get('max_tokens')}"

    # -- appels -----------------------------------------------------------------
    def _think_flag(self, model: str) -> bool | None:
        from ..ai.registry import by_installed_name

        c = by_installed_name(model)
        return c.think if c is not None else None

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:
        import base64

        from ..ai.registry import task_params

        model = self.model_for(task)
        if not model or model == "local":
            raise ProviderError("local : aucun modèle local installé (python -m pai ai setup)")
        p = task_params(task)
        message: dict[str, Any] = {"role": "user", "content": prompt_text}
        if images:
            message["images"] = [base64.b64encode(i).decode("ascii") for i in images]
        payload: dict[str, Any] = {
            "model": model, "messages": [message], "stream": False, "keep_alive": self.keep_alive,
            "options": {"temperature": float(p.get("temperature", 0.2)), "num_ctx": int(p.get("num_ctx", 4096)),
                        "num_predict": int(p.get("max_tokens", 800))}}
        if "json" in prompt_text.lower():
            payload["format"] = "json"
        if self._think_flag(model) is False:
            payload["think"] = False
        timeout = float(p.get("timeout_s", 240)) * self.timeout_scale
        start = time.monotonic()
        try:
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=httpx.Timeout(timeout, connect=5.0))
            if resp.status_code == 400 and "think" in payload and "think" in resp.text.lower():
                payload.pop("think")   # version d'Ollama ou modèle sans prise en charge du paramètre
                resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=httpx.Timeout(timeout, connect=5.0))
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            hint = {404: "modèle absent : python -m pai ai setup"}.get(code, "service local en erreur" if code >= 500 else "requête refusée")
            raise ProviderError(f"local : HTTP {code} ({hint})") from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(f"local : délai de réponse dépassé ({timeout:.0f} s)") from exc
        except httpx.HTTPError as exc:
            reset_probe_cache()
            raise ProviderError(f"local : Ollama injoignable ({exc.__class__.__name__})") from exc
        text = _THINK.sub("", ((data.get("message") or {}).get("content") or "")).strip()
        return ProviderResult(text=text, model=model, tokens_in=int(data.get("prompt_eval_count") or 0),
                              tokens_out=int(data.get("eval_count") or 0), cost_eur=0.0,
                              latency_ms=int((time.monotonic() - start) * 1000))

    def embed(self, texts: list[str], model: str = "") -> list[list[float]]:
        """Embeddings (correspondance sémantique). Lève ProviderError si indisponible : l'appelant garde sa voie
        déterministe (taxonomie, racines, proximité lexicale)."""
        model = model or resolve_model("embed", "", self.state())
        if not model:
            raise ProviderError("local : aucun modèle d'embeddings installé")
        try:
            resp = httpx.post(f"{self.base_url}/api/embed", json={"model": model, "input": texts, "keep_alive": self.keep_alive},
                              timeout=httpx.Timeout(120.0, connect=5.0))
            resp.raise_for_status()
            vectors = resp.json().get("embeddings") or []
        except httpx.HTTPError as exc:
            raise ProviderError(f"local : embeddings indisponibles ({exc.__class__.__name__})") from exc
        if len(vectors) != len(texts):
            raise ProviderError("local : réponse d'embeddings incomplète")
        return vectors


def ollama_provider(model: str = "", base_url: str = DEFAULT_BASE_URL, tier: str = "large") -> OllamaProvider:
    return OllamaProvider(name="local", base_url=base_url, model=model, tier=tier)
