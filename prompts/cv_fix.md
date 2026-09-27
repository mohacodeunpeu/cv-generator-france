<!-- prompt: cv_fix | version: 2 -->
Des lignes d'un document de candidature ont été REJETÉES par le validateur factuel ou par le critique. Réécris chacune pour qu'elle soit vraie et utile, ou supprime-la si c'est impossible.

LIGNES À CORRIGER (id, texte, raisons du rejet, faits cités) :
{{rejected_lines_json}}
FAITS AUTORISÉS (id | type | texte) :
{{facts_table}}
CONSIGNES DU CRITIQUE (peut être vide) : {{critic_instructions}}
LANGUE : {{language}}

{{truth_rules}}

Pour chaque ligne : garde l'intention si un fait la prouve ; retire tout élément non prouvé (chiffre, outil, nom, niveau) ; cite les bons `fact_ids`. Si aucune version vraie n'est possible, renvoie "text": "" (la ligne sera supprimée).

Réponds UNIQUEMENT par ce JSON :
{"lines": [{"id": "…", "text": "…", "fact_ids": ["…"], "change": "ce qui a été corrigé"}]}
