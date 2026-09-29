<!-- prompt: letter | version: 3 -->
Tu écris la lettre de motivation de {{candidate_name}} pour cette offre, en {{language}}. Une lettre qu'un recruteur lit jusqu'au bout parce qu'elle parle de SON poste, avec des preuves.

OFFRE ANALYSÉE : {{analysis_json}}
STRATÉGIE : {{strategy_json}}
CE QUE L'ON SAIT DE L'ENTREPRISE (uniquement ceci) : {{company_facts}}
FAITS AUTORISÉS (id | type | texte) :
{{facts_table}}
PROFIL SECTEUR (ton, longueur) : {{sector_json}}
PHRASES INTERDITES : {{banned_phrases}}
RETOURS PASSÉS DE L'UTILISATEUR (peut être vide) : {{feedback_context}}

{{truth_rules}}

Structure obligatoire (un paragraphe par étape) :
1. HOOK : une accroche spécifique à CE poste (pas de formule d'ouverture générique).
2. WHY_ROLE : pourquoi ce poste (missions reprises de l'offre).
3. WHY_COMPANY : pourquoi cette entreprise, UNIQUEMENT avec ce que disent l'offre ou les sources enregistrées. Si l'on ne sait rien, parle du poste et du contexte décrit, sans inventer.
4. PROOF : 2 ou 3 preuves du parcours, chacune reliée aux faits.
5. VALUE : ce que le candidat apportera (projection au futur, sans chiffre inventé).
6. CLOSE : conclusion avec disponibilité et mobilité si ces faits existent.

Chaque phrase est typée :
- "claim" : affirme un fait sur le candidat → `fact_ids` obligatoires.
- "offer_ref" : reprend un élément de l'offre → `offer_quote` = citation exacte de l'offre.
- "projection" : intention ou valeur future, sans chiffre ni nom propre hors entreprise et poste.
- "closing" : politesse et appel à l'échange (sobre).
Au moins 2 phrases "offer_ref" avec des éléments propres à l'annonce. Longueur : {{length_words}} mots. Nom de l'entreprise et intitulé exacts : « {{company}} », « {{job_title}} ».

Réponds UNIQUEMENT par ce JSON :
{
  "subject": "…",
  "salutation": "…",
  "paragraphs": [{"role": "HOOK", "sentences": [{"text": "…", "kind": "claim", "fact_ids": ["…"], "offer_quote": ""}]}],
  "signature": "{{candidate_name}}"
}
