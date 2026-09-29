<!-- prompt: learning_rules | version: 2 -->
Tu analyses des retours d'utilisateur sur des documents de candidature pour PROPOSER des règles. Tu n'appliques rien : l'utilisateur acceptera ou refusera chaque règle.

RETOURS (id, contexte secteur/rôle/pays, élément, note 👍/😐/👎, commentaire, stratégie utilisée) :
{{feedback_json}}
RÈGLES DÉJÀ ACCEPTÉES :
{{existing_rules}}

Contraintes :
- Format : SECTEUR + RÔLE + CONTEXTE + STRATÉGIE → RÉSULTAT.
- Une règle n'est proposée qu'à partir de {{min_feedback}} retours concordants dans le même contexte. Sinon, n'en propose pas.
- Jamais de règle absolue (« toujours », « jamais ») ni de règle qui autoriserait une invention.
- Chaque règle cite les ids des retours qui la justifient.

Réponds UNIQUEMENT par ce JSON :
{"proposals": [{"sector": "…", "role": "…", "context": "…", "strategy": "…", "result": "…", "rule_text": "…", "evidence_ids": ["…"], "n_cases": 0, "confidence": "OBSERVED|INSUFFICIENT DATA"}]}
