from __future__ import annotations

import re
from typing import List

from pai.models import OfferAnalysis


KEYWORDS = {
    "commercial": ["commercial", "business develop", "bdr", "sales", "account manager", "key account", "vendeur", "vente", "prospection"],
    "marketing": ["marketing", "community manager", "brand", "growth", "digital", "performance marketing"],
    "recrutement": ["recrutement", "talent acquisition", "rh", "sourcer", "recruitment"],
    "relation_client": ["relation client", "customer success", "account management", "client", "service client"],
    "international": ["international", "export", "vie", "expatriation", "global account"],
}


def _tokenize(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\s-]", " ", (text or "").lower())


def _score_match(text: str, keywords: List[str]) -> int:
    normalized = _tokenize(text)
    return sum(1 for keyword in keywords if keyword in normalized)


def analyze_offer(offer_text: str, job_title: str = "", company: str = "", offer_url: str = "") -> OfferAnalysis:
    full_text = " ".join(part for part in [job_title, company, offer_text] if part)
    tokens = _tokenize(full_text)

    sector = "commercial"
    sector_score = 0
    for name, keywords in KEYWORDS.items():
        score = _score_match(full_text, keywords)
        if score > sector_score:
            sector_score = score
            sector = name

    must_have = []
    for keyword in ["prospection", "vente", "commercial", "client", "crm", "b2b", "sales", "relation client", "marketing", "recrutement"]:
        if keyword in tokens:
            must_have.append(keyword)

    strengths = [
        "Le profil présente une forte base en prospection commerciale et relation client.",
        "Le parcours montre des résultats concrets sur des missions de vente et de développement.",
        "Le candidat est pertinent pour des rôles terrain, B2B et relationnel.",
    ]

    risks = [
        "Le rôle peut nécessiter un contexte plus lourd en chiffres ou en suivi de KPI.",
        "Le secteur peut imposer une forte spécialisation secteur ou un réseau de marché spécifique."
    ]

    match_score = min(96, max(62, 72 + sector_score * 5))
    rec = "Positionnement recommandé : rôle commercial orienté client / business development avec angle résultats, relation client et portefeuille."

    return OfferAnalysis(
        job_title=job_title or "poste cible non renseigné",
        company=company or "entreprise non renseignée",
        sector=sector,
        match_score=round(match_score, 1),
        required_skills=[*sorted(set(must_have))],
        nice_to_have=[],
        strengths=strengths,
        risks=risks,
        recommendation=rec,
        offer_url=offer_url,
    )
