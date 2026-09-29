<!-- prompt: answers | version: 2 -->
Tu prépares les réponses aux questions d'un formulaire de candidature, pour {{candidate_name}}, en {{language}}.

QUESTIONS :
{{questions}}
OFFRE ANALYSÉE : {{analysis_json}}
FAITS AUTORISÉS (id | type | texte) :
{{facts_table}}

{{truth_rules}}

Pour chaque question :
- `type` : FACTUAL, ADMIN, EXPERIENCE, SALARY, AVAILABILITY, LANGUAGE, PERSONALITY, VALUES ou OPEN.
- `confidence` : HIGH (fait direct), MEDIUM (fait + reformulation), LOW (fait partiel), BLOCKED (aucun fait : on demande à l'utilisateur).
- BLOCKED ⇒ "answer": "" et `ask_user` = la question précise à poser à l'utilisateur. Salaire, âge, nationalité, permis, handicap : BLOCKED sauf fait explicite.
- Réponses courtes, concrètes, sans phrase creuse.

Réponds UNIQUEMENT par ce JSON :
{"answers": [{"question": "…", "type": "FACTUAL", "answer": "…", "fact_ids": ["…"], "confidence": "HIGH", "ask_user": ""}]}
