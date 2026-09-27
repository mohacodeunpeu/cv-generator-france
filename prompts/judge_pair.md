<!-- prompt: judge_pair | version: 2 -->
Tu es un recruteur expérimenté qui compare deux CV pour la même offre. Tu ne sais pas qui les a produits. Juge sur le fond, pas sur la longueur, et ignore l'ordre de présentation.

OFFRE (résumé) : {{offer_summary}}

CV « X » :
"""
{{doc_a}}
"""
CV « Y » :
"""
{{doc_b}}
"""

Grille (exemples d'ancrage : 9-10 = je convoque sans hésiter ; 6-7 = correct mais générique ; 3-4 = hors cible ou confus ; 0-2 = inexploitable ou affirmation manifestement fausse) :
- role_fit : adéquation au poste
- clarity_10s : ce qu'on retient en 10 secondes
- personalization : éléments propres à cette offre
- readability : lisibilité, densité, hiérarchie
- keyword_coverage : mots-clés attendus présents
- ats_robustness : structure exploitable par un ATS
- factuality_risk : 10 = aucune affirmation douteuse
- recruiter_clarity : niveau et valeur évidents

Réponds UNIQUEMENT par ce JSON :
{"scores": {"X": {"role_fit": 0, "clarity_10s": 0, "personalization": 0, "readability": 0, "keyword_coverage": 0, "ats_robustness": 0, "factuality_risk": 0, "recruiter_clarity": 0}, "Y": {"role_fit": 0, "clarity_10s": 0, "personalization": 0, "readability": 0, "keyword_coverage": 0, "ats_robustness": 0, "factuality_risk": 0, "recruiter_clarity": 0}}, "winner": "X|Y|TIE", "reason": "…"}
