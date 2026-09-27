<!-- prompt: judge_visual | version: 2 -->
Tu regardes l'image d'une page de CV (rendu réel du PDF). Contexte : {{context}}.
Évalue uniquement ce qui se VOIT : hiérarchie, densité, alignements, marges, débordements, texte coupé, contraste, taille des caractères, cohérence des couleurs, rendu de la photo (si présente), lisibilité en 10 secondes.

Réponds UNIQUEMENT par ce JSON :
{"score": 0, "issues": [{"severity": "high|medium|low", "where": "…", "problem": "…", "fix": "…"}], "verdict": "PASS|FAIL"}
Score de 0 à 10. FAIL si un défaut empêche l'envoi (texte coupé, débordement, page blanche, illisible).
