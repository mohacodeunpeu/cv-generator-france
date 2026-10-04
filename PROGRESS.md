# Progression PAI — point de reprise

Une nouvelle session lit ce fichier, puis `ARCHITECTURE.md`, `DECISIONS.md` et `docs/deployment.md`.
Branche : `feature/pai-ultimate-autonomous` → PR brouillon `mohacodeunpeu/cv-generator-france#3` (base
`claude/elegant-dirac-vhi4np`) ; rien sur `master`, la fusion est la décision du propriétaire.
JobAgent : branche `feature/pai-integration` → PR brouillon `mohacodeunpeu/hellowork-automation-pro#1` (jamais `main`,
qui se déploie tout seul).

## Grille d'avancement (critères explicites, mesurés au 4 octobre 2026)

Chaque pourcentage = critères remplis et prouvés / critères définis. Une dépendance externe est nommée à part,
jamais comptée comme faite.

| Domaine | Critères (preuve) | Fait | % |
|---|---|---|---|
| **Moteur ATS** | lecture de CV ; analyse d'offre ; mots-clés ; synonymes et taxonomie française ; sémantique locale jamais preuve ; classes MUST/IMPORTANT/NICE/CONTEXT ; PROUVÉ/PLAUSIBLE/NON PROUVÉ (HubSpot, prospection, Salesforce, immobilier testés) ; écarts ; factualité ; scanner PDF OK/WARNING/ERROR (liste complète du cahier des charges, dont en-tête/pied de page et densité) ; Score PAI en dimensions ; modes A et B ; « pourquoi présent / pas ajouté » ; corpus TOP 20/40 avec volume ; boucle de relecture bornée ; parité Python ↔ JS (`tests/test_ats.py`, `tests/js/ats.test.js`) | 16/16 | **100 %** |
| **Moteur de documents** | gabarits conservés ; contenu séparé du design ; profil maître unique ; 6 variantes ; interdits (MBA, diplômes, chiffres…) ; provenance par ligne ; avant/après/raison/preuve ; CV → PDF → relecture ; lettre au même validateur ; pack complet ; versions (`application_id`, `version_id`, empreintes, profil, gabarit, date) ; pack téléchargeable | 12/12 | **100 %** |
| **Abstraction IA** | interface multi-fournisseurs ; défaut local/none ; alias `AI_*` ; routeur aucune/petit/grand/externe et profils ; aucune IA pour le déterministe ; cache par empreinte (hit/miss, invalidation) ; JSON validé et réponses rejetées jamais resservies ; contextes minimaux (lettre, correction) ; dégradation propre ; usage visible | 10/10 | **100 %** |
| **IA locale** | fournisseur Ollama ; détection matérielle réelle ; auto-évaluation 7 tâches + vitesse + mémoire ; porte de vérité ; choix automatique ; registre configurable (contexte, température, délai, jetons) ; marche sans modèle ; génération réelle en Docker mesurée ; profil conseillé par la mesure | 9/9 | **100 %** (qualité bornée par le CPU : voir limites) |
| **API** | `/api/jobs/analyze`, `/jobs/ingest`, `/cv/analyze`, `/cv/optimize`, `/cv/generate`, `/cv/validate`, `/letter/generate`, `/application/prepare`, `GET /application/{id}`, `/health`, `/ready` ; PDF/HTML/DOCX/texte directs ; documentée (`docs/api.md`) ; testée (`tests/test_public_api.py`) | 14/14 | **100 %** |
| **Sécurité** | secrets hors Git + garde-fou CI (clés, jetons, IP de serveur) ; journaux sans contenu ; sessions (connexion, déconnexion, expiration, révocation au changement de mot de passe) ; CSRF/CSP/en-têtes ; anti-SSRF ; clés d'API hachées à droits ; IP réelle derrière le tunnel ; `pip-audit` ; lint et typage | 9/9 | **100 %** autonome · externe : dépôt public avec ancien historique `legacy/` (décision du propriétaire) |
| **Déploiement** | image multi-architecture ; Compose pai/postgres/ollama/cloudflared(/caddy) ; `.env.example` ; tunnel nommé + état ; migrations au démarrage + `/api/ready` ; sauvegarde chiffrée + restauration vérifiée en CI ; mise à jour sauvegarde → build → migration → santé → fumée → retour arrière (détachée) ; image testée en CI ; contrôles de santé des trois services | 9/9 | **100 % prêt** · externe : jeton de tunnel et domaine, mise à jour du serveur (accès non disponible d'ici) |
| **JobAgent** | audit du pont ; pont robuste ; modes OFF/ASSISTED/AUTO + `PAI_ENABLED`/`PAI_REQUIRED` ; branché (HelloWork, France Travail) ; repli ; tests (faux PAI) + essai réel de bout en bout ; README conforme au comportement réel ; automatisation existante intacte (534 tests) | 8/8 | **100 %** du code · externe : fusion de la PR #1 |
| **Tests** | Python (SQLite + PostgreSQL) ; API ; JS (parité) ; navigateur (Studio et serveur, CSP) ; Docker (CI + pile locale) ; sauvegarde/restauration ; IA (routeur, cache, replis, IA locale réelle) ; PDF ; URL (anti-SSRF, causes d'échec) ; pont JobAgent ; lint ; typage | 12/12 | **100 %** · externe : test d'URL sur de vrais sites d'emploi (refusés par le réseau de l'environnement) |
| **Documentation** | README ; RUNBOOK ; ARCHITECTURE ; API ; DEPLOYMENT ; ATS ; AI PROVIDERS ; JOBAGENT INTEGRATION ; SECURITY ; PROGRESS ; BENCHMARK | 11/11 | **100 %** |

AUTONOME : 100 % des fonctions marchent sans IA externe ni compte Claude · OPTIONNEL EXTERNE : disponible.

## Mesures clés

- Régression (13 offres fictives, PAI sans IA) : score 92,9 contre 54,6 ; factualité CV et lettre 100 % ;
  0 ligne non prouvée ; couverture honnête 97,4 % (`docs/benchmark.md`).
- IA locale en Docker (3 cœurs, sans GPU) : pack en 320 s, lettre de `qwen3:4b-instruct` retenue, factualité 100 %
  (`docs/ai-providers.md`).
- Pile Docker (PostgreSQL + interface/API + worker) saine en 23 s ; test de fumée complet (`docs/deployment.md`).

## À faire par le propriétaire

1. **Valider le profil** dans PAI (onglet Profil) : sans validation, tout reste `BROUILLON` et JobAgent (mode auto)
   n'envoie jamais un document PAI.
2. **Accès public** : domaine chez Cloudflare, tunnel nommé, `CLOUDFLARE_TUNNEL_TOKEN` (`docs/deployment.md` § 3).
3. **Mettre à jour le serveur** : `deploy/update.sh` (ou minuteur / bouton, `docs/DEPLOIEMENT_AUTO.md`).
4. **IA locale** (facultatif) : `COMPOSE_PROFILES=…,ai-local` puis `python -m pai ai setup --pull`.
5. **JobAgent** : clé d'API PAI, `JOBAGENT_PAI_URL`, `PAI_MODE=assisted` pour commencer ; fusionner la PR #1.
6. **Offres réelles** : déposer des offres dans `data/benchmark_real/` sur le serveur et lancer
   `python -m pai benchmark-real` (l'environnement de développement n'a pas accès aux sites d'emploi).
7. **Dépôt public** : passer en privé (historique `legacy/` avec d'anciennes coordonnées).

## Limites connues

- IA locale sur CPU : une lettre prend 3 à 6 minutes ; le profil `eco` limite l'IA à la lettre. Un modèle de
  4 milliards de paramètres rédige moins bien qu'un grand modèle externe : PAI garantit la vérité, pas le style.
- Le Score PAI mesure la qualité et la preuve, pas une probabilité d'embauche ; deux familles de lecture d'ATS
  sont simulées, pas tous les ATS du marché.
- Benchmark sur offres réelles : outil prêt et testé, aucun résultat publié tant que des offres réelles n'ont pas
  été mesurées sur le serveur.
