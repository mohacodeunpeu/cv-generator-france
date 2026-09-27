# Progression PAI — point de reprise

Une nouvelle session lit ce fichier, puis `DECISIONS.md` et `RUNBOOK.md`, et reprend à « Reste à faire ».

## Fait (avec preuve)

- **P0** — commit `master` décalé réparé ; architecture, décisions, règles versionnées. Preuve : `import pai` OK.
- **P0.5** — JobAgent `/profil` : GET refusé par la politique réseau → `PROFILE_IMPORT_REQUIRED`.
  Master Profile v1 construit depuis `profiles/confirmations.yaml` + `legacy/amine_profile.py` (85 faits,
  MBA FORBIDDEN, 1 conflit en REVIEW). Preuve : `python -m pai bootstrap-profile`.
- **P1-P3** — profil versionné, analyse d'offre (13/13 secteurs corrects sur le benchmark), matching, stratégie.
- **P4** — CV Architect + rendu Chromium + PDF QA. Preuve : premier CV réel (profil réel, offre SYNTHETIC)
  1 page, factualité 100 %, 6/6 mots-clés REQUIRED extraits par pdfplumber.
- **P5** — validateur claim → evidence : tous les pièges rejetés (MBA, faux Master, faux chiffre, Salesforce,
  « bilingue », entreprise inventée, fait UNVERIFIED, phrases creuses, fausse date).
- **P6** — lettre, questions (salaire BLOCKED), Application Pack ZIP versionné (mode dégradé : 3 s).

## Reste à faire

Voir la section « Reste à faire » mise à jour en fin de session.
