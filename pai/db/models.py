"""Schéma relationnel (section E). PostgreSQL 16 en production, SQLite accepté en local et en test.

Principes : contenu généré immuable et versionné (jamais écrasé), suppression douce (`deleted_at`),
provenance systématique. Les documents de l'interface PAI Studio (mode serveur) vivent dans
`store_documents` (magasin de documents JSON, même contrat que la capacité db de claude.ai).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Système ──────────────────────────────────────────────────────────────────
class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Déconnexion / changement de mot de passe : toute session émise avant cette date est refusée.
    sessions_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Job(TimestampMixin, Base):
    """File de travail adossée à la base : PENDING → RUNNING → DONE | FAILED (reprenable, idempotente)."""

    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    progress: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StoreDocument(Base):
    """Magasin de documents JSON de l'interface (contrat identique à la capacité db de claude.ai)."""

    __tablename__ = "store_documents"
    path: Mapped[str] = mapped_column(String(1000), primary_key=True)
    collection: Mapped[str] = mapped_column(String(1000), index=True, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AppSetting(Base):
    """Réglages modifiables depuis l'interface (clé → valeur JSON), ex. `ai` : fournisseur IA actif, modèles,
    URL de base et clés d'API CHIFFRÉES (Fernet dérivé de SECRET_KEY) — jamais de secret en clair."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StoredFile(TimestampMixin, Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    generation_id: Mapped[str | None] = mapped_column(ForeignKey("generations.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


# ── Profil ───────────────────────────────────────────────────────────────────
class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)


class ProfileVersion(TimestampMixin, Base):
    __tablename__ = "profile_versions"
    __table_args__ = (UniqueConstraint("candidate_id", "tag", name="uq_profile_version_tag"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    tag: Mapped[str] = mapped_column(String(60), nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FactRow(Base):
    """Miroir interrogeable des faits d'une version de profil (expériences, diplômes, langues… = faits typés)."""

    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_version_id: Mapped[int] = mapped_column(ForeignKey("profile_versions.id"), index=True, nullable=False)
    fact_key: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    provenance: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    parent_key: Mapped[str | None] = mapped_column(String(120))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


# ── Offres et analyses ────────────────────────────────────────────────────────
class OfferRow(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "offers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    text_hash: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(12), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    title_hint: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    company_hint: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)


class CompanySource(TimestampMixin, Base):
    __tablename__ = "company_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    info: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AnalysisRow(TimestampMixin, Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id"), nullable=False, index=True)
    engine_v: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    match: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON)


# ── Génération ──────────────────────────────────────────────────────────────
class Generation(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "generations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id"), nullable=False, index=True)
    profile_version_id: Mapped[int] = mapped_column(ForeignKey("profile_versions.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    versions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    risks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    next_action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cost_eur: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    log: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class LlmCall(TimestampMixin, Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str | None] = mapped_column(ForeignKey("generations.id"), index=True)
    task: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_tag: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    input_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_eur: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CvVersion(TimestampMixin, Base):
    __tablename__ = "cv_versions"
    __table_args__ = (UniqueConstraint("generation_id", "version", name="uq_cv_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"))


class LetterVersion(TimestampMixin, Base):
    __tablename__ = "letter_versions"
    __table_args__ = (UniqueConstraint("generation_id", "version", name="uq_letter_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"))


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), index=True, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)
    line_id: Mapped[str] = mapped_column(String(60), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    fact_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class Critique(TimestampMixin, Base):
    __tablename__ = "critiques"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AnswerSet(TimestampMixin, Base):
    __tablename__ = "answer_sets"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), nullable=False)
    answers: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class ApplicationPackRow(TimestampMixin, Base):
    __tablename__ = "application_packs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), unique=True, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    zip_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"))


# ── Évaluation et apprentissage ──────────────────────────────────────────────
class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str | None] = mapped_column(ForeignKey("generations.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(10), default="cv", nullable=False)
    element: Mapped[str] = mapped_column(String(40), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 👍, 0 😐, -1 👎
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ScoreEvent(TimestampMixin, Base):
    __tablename__ = "score_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), index=True, nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class ArenaVote(TimestampMixin, Base):
    __tablename__ = "arena_votes"
    id: Mapped[int] = mapped_column(primary_key=True)
    pair: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    choice: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    judge: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class BenchmarkCase(TimestampMixin, Base):
    __tablename__ = "benchmark_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)


class BenchmarkRun(TimestampMixin, Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    engine_v: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rows: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)


class RuleProposal(TimestampMixin, Base):
    __tablename__ = "rule_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="proposed", nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningPattern(TimestampMixin, Base):
    __tablename__ = "learning_patterns"
    id: Mapped[int] = mapped_column(primary_key=True)
    context: Mapped[str] = mapped_column(String(300), nullable=False)
    strategy: Mapped[str] = mapped_column(String(300), nullable=False)
    result: Mapped[str] = mapped_column(String(300), nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)


# ── JobAgent (lecture seule aujourd'hui) ─────────────────────────────────────
class LegacyItem(TimestampMixin, Base):
    __tablename__ = "legacy_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="REVIEW", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Outcome(TimestampMixin, Base):
    __tablename__ = "outcomes"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str | None] = mapped_column(ForeignKey("generations.id"))
    offer_ref: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)  # applied, answered, interview, offer, rejected…
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="api", nullable=False)
