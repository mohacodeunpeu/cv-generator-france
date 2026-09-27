from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class Fact(BaseModel):
    fact_id: str
    label: str
    value: str
    source: str = "user_profile"
    status: str = "CONFIRMED"


class Experience(BaseModel):
    title: str
    company: str
    period: str
    summary: str
    results: List[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    candidate_name: str
    email: str
    phone: str
    city: str
    target_roles: List[str] = Field(default_factory=list)
    experiences: List[Experience] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    version: str = "v1"
    status: str = "BROUILLON"


class OfferAnalysis(BaseModel):
    job_title: str
    company: str
    sector: str
    match_score: float
    required_skills: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommendation: str
    offer_url: str = ""


class Strategy(BaseModel):
    positioning: str
    ats_mode: str
    retention_hook: str
    primary_experiences: List[str] = Field(default_factory=list)
    secondary_experiences: List[str] = Field(default_factory=list)
    key_skills: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    next_action: str
