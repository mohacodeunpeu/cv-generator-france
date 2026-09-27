# Architecture PAI

## Objectif
PAI est une application autonome de préparation de candidatures, séparée du JobAgent et conçue pour produire des dossiers factuels, versionnés et testables.

## Composants
- profile: source de vérité du candidat et ses faits vérifiables
- analyze: parsing de l'offre, identification du secteur et du rôle cible
- strategy: positionnement, angle de message, priorités de contenu
- pdf_renderer: génération de CV et de lettre au format PDF
- benchmark: scores et comparaison des versions
- learning: historique de feedbacks, règles proposées

## Séparation stricte
- projet découplé de JobAgent
- environnement Docker distinct
- base PostgreSQL distincte
- secrets séparés
- aucun accès en écriture à JobAgent

## Périmètre Lot A livré
- Master profile
- Analyse d'offre
- Matching / strategy
- Génération de CV et de lettre PDF basique
- Pack ZIP exportable
- API /health /profile /analyze-job /generate-strategy /generate-cv /generate-pack

## Prochaines étapes
- benchmarking réel sur offres historiques
- validation factuelle stricte
- interface premium desktop/mobile
- stockage durable Postgres et jobs reprenables
