<!-- prompt: match | version: 2 -->
Tu évalues l'adéquation sémantique entre une offre et un candidat. Les sous-scores chiffrés sont déjà calculés de façon déterministe : tu ne les changes pas, tu expliques et tu complètes.

OFFRE ANALYSÉE : {{analysis_json}}
FAITS DU CANDIDAT (id | type | statut | texte) :
{{facts_table}}
CALCUL DÉTERMINISTE : {{deterministic_match_json}}

{{truth_rules}}

Réponds UNIQUEMENT par ce JSON :
{
  "why_fit": [{"text": "…", "fact_ids": ["…"]}],
  "why_not": [{"text": "…", "fact_ids": []}],
  "missing": [{"requirement": "…", "priority": "MUST|IMPORTANT|NICE", "note": "…"}],
  "strengths": [{"text": "…", "fact_ids": ["…"]}],
  "risks": [{"text": "…"}],
  "semantic_links": [{"offer_term": "…", "fact_ids": ["…"], "via": "direct|synonyme|contexte"}]
}
`why_fit` et `strengths` citent les faits qui les prouvent. `missing` liste honnêtement ce qu'aucun fait ne couvre.
