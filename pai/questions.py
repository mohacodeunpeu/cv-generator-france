"""Réponses aux questions de candidature. BLOCKED = on demande à l'utilisateur, on n'invente jamais."""

from __future__ import annotations

import re

from .schemas import Answer, MasterProfile
from .textnorm import norm

_ROUTES = [
    ("SALARY", r"salaire|remuneration|pretention|package|salary|compensation"),
    ("AVAILABILITY", r"disponib|date de debut|quand pouvez|start date|notice|preavis"),
    ("LANGUAGE", r"langue|anglais|espagnol|arabe|english|spanish|arabic|toeic|language"),
    ("ADMIN", r"permis|nationalit|visa|titre de sejour|age|handicap|rqth|work permit|driving|mobilit|demenag|relocat"),
    ("EXPERIENCE", r"experience|parcours|realisation|exemple|situation|projet|resultat|achievement"),
    ("VALUES", r"valeur|ethique|pourquoi nous|why us|culture"),
    ("PERSONALITY", r"qualit|defaut|personnalit|strength|weakness|decri"),
    ("FACTUAL", r"diplome|formation|ecole|degree|education|certif"),
]


def classify(question: str) -> str:
    q = norm(question)
    for qtype, pattern in _ROUTES:
        if re.search(pattern, q):
            return qtype
    return "OPEN"


def answer_deterministic(question: str, profile: MasterProfile) -> Answer:
    qtype = classify(question)
    q = norm(question)
    if qtype == "AVAILABILITY" and profile.fact("avail.immediate"):
        return Answer(question=question, type=qtype, answer=profile.value("avail.immediate") + ".",
                      fact_ids=["avail.immediate"], confidence="HIGH")
    if qtype == "LANGUAGE":
        facts = profile.by_kind("language")
        wanted = [f for f in facts if norm(f.data.get("language", ""))[:4] in q] or facts
        ids = [f.id for f in wanted]
        text = " ; ".join(f.text for f in wanted)
        if any("anglais" in norm(f.text) for f in wanted) and profile.fact("cert.toeic"):
            ids.append("cert.toeic")
            text += f" ({profile.value('cert.toeic')})"
        return Answer(question=question, type=qtype, answer=text + ".", fact_ids=ids, confidence="HIGH" if wanted else "BLOCKED")
    if qtype == "ADMIN" and re.search(r"mobilit|demenag|relocat", q) and profile.fact("mobility.idf"):
        return Answer(question=question, type=qtype, answer=profile.value("mobility.idf") + " (confirmée). Au-delà : à préciser.",
                      fact_ids=["mobility.idf"], confidence="MEDIUM")
    if qtype == "FACTUAL":
        edu = profile.by_kind("education", "certification")
        if edu:
            return Answer(question=question, type=qtype, answer=" ; ".join(f.text for f in edu) + ".",
                          fact_ids=[f.id for f in edu], confidence="MEDIUM")
    asks = {
        "SALARY": "Quelles sont vos prétentions salariales pour ce poste (fixe + variable) ?",
        "ADMIN": "Information administrative non présente dans le profil : quelle réponse exacte souhaitez-vous donner ?",
        "EXPERIENCE": "Quel exemple concret (fait du profil) voulez-vous mettre en avant ? L'IA peut rédiger à partir des faits.",
        "VALUES": "Qu'est-ce qui vous attire personnellement dans cette entreprise ?",
        "PERSONALITY": "Quelles qualités voulez-vous mettre en avant (avec un exemple réel) ?",
        "OPEN": "Réponse personnelle nécessaire : que souhaitez-vous dire ?",
    }
    return Answer(question=question, type=qtype, answer="", confidence="BLOCKED",
                  ask_user=asks.get(qtype, asks["OPEN"]))


def split_questions(raw: str) -> list[str]:
    parts = [p.strip(" -•*\t") for p in re.split(r"\n+|(?<=\?)\s+", raw or "")]
    return [p for p in parts if len(p) > 5][:15]
