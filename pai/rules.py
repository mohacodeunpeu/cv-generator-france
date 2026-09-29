"""Chargement des règles versionnées (YAML) et des prompts, avec leurs empreintes de version.

Tout ce qui change le comportement du moteur sans toucher au code vit ici :
/rules, /sector_profiles, /design_profiles, /brand, /prompts, /config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import paths
from .textnorm import contains_term, norm, stable_hash


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _dir_hash(*dirs: Path) -> str:
    chunks: list[str] = []
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in {".yaml", ".yml", ".md"}:
                chunks.append(p.relative_to(paths.ROOT).as_posix())
                chunks.append(p.read_text(encoding="utf-8"))
    return stable_hash("\n".join(chunks), 10)


# ── Équivalences de compétences ──────────────────────────────────────────────

@dataclass
class Synonyms:
    groups: list[list[str]] = field(default_factory=list)
    implies: dict[str, list[str]] = field(default_factory=dict)

    def equivalents(self, term: str) -> set[str]:
        t = norm(term)
        out = {t}
        for group in self.groups:
            normed = [norm(g) for g in group]
            if t in normed:
                out.update(normed)
        return out

    def supported_by(self, term: str, evidence_norm: str) -> str | None:
        """Retourne la voie de preuve ('direct', 'synonyme', 'implique') si `term` est justifié par le texte."""
        if contains_term(evidence_norm, term):
            return "direct"
        for eq in self.equivalents(term):
            if eq != norm(term) and contains_term(evidence_norm, eq):
                return "synonyme"
        target = norm(term)
        targets = self.equivalents(term)
        for key, implied in self.implies.items():
            implied_n = {norm(x) for x in implied}
            if (target in implied_n or targets & implied_n) and contains_term(evidence_norm, key):
                return "implique"
        return None


# ── Règles regroupées ────────────────────────────────────────────────────────

@dataclass
class RuleSet:
    banned_hard: list[str]
    banned_soft: list[str]
    synonyms: Synonyms
    scoring: dict[str, Any]
    countries: dict[str, dict[str, Any]]
    sectors: dict[str, dict[str, Any]]
    designs: dict[str, dict[str, Any]]
    brand: dict[str, Any]
    models: dict[str, Any]
    version: str

    # Pays
    def country(self, code: str | None) -> dict[str, Any]:
        key = (code or "").upper()
        for c in self.countries.values():
            if c.get("code", "").upper() == key:
                return c
        return self.countries.get("_default", {})

    def sector(self, sector_id: str | None) -> dict[str, Any]:
        return self.sectors.get(sector_id or "", self.sectors.get("commercial", {}))

    def design(self, design_id: str | None) -> dict[str, Any]:
        return self.designs.get(design_id or "", self.designs.get("hybrid_modern", {}))

    def banned_found(self, text: str) -> tuple[list[str], list[str]]:
        t = norm(text)
        hard = [p for p in self.banned_hard if norm(p) and norm(p) in t]
        soft = [p for p in self.banned_soft if norm(p) and norm(p) in t]
        return hard, soft


@lru_cache(maxsize=1)
def load_rules() -> RuleSet:
    banned = _load_yaml(paths.RULES_DIR / "banned_phrases.yaml")
    hard = [p for lang in (banned.get("hard") or {}).values() for p in lang]
    soft = [p for lang in (banned.get("soft") or {}).values() for p in lang]
    syn_raw = _load_yaml(paths.RULES_DIR / "skill_synonyms.yaml")
    synonyms = Synonyms(groups=syn_raw.get("equivalents") or [], implies=syn_raw.get("implies") or {})
    countries = {p.stem: _load_yaml(p) for p in sorted(paths.COUNTRY_DIR.glob("*.yaml"))}
    sectors = {}
    for p in sorted(paths.SECTOR_DIR.glob("*.yaml")):
        data = _load_yaml(p)
        sectors[data.get("id", p.stem)] = data
    designs = {}
    for p in sorted(paths.DESIGN_DIR.glob("*.yaml")):
        data = _load_yaml(p)
        designs[data.get("id", p.stem)] = data
    brand = _load_yaml(paths.BRAND_DIR / "brand.yaml")
    models = _load_yaml(paths.CONFIG_DIR / "models.yaml")
    scoring = _load_yaml(paths.RULES_DIR / "scoring.yaml")
    version = _dir_hash(paths.RULES_DIR, paths.SECTOR_DIR, paths.DESIGN_DIR, paths.BRAND_DIR, paths.CONFIG_DIR)
    return RuleSet(hard, soft, synonyms, scoring, countries, sectors, designs, brand, models, version)


def reload_rules() -> RuleSet:
    load_rules.cache_clear()
    load_prompts.cache_clear()
    return load_rules()


# ── Prompts versionnés ───────────────────────────────────────────────────────

_PROMPT_HEADER = re.compile(r"<!--\s*prompt:\s*(?P<name>[\w-]+)\s*\|\s*version:\s*(?P<version>\d+)\s*-->")


@dataclass
class Prompt:
    name: str
    version: int
    template: str

    @property
    def tag(self) -> str:
        return f"{self.name}@v{self.version}"

    def render(self, **variables: Any) -> str:
        text = self.template
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", value if isinstance(value, str) else str(value))
        leftovers = re.findall(r"\{\{(\w+)\}\}", text)
        if leftovers:
            raise KeyError(f"Variables manquantes pour le prompt {self.tag} : {sorted(set(leftovers))}")
        return text


@lru_cache(maxsize=1)
def load_prompts() -> dict[str, Prompt]:
    prompts: dict[str, Prompt] = {}
    for p in sorted(paths.PROMPTS_DIR.glob("*.md")):
        raw = p.read_text(encoding="utf-8")
        m = _PROMPT_HEADER.search(raw)
        if not m:
            raise ValueError(f"En-tête de version manquant dans {p}")
        body = raw[m.end():].lstrip("\n")
        prompts[m.group("name")] = Prompt(m.group("name"), int(m.group("version")), body)
    return prompts


def prompt(name: str) -> Prompt:
    return load_prompts()[name]


def prompts_version() -> str:
    return stable_hash({n: p.version for n, p in load_prompts().items()}, 8)


def truth_rules(forbidden_terms: list[str]) -> str:
    terms = ", ".join(f"« {t} »" for t in forbidden_terms) if forbidden_terms else "aucun"
    return prompt("_truth_rules").render(forbidden_terms=terms)
