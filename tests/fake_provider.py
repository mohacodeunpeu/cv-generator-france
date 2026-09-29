"""Fournisseur IA enregistré (tests déterministes, gratuits, hors ligne).

Réponses SYNTHETIC calquées sur tests/e2e/claude_mock.js (même profil fictif, mêmes pièges) :
une ligne « MBA », un faux chiffre « 40+ », un fait UNVERIFIED et un salaire inventé.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pai.providers.base import AIProvider, ProviderResult


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i + len(start): j if j >= 0 else None]


@dataclass
class FakeProvider(AIProvider):
    name: str = "fake"
    seen: list[str] = field(default_factory=list)
    price_per_call: float = 0.01

    def model_for(self, task: str) -> str:
        return f"fake-{task}"

    def _complete(self, task: str, prompt_text: str, images: list[bytes] | None = None) -> ProviderResult:
        self.seen.append(task)
        return ProviderResult(text=json.dumps(self.respond(task, prompt_text), ensure_ascii=False), model=self.model_for(task),
                              tokens_in=len(prompt_text) // 4, tokens_out=200, cost_eur=self.price_per_call)

    def respond(self, task: str, prompt: str) -> dict:
        if task == "analyze_offer":
            return {"company": "Acme SaaS", "job_title": "Business Developer Junior", "contract": "CDI",
                    "missions": ["Prospecter de nouveaux clients PME par téléphone et LinkedIn.", "Suivre votre pipeline dans HubSpot."],
                    "keywords": [{"term": "prospection", "priority": "REQUIRED"}, {"term": "CRM", "priority": "REQUIRED"},
                                 {"term": "anglais", "priority": "REQUIRED"}, {"term": "HubSpot", "priority": "IMPORTANT"}],
                    "recruiter_wants": {"explicit": ["Prospection outbound de PME"], "inferred": ["Volume d'appels (déduit)"]}}
        if task == "match":
            return {"why_fit": [{"text": "Prospection B2B prouvée", "fact_ids": ["exp.alpha.t1"]}], "missing": [], "risks": []}
        if task == "strategy":
            best = {"title": "Business Developer Junior", "hook": "25+ leads qualifiés/mois", "hook_fact_ids": ["exp.alpha.r2"],
                    "experiences_up": ["exp.alpha", "exp.beta", "exp.inconnue"], "experiences_down": ["exp.gamma"],
                    "key_skill_fact_ids": ["tool.hubspot"], "ats_mode": "HYBRID", "design_profile": "hybrid_modern", "photo_mode": "HEADER"}
            return {"options": [dict(best, key="A", angle="ATS")], "comparison": "A", "chosen": "A", "best": best}
        if task == "cv_content":
            return {"headline": {"text": "Business Developer Junior", "fact_ids": ["target.roles"], "offer_terms": ["Business Developer Junior"]},
                    "summary": [{"text": "Business Developer B2B : prospection, négociation avec les décideurs et suivi sous HubSpot.",
                                 "fact_ids": ["exp.alpha.t1", "exp.alpha.t2", "exp.alpha.t3"]},
                                {"text": "40+ leads qualifiés par mois.", "fact_ids": ["exp.alpha.r2"]}],
                    "experiences": [{"experience_id": "exp.alpha", "bullets": [
                        {"text": "25+ leads qualifiés par mois grâce à LinkedIn Sales Navigator", "fact_ids": ["exp.alpha.r2", "exp.alpha.t3"]},
                        {"text": "Titulaire d'un MBA en stratégie commerciale", "fact_ids": ["edu.bachelor"]},
                        {"text": "Négociation directe avec les décideurs", "fact_ids": ["exp.alpha.t2"]}]},
                        {"experience_id": "exp.beta", "bullets": [{"text": "+12 % vs objectif mensuel", "fact_ids": ["exp.beta.r1"]}]}],
                    "skills": [{"group": "Outils", "items": [{"label": "HubSpot", "fact_ids": ["tool.hubspot"]}]}],
                    "education_ids": ["edu.bachelor", "edu.unverified"], "language_ids": ["lang.fr", "lang.en"]}
        if task == "cv_fix":
            raw = _between(prompt, "LIGNES À CORRIGER (id, texte, raisons du rejet, faits cités) :\n", "\nFAITS AUTORISÉS")
            items = json.loads(raw) if raw.strip() else []
            out = []
            for it in items:
                if re.search("MBA", it["text"], re.I):
                    out.append({"id": it["id"], "text": "", "fact_ids": []})
                elif "40+" in it["text"]:
                    out.append({"id": it["id"], "text": "25+ leads qualifiés par mois.", "fact_ids": ["exp.alpha.r2"]})
                else:
                    out.append({"id": it["id"], "text": it["text"], "fact_ids": it["fact_ids"]})
            return {"lines": out}
        if task == "factuality_judge":
            return {"verdicts": []}
        if task == "critique":
            return {"scores": {k: {"score": 8, "why": "ok"} for k in ("RECRUITER", "HIRING_MANAGER", "ATS", "DESIGN", "FACTUALITY", "MATCH", "SECTOR")},
                    "issues": [], "ten_second": {"verdict": "PASS"}}
        if task == "letter":
            return {"subject": "Objet : candidature au poste de Business Developer Junior", "salutation": "Madame, Monsieur,", "paragraphs": [
                {"role": "HOOK", "sentences": [{"text": "Votre annonce demande de « prospecter de nouveaux clients PME par téléphone et LinkedIn ».",
                                                "kind": "offer_ref", "offer_quote": "Prospecter de nouveaux clients PME par téléphone et LinkedIn"}]},
                {"role": "WHY_COMPANY", "sentences": [{"text": "Acme SaaS édite un logiciel pour les PME françaises.", "kind": "offer_ref",
                                                       "offer_quote": "Acme SaaS édite un logiciel pour les PME françaises"}]},
                {"role": "PROOF", "sentences": [{"text": "Chez Alpha Services, je génère 25+ leads qualifiés par mois.", "kind": "claim", "fact_ids": ["exp.alpha.r2"]},
                                                {"text": "J'ai dirigé une équipe de 6 commerciaux.", "kind": "claim", "fact_ids": ["exp.alpha.t1"]}]},
                {"role": "CLOSE", "sentences": [{"text": "Disponible immédiatement, je serais heureux d'échanger avec vous.", "kind": "claim",
                                                 "fact_ids": ["avail.immediate"]}]}]}
        if task == "answers":
            return {"answers": [{"question": "Quelles sont vos prétentions salariales ?", "type": "SALARY", "answer": "45 k€", "fact_ids": [], "confidence": "HIGH"}]}
        return {}
