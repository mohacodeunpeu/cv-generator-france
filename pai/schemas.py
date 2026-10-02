"""Modèles de données (Pydantic v2) partagés par le moteur, l'API et l'export.

Les mêmes formes JSON sont utilisées par PAI Studio (web/studio) : ne pas renommer
un champ sans mettre à jour les deux côtés.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FactStatus = Literal["CONFIRMED", "IMPORTED", "INFERRED", "UNVERIFIED", "FORBIDDEN"]
USABLE_STATUSES = ("CONFIRMED", "IMPORTED")
Priority = Literal["MUST", "IMPORTANT", "NICE", "UNKNOWN"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Loose(BaseModel):
    """Base tolérante pour les sorties IA : champs inconnus conservés."""

    model_config = ConfigDict(extra="allow")


# ── Profil ───────────────────────────────────────────────────────────────────

class Fact(BaseModel):
    id: str
    kind: str
    text: str
    data: dict[str, Any] = Field(default_factory=dict)
    status: FactStatus
    source: str
    provenance: str = ""
    confidence: float = 1.0
    parent: str | None = None
    terms: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False
    approved: bool = False
    note: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @property
    def usable(self) -> bool:
        return self.status in USABLE_STATUSES or (self.status == "INFERRED" and self.approved)


class ReviewItem(BaseModel):
    fact_id: str
    reason: str
    severity: Literal["info", "warning", "conflict"] = "warning"


class ProfileEvent(BaseModel):
    at: str = Field(default_factory=now_iso)
    action: str
    detail: str = ""


class MasterProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field("pai.master_profile/1", alias="schema")
    candidate_id: str
    version: int = 1
    validated: bool = False
    validated_at: str | None = None
    facts: list[Fact] = Field(default_factory=list)
    review_queue: list[ReviewItem] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    history: list[ProfileEvent] = Field(default_factory=list)

    # Accès pratiques
    def fact(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def by_kind(self, *kinds: str, usable_only: bool = True) -> list[Fact]:
        return [f for f in self.facts if f.kind in kinds and (f.usable or not usable_only)]

    def usable_facts(self) -> list[Fact]:
        return [f for f in self.facts if f.usable]

    def children(self, parent_id: str, usable_only: bool = True) -> list[Fact]:
        return [f for f in self.facts if f.parent == parent_id and (f.usable or not usable_only)]

    def experiences(self) -> list[Fact]:
        exps = self.by_kind("experience")
        return sorted(exps, key=lambda f: (f.data.get("start") or "0000"), reverse=True)

    def forbidden_terms(self) -> list[str]:
        terms: list[str] = []
        for f in self.facts:
            if f.status == "FORBIDDEN":
                terms.extend(f.terms or [f.text])
        return terms

    def value(self, fact_id: str, default: str = "") -> str:
        f = self.fact(fact_id)
        return f.text if f and f.usable else default

    @property
    def version_label(self) -> str:
        return f"v{self.version}"


# ── Offre et analyse ─────────────────────────────────────────────────────────

class Offer(BaseModel):
    id: str
    source_type: Literal["text", "url", "pdf", "html", "file", "fixture"] = "text"
    source_url: str = ""
    fetched_at: str = Field(default_factory=now_iso)
    title_hint: str = ""
    company_hint: str = ""
    text: str
    text_hash: str
    synthetic: bool = False


class Skill(Loose):
    name: str
    priority: Priority = "UNKNOWN"
    evidence: str = ""


class Keyword(Loose):
    term: str
    priority: Literal["REQUIRED", "IMPORTANT", "NICE"] = "IMPORTANT"


class Analysis(Loose):
    company: str = "UNKNOWN"
    job_title: str = "UNKNOWN"
    location: str = "UNKNOWN"
    country: str = "UNKNOWN"
    contract: str = "UNKNOWN"
    salary: dict[str, Any] = Field(default_factory=dict)
    seniority: str = "UNKNOWN"
    experience_years_min: float | None = None
    degree_required: str = "UNKNOWN"
    missions: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[dict[str, Any]] = Field(default_factory=list)
    remote: str = "UNKNOWN"
    travel: str = "UNKNOWN"
    schedule: str = "UNKNOWN"
    sector: str = "UNKNOWN"
    business_model: str = "UNKNOWN"
    benefits: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    hidden_risks: list[str] = Field(default_factory=list)
    freshness: str = "UNKNOWN"
    ats_guess: str = "UNKNOWN"
    recruiter_wants: dict[str, list[str]] = Field(default_factory=lambda: {"explicit": [], "inferred": []})
    keywords: list[Keyword] = Field(default_factory=list)
    language_of_offer: str = "fr"
    # Ajouts du moteur
    sector_id: str = "commercial"
    sector_scores: dict[str, float] = Field(default_factory=dict)
    source: Literal["deterministic", "ai+deterministic"] = "deterministic"


# ── Matching et stratégie ────────────────────────────────────────────────────

class KeywordCoverage(BaseModel):
    term: str
    priority: str
    covered: bool
    fact_ids: list[str] = Field(default_factory=list)
    via: str = ""


class Match(Loose):
    scores: dict[str, float] = Field(default_factory=dict)
    match: float = 0
    quality: float = 0
    risk: float = 0
    coverage: list[KeywordCoverage] = Field(default_factory=list)
    why_fit: list[dict[str, Any]] = Field(default_factory=list)
    why_not: list[dict[str, Any]] = Field(default_factory=list)
    missing: list[dict[str, Any]] = Field(default_factory=list)
    strengths: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)


class StrategyChoice(Loose):
    title: str
    hook: str = ""
    hook_fact_ids: list[str] = Field(default_factory=list)
    experiences_up: list[str] = Field(default_factory=list)
    experiences_down: list[str] = Field(default_factory=list)
    key_skill_fact_ids: list[str] = Field(default_factory=list)
    ats_mode: Literal["ATS_FIRST", "HUMAN_FIRST", "HYBRID"] = "HYBRID"
    design_profile: str = "hybrid_modern"
    photo_mode: Literal["OFF", "HEADER", "SIDEBAR"] = "OFF"
    letter_angle: str = ""
    channel: str = ""
    risks: list[str] = Field(default_factory=list)
    next_action: str = ""
    why: str = ""


class Strategy(Loose):
    options: list[dict[str, Any]] = Field(default_factory=list)
    comparison: str = ""
    chosen: str = "A"
    best: StrategyChoice
    source: str = "deterministic"


# ── Documents ────────────────────────────────────────────────────────────────

LineKind = Literal["headline", "claim", "fact", "offer_ref", "projection", "closing", "structure"]


class Line(BaseModel):
    id: str
    section: str
    kind: LineKind = "claim"
    text: str
    fact_ids: list[str] = Field(default_factory=list)
    offer_terms: list[str] = Field(default_factory=list)
    offer_quote: str = ""
    experience_id: str | None = None
    group: str | None = None


class ExperienceBlock(BaseModel):
    experience_id: str
    title: str
    company: str
    city: str = ""
    period: str = ""
    featured: bool = True
    bullet_ids: list[str] = Field(default_factory=list)


class CvDocument(BaseModel):
    version: int = 1
    language: str = "fr"
    design_profile: str = "hybrid_modern"
    photo_mode: str = "OFF"
    ats_mode: str = "HYBRID"
    paper: str = "A4"
    draft: bool = True
    name: str
    contact: list[str] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    experiences: list[ExperienceBlock] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=lambda: ["summary", "experience", "skills", "education", "languages"])
    section_titles: dict[str, str] = Field(default_factory=dict)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    keywords_covered: list[str] = Field(default_factory=list)
    removed_lines: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "deterministic"

    def line(self, line_id: str) -> Line | None:
        return next((ln for ln in self.lines if ln.id == line_id), None)

    def section_lines(self, section: str) -> list[Line]:
        return [ln for ln in self.lines if ln.section == section]


class LetterDocument(BaseModel):
    version: int = 1
    language: str = "fr"
    draft: bool = True
    place_date: str = ""
    recipient: str = ""
    subject: str = ""
    salutation: str = ""
    lines: list[Line] = Field(default_factory=list)       # sections : HOOK, WHY_ROLE, …
    paragraph_order: list[str] = Field(default_factory=lambda: ["HOOK", "WHY_ROLE", "WHY_COMPANY", "PROOF", "VALUE", "CLOSE"])
    signature: str = ""
    removed_lines: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "deterministic"


class Answer(Loose):
    question: str
    type: str = "OPEN"
    answer: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    confidence: Literal["HIGH", "MEDIUM", "LOW", "BLOCKED"] = "BLOCKED"
    ask_user: str = ""


# ── Validation, critique, pack ───────────────────────────────────────────────

class LineVerdict(BaseModel):
    line_id: str
    ok: bool
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    forbidden: bool = False
    exaggeration: bool = False


class ValidationReport(BaseModel):
    verdicts: list[LineVerdict] = Field(default_factory=list)
    total: int = 0
    traced: int = 0
    factuality: float = 0.0
    forbidden_hits: int = 0
    rejected_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def perfect(self) -> bool:
        return self.total > 0 and self.traced == self.total and self.forbidden_hits == 0


class Versions(BaseModel):
    application_id: str = ""     # même offre = même candidature (plusieurs versions possibles)
    offer_v: str
    profile_v: str
    analysis_v: str = ""
    template: str = ""
    cv_v: str = ""
    letter_v: str = ""
    answers_v: str = ""
    engine_v: str
    prompt_v: str
    rules_v: str
    timestamp: str = Field(default_factory=now_iso)


class ApplicationPack(BaseModel):
    id: str
    mode: Literal["QUICK", "STANDARD", "DEEP"] = "STANDARD"
    status: Literal["DRAFT", "FINAL", "FAILED"] = "DRAFT"
    created_at: str = Field(default_factory=now_iso)
    provider: str = "null"
    versions: Versions
    offer: Offer
    analysis: Analysis
    match: Match
    strategy: Strategy
    cv: CvDocument | None = None
    letter: LetterDocument | None = None
    answers: list[Answer] = Field(default_factory=list)
    validation: dict[str, ValidationReport] = Field(default_factory=dict)
    critique: dict[str, Any] = Field(default_factory=dict)
    pdf_qa: dict[str, Any] = Field(default_factory=dict)
    scores: dict[str, Any] = Field(default_factory=dict)
    ats: dict[str, Any] = Field(default_factory=dict)      # Score PAI, dimensions, exigences prouvées, changements
    risks: list[str] = Field(default_factory=list)
    next_action: str = ""
    missing_profile_data: list[str] = Field(default_factory=list)
    log: list[dict[str, Any]] = Field(default_factory=list)
    cost_eur: float = 0.0
