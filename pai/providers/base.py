"""Interface fournisseur IA (section F). Aucun module métier n'importe un SDK de fournisseur.

Chaque tâche rend un prompt versionné (prompts/*.md), appelle le fournisseur, extrait le JSON,
le valide (Pydantic si un modèle est fourni) et réessaie 2 fois avant un échec propre.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from ..rules import load_rules, prompt

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """Échec propre d'un appel IA (l'opération passe en FAILED ou bascule en déterministe)."""


class DegradedMode(ProviderError):
    """Aucun fournisseur IA disponible : le pipeline utilise les voies déterministes."""


class BudgetExceeded(ProviderError):
    """Plafond de coût atteint (par pack ou par jour)."""


@dataclass
class CallRecord:
    task: str
    provider: str
    model: str
    prompt_tag: str
    input_hash: str
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_eur: float = 0.0
    cached: bool = False
    ok: bool = True
    error: str = ""
    tier: str = ""          # small | large | external (routeur)


@dataclass
class ProviderResult:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_eur: float = 0.0
    latency_ms: int = 0
    cached: bool = False


def extract_json(text: str) -> Any:
    """Lecture tolérante : JSON brut, bloc ```json```, ou du premier { / [ au dernier } / ]."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if starts:
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("Aucun JSON valide dans la réponse")


@dataclass
class AIProvider:
    """Base commune. Les sous-classes implémentent `_complete`."""

    name: str = "base"
    calls: list[CallRecord] = field(default_factory=list)
    budget_eur: float | None = None
    on_call: Callable[[CallRecord], None] | None = None

    @property
    def available(self) -> bool:
        return True

    # -- à implémenter -------------------------------------------------------
    def model_for(self, task: str) -> str:
        return "unknown"

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:
        raise NotImplementedError

    # -- commun ---------------------------------------------------------------
    @property
    def spent_eur(self) -> float:
        return round(sum(c.cost_eur for c in self.calls), 4)

    def complete(self, task: str, prompt_text: str, prompt_tag: str = "", images: list[bytes] | None = None) -> ProviderResult:
        from ..textnorm import stable_hash

        if not self.available:
            raise DegradedMode(f"Fournisseur « {self.name} » indisponible")
        if self.budget_eur is not None and self.spent_eur >= self.budget_eur:
            raise BudgetExceeded(f"Plafond atteint ({self.spent_eur:.2f} € ≥ {self.budget_eur:.2f} €)")
        record = CallRecord(task=task, provider=self.name, model=self.model_for(task), prompt_tag=prompt_tag,
                            input_hash=stable_hash(prompt_text, 16))
        start = time.monotonic()
        try:
            result = self._complete(task, prompt_text, images)
        except ProviderError:
            record.ok, record.error = False, "provider_error"
            self._record(record, start)
            raise
        except Exception as exc:  # noqa: BLE001 — toute erreur SDK devient un échec propre
            record.ok, record.error = False, f"{exc.__class__.__name__}: {str(exc)[:200]}"
            self._record(record, start)
            raise ProviderError(record.error) from exc
        record.model, record.tokens_in, record.tokens_out = result.model, result.tokens_in, result.tokens_out
        record.cost_eur, record.cached = result.cost_eur, result.cached
        self._record(record, start, result.latency_ms)
        return result

    def _record(self, record: CallRecord, start: float, latency_ms: int = 0) -> None:
        from ..obs import event, tier_var

        record.latency_ms = latency_ms or int((time.monotonic() - start) * 1000)
        record.tier = record.tier or tier_var.get()
        self.calls.append(record)
        event("ai_call", task=record.task, provider=record.provider, model=record.model, tier=record.tier,
              cache_hit=record.cached, success=record.ok, duration_ms=record.latency_ms, error=record.error)
        if self.on_call:
            self.on_call(record)

    def json(self, task: str, prompt_name: str, variables: dict[str, Any], schema: type[T] | None = None,
             images: list[bytes] | None = None) -> Any:
        """Rend le prompt, appelle, parse et valide ; 2 nouvelles tentatives puis ProviderError."""
        tpl = prompt(prompt_name)
        text = tpl.render(**variables)
        retries = int(load_rules().models.get("generation", {}).get("max_retries", 2))
        last_error = ""
        for attempt in range(retries + 1):
            suffix = "" if attempt == 0 else (
                f"\n\nTa réponse précédente était invalide ({last_error}). Réponds UNIQUEMENT par le JSON demandé, complet.")
            result = self.complete(task, text + suffix, prompt_tag=tpl.tag, images=images)
            try:
                data = extract_json(result.text)
                if schema is not None:
                    return schema.model_validate(data)
                return data
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:300]
        raise ProviderError(f"Sortie JSON invalide pour {task} après {retries + 1} essais : {last_error}")

    # -- tâches (interface section F) -------------------------------------------
    def analyze_offer(self, **v: Any) -> dict[str, Any]:
        return self.json("analyze_offer", "analyze_offer", v)

    def analyze_company(self, **v: Any) -> dict[str, Any]:
        return self.json("analyze_company", "analyze_company", v)

    def analyze_profile_match(self, **v: Any) -> dict[str, Any]:
        return self.json("match", "match", v)

    def generate_strategy(self, **v: Any) -> dict[str, Any]:
        return self.json("strategy", "strategy", v)

    def generate_cv_content(self, **v: Any) -> dict[str, Any]:
        return self.json("cv_content", "cv_content", v)

    def fix_lines(self, **v: Any) -> dict[str, Any]:
        return self.json("cv_fix", "cv_fix", v)

    def generate_letter(self, **v: Any) -> dict[str, Any]:
        return self.json("letter", "letter", v)

    def critique_document(self, **v: Any) -> dict[str, Any]:
        return self.json("critique", "critique", v)

    def judge_factuality(self, **v: Any) -> dict[str, Any]:
        return self.json("factuality_judge", "factuality_judge", v)

    def answer_question(self, **v: Any) -> dict[str, Any]:
        return self.json("answers", "answers", v)

    def judge_pair(self, **v: Any) -> dict[str, Any]:
        return self.json("judge_pair", "judge_pair", v)

    def judge_visual(self, png: bytes, **v: Any) -> dict[str, Any]:
        return self.json("judge_visual", "judge_visual", v, images=[png])

    def propose_rules(self, **v: Any) -> dict[str, Any]:
        return self.json("learning_rules", "learning_rules", v)
