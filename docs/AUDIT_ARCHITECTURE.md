# Audit : vers un moteur CV/ATS autonome (29 septembre 2026)

Étape 1 du plan « moteur CV/ATS autonome + intégration future avec JobAgent ». **Aucun code n'a été modifié pour
cet audit** : lecture du dépôt, des branches, des commits, des tests, de la CI et de la PR, exécution des suites de
tests. Les constats sur JobAgent (dépôt privé) sont transmis à part : ce document public ne décrit que son
interface avec PAI.

## 1. Verdict

PAI est déjà, pour l'essentiel, le moteur applicatif demandé : un moteur Python indépendant de l'interface, des
fournisseurs IA interchangeables (Claude n'est qu'un fournisseur), un mode sans IA utile, une API `/v1`
authentifiée, PostgreSQL + migrations, Docker + HTTPS, et un validateur de factualité ligne à ligne. **Un rewrite
serait une perte** : le chemin le plus sûr est une série de petits ajouts testés.

Les vrais écarts avec la cible :

1. **Matching sémantique (niveau 3)** et étiquetage explicite **PROUVÉ / PLAUSIBLE / NON PROUVÉ** : absents.
2. **Validateur de format ATS** : la relecture du PDF existe, mais pas encore la détection des coordonnées, des
   dates, des en-têtes et pieds de page, des colonnes et tableaux, ni des textes contenus dans des images.
3. **Score** : des sous-scores explicables existent, mais pas le « PAI MATCH SCORE » nommé avec les composantes
   demandées.
4. **API pour JobAgent** : il manque l'analyse et la validation d'un CV existant, et l'envoi direct d'un PDF ou
   d'une page HTML d'offre (aujourd'hui : texte ou URL).
5. **Indépendance totale** : `config/models.yaml` désigne encore Claude comme fournisseur par défaut.
6. **Exposition** : le serveur est joint par son IP (nom sslip.io + Caddy) ; pas encore derrière Cloudflare.
7. **Observabilité** : pas d'identifiant de requête commun aux journaux ; la CI n'a ni lint ni typage, et elle
   valide la configuration Docker sans construire l'image.
8. **Production** : le serveur sert encore l'ancienne interface (mise à jour à lancer, `docs/DEPLOIEMENT_AUTO.md`).

## 2. Méthode et état du dépôt

| Élément | Constat |
| --- | --- |
| Visibilité | dépôt **public** ; branche par défaut sur GitHub : `pai-lot-a` (et non `master`) |
| Branches | `master`, `pai-lot-a`, `v-ultimate`, `claude/elegant-dirac-vhi4np` (travail en cours) |
| PR | mohacodeunpeu/cv-generator-france#2 (brouillon) : 13 commits au-dessus de `master`, fusionnable |
| Historique | `master` = « PAI Lot A foundation » (commit décalé, réparé sur la branche de travail) |
| Tests exécutés (29/09) | Python **274 réussis, 1 ignoré** (SQLite + PostgreSQL 16) · JS **13/13** · e2e Chromium **15/15** |
| CI (`.github/workflows/ci.yml`) | PostgreSQL 16 en service ; migrations upgrade → check → downgrade ; Python ; JS ; e2e ; `pip-audit` ; `docker compose config` |
| Données personnelles | garde-fou `tests/test_no_personal_data.py` ; l'historique Git public contient encore des coordonnées (`legacy/`, voir `docs/SECURITE_GIT.md`) |

## 3. Architecture actuelle (avant)

```
Navigateur ──HTTPS──► Caddy (Let's Encrypt, nom sslip.io de l'IP) ──► pai_web (FastAPI)
                                                                         │  /login, PAI Studio (une page, CSP à nonce)
                                                                         │  /v1 (clés d'API à droits), /v1/store, /v1/ai
                                                                         ├──► PostgreSQL 16 (pai_db, 30 tables)
                                                                         └──► pai_worker (jobs SKIP LOCKED, PDF Chromium)
Fournisseurs IA : Claude · OpenAI · Gemini · Mistral · local (Ollama) · null  ← réglages chiffrés / environnement
Seconde surface : la même page PAI Studio publiée sur claude.ai (IA et base de la plateforme) — optionnelle.
JobAgent (projet Docker séparé, même serveur) : client /v1 déjà écrit côté JobAgent, inactif sans clé d'API.
```

Moteur (`pai/`) : `ingest` (texte, URL anti-SSRF, PDF) → `analyzer` (intitulé, entreprise, lieu, contrat,
exigences MUST/NICE, mots-clés, outils, langues, secteur) → `matching` (12 sous-scores, preuves par fait :
direct / synonyme / implication) → `strategy` (angles A/B/C) → `cv_architect` (sélection gloutonne des faits) →
`claims` (validateur claim → evidence) → `critic` → `render` + `pdf_qa` (relecture du PDF) → `letter` →
`questions` → `pack` (ZIP, versions) ; `benchmark`, `providers`, `api`, `db`.

## 4. Ce qui est déjà solide (à garder tel quel)

| Domaine | Preuve |
| --- | --- |
| Profil maître = source de vérité, statuts CONFIRMED / IMPORTED / INFERRED / UNVERIFIED / FORBIDDEN | `pai/profile.py`, `profiles/`, MBA interdit (`tests/golden/validator_cases.json`, 23 cas) |
| Factualité ligne à ligne (faux diplôme, faux chiffre, outil non prouvé, niveau de langue gonflé, fausse entreprise, fausse date…) | `pai/claims.py`, parité JS `web/studio/engine.js`, factualité 100 sur le benchmark |
| Préférer « absent » à « inventé » | exigences non prouvées listées « non écrites » ; salaire BLOCKED |
| Abstraction IA : aucun module métier n'importe de SDK | `pai/providers/` (`base`, `claude`, `openai_compat` pour OpenAI / Gemini / Mistral / Ollama, `null`, `cache`) |
| Mode sans IA utile | fournisseur `null` ; benchmark « sans IA » 92,9 contre 54,6 pour l'ancien générateur |
| Coûts : modèle par tâche, cache, plafond journalier | `config/models.yaml` (petit modèle pour l'extraction, gros pour la critique), `pai/providers/cache.py` |
| Ingestion d'URL sûre et honnête | `pai/netfetch.py` (adresses privées, redirections, taille, délai), `pai/ingest.py` (pages derrière connexion refusées, repli texte / PDF) ; `tests/test_netfetch.py` (29 tests) |
| Séparation contenu / présentation | les gabarits ne font que la mise en page ; même texte dans les 5 designs (`tests/e2e/test_designs.py`) |
| Relecture du PDF produit | pages, texte extractible, ordre de lecture ATS, polices embarquées, taille minimale, contraste, débordement (`pai/pdf_qa.py`, `PDF.inspect`) |
| Serveur : auth argon2, sessions révocables, CSRF, limitation, clés d'API, liens signés, CSP, HSTS, noindex | `pai/api/`, `tests/test_api.py` (SQLite + PostgreSQL) |
| Jobs asynchrones idempotents, journal des appels IA, résultats réels | tables `jobs`, `llm_calls`, `outcomes`, `application_packs`, `generations` |
| Déploiement : Docker multi-arch, projet isolé, sauvegardes chiffrées testées, mise à jour avec retour arrière | `Dockerfile`, `docker-compose.yml`, `deploy/` |

## 5. Ce qui est fragile

| Risque | Pourquoi | Parade proposée |
| --- | --- | --- |
| Deux moteurs (Python et JS) à maintenir en parité | la page claude.ai calcule en JS | garder le test de parité ; à terme, le serveur devient la référence et la page claude.ai une vitrine |
| Fournisseur par défaut = Claude | `config/models.yaml` : `default_provider: claude` | défaut `null`, choix explicite du fournisseur |
| Aucun identifiant de requête | diagnostic d'un pipeline difficile | `request_id` propagé (journal, jobs, `llm_calls`) sans contenu personnel |
| CI sans lint, sans typage, sans build d'image | régressions de style ou d'image détectées tard | `ruff` + `docker build` en CI (typage progressif ensuite) |
| Page unique de 1,3 Mo, bibliothèques sur CDN | premier chargement plus lent ; dépendance au CDN | acceptable pour un seul utilisateur ; possible mise en cache immuable plus tard |
| Serveur joint par son IP | l'IP est connue de quiconque a l'adresse | Cloudflare devant (DNS proxifié ou Tunnel nommé) |
| Historique Git public | coordonnées dans `legacy/` | passage en privé ou purge (`docs/SECURITE_GIT.md`), décision du propriétaire |

## 6. Exigences du cahier des charges → état

Barème : **1** = fait et testé · **0,5** = partiel · **0** = absent. Les pourcentages de la section 9 sont
calculés sur cette grille ; la grille elle-même est un choix : c'est une estimation structurée, pas une mesure.

### ATS ENGINE — 9 / 12 = 75 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| Parsing de l'offre (titre, entreprise, lieu, contrat) | 1 | `analyzer.py` |
| Exigences obligatoires / souhaitées | 1 | priorités REQUIRED / MUST, `missing` |
| Mots-clés, outils, langues | 1 | `analyzer.py`, `rules/skill_synonyms.yaml` |
| Niveau 1 : correspondance exacte | 1 | `rules.Synonyms.supported_by` → « direct » |
| Niveau 2 : synonymes / variations | 1 | groupes d'équivalents et implications |
| Niveau 3 : correspondance sémantique | 0 | absent (ni IA dédiée ni plongements) |
| Classement PROUVÉ / PLAUSIBLE / NON PROUVÉ exposé | 0,5 | couvert / manquant + voie « implication », sans étiquette PLAUSIBLE |
| Analyse des écarts | 1 | `missing`, `why_not`, `risks` |
| Score interne nommé, composantes expliquées | 0,5 | 12 sous-scores expliqués ; pas de « PAI MATCH SCORE » aux composantes demandées |
| Rapport JSON job / candidate / matching / recommendations | 0,5 | JSON d'analyse et de correspondance, forme différente |
| Fonctionne sans IA | 1 | fournisseur `null`, benchmark |
| Module ATS indépendant de l'interface | 0,5 | logique indépendante mais répartie (`analyzer`, `matching`, `claims`, `pdf_qa`), pas de paquet `ats/` |

### DOCUMENT ENGINE — 8,5 / 10 = 85 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| Contenu séparé de la présentation | 1 | gabarits sans texte propre ; test « même contenu dans les 5 designs » |
| Designs existants conservés | 1 | 5 familles + gabarits serveur |
| Re-parsing du PDF généré | 1 | `pdf_qa.extract_text`, `PDF.inspect` |
| Validateur de format ATS complet | 0,5 | manquent coordonnées, dates, en-têtes / pieds, colonnes / tableaux, texte en image, caractères inhabituels |
| Boucle génération → contrôle → correction bornée | 1 | cycles de critique bornés, `trimForSpace`, contrôle final |
| Plusieurs CV de base (MASTER, COMMERCIAL…) | 0,5 | profils sectoriels + angles ; pas d'objet « CV de base » choisi et journalisé |
| Lettre soumise aux mêmes règles | 1 | validateur de lettre, factualité 100 |
| Justification de chaque changement | 0,5 | « Pourquoi ce CV ? », « Ce qui a changé », preuves au survol ; pas de tableau mot-clé par mot-clé (ajouté + preuve / non ajouté + raison) |
| Aperçu avant téléchargement | 1 | vue Application Pack |
| Pack candidature | 1 | ZIP (PDF, JSON, Markdown) |

### AI ABSTRACTION — 8,5 / 10 = 85 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| Interface unique, métier sans SDK | 1 | `pai/providers/__init__.py` |
| Anthropic optionnel | 0,5 | fonctionne sans, mais reste le défaut de `config/models.yaml` |
| OpenAI-compatible (OpenAI, Gemini, Mistral) | 1 | `openai_compat.py` |
| Local (Ollama) | 1 | `local_provider` |
| Configuration par environnement / réglages | 1 | `PAI_AI_PROVIDER`, `*_API_KEY`, `*_MODEL`, réglages chiffrés en base |
| Noms génériques `AI_PROVIDER` / `AI_MODEL` / `AI_BASE_URL` / `AI_API_KEY` | 0 | non reconnus (ajout trivial) |
| Mode sans IA | 1 | `null`, badge DEGRADED |
| Cache par empreinte, déduplication | 1 | `CachedProvider`, jobs idempotents |
| Budget contrôlable | 1 | plafond de coût journalier |
| Modèle léger / puissant selon la tâche | 1 | `config/models.yaml` |

### API — 7 / 10 = 70 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| API JSON authentifiée à droits | 1 | clés `read` / `analyze` / `generate` / `outcomes` |
| Analyse d'offre | 1 | `POST /v1/analyze-job` |
| Génération CV, lettre, pack | 1 | `POST /v1/generate-cv`, `/generate-letter`, `/generate-application-pack` |
| Analyse d'un CV existant | 0 | absent |
| Validation d'un CV (re-parsing + rapport ATS) | 0 | absent |
| Optimisation séparée de la génération | 0,5 | faite dans `generate-cv`, pas d'appel distinct |
| Offre en texte / URL / PDF / HTML | 0,5 | texte et URL (PDF derrière une URL lu) ; pas d'envoi direct de PDF ou de HTML |
| Échec d'URL honnête + repli | 1 | codes `login_walled`, `blocked_address`, `timeout`… |
| Jobs asynchrones, idempotence | 1 | `Idempotency-Key`, `GET /v1/jobs/{id}` |
| Contrat documenté | 1 | `docs/api.md` |

### SECURITY — 7,5 / 10 = 75 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| Secrets hors Git | 1 | `.env`, réglages IA chiffrés |
| Garde-fou anti-données personnelles | 1 | `tests/test_no_personal_data.py` |
| Historique public sans données personnelles | 0 | `legacy/` dans l'historique |
| Authentification serveur | 1 | argon2, sessions révocables, CSRF, limitation |
| En-têtes de sécurité | 1 | CSP à nonce, HSTS, `noindex`, `frame-ancestors 'none'` |
| SSRF | 1 | `netfetch.py`, 29 tests |
| Journaux sans secret ni contenu personnel inutile | 0,5 | aucun secret journalisé par conception ; pas d'audit systématique du contenu |
| Origine masquée | 0,5 | HTTPS + connexion, mais IP exposée |
| Données de l'outil voisin | 0,5 | voir le rapport privé |
| Audit des dépendances | 1 | `pip-audit` en CI |

### DEPLOYMENT — 4,5 / 7 = 64 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| Dockerfile, Compose, `.env.example` | 1 | multi-arch, projet `pai` isolé |
| PostgreSQL en production, SQLite en développement, migrations fiables | 1 | Alembic upgrade / check / downgrade en CI |
| Reverse proxy HTTPS | 1 | Caddy |
| Sauvegardes chiffrées, restauration testée | 1 | `deploy/backup.sh`, `deploy/restore.sh` |
| Mise à jour sûre avec retour arrière | 0,5 | `deploy/update.sh` testé en bac à sable, pas encore exécuté en production |
| Cloudflare devant PAI | 0 | absent |
| Production à jour | 0 | ancienne interface en ligne |

### JOBAGENT INTEGRATION — 3 / 7 = 43 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| API stable côté PAI | 1 | `/v1` + clés à droits |
| Client côté JobAgent avec repli | 1 | écrit côté JobAgent, inactif sans clé |
| Clé d'API créée et branchée | 0 | à faire |
| Pack (CV, lettre, métadonnées) consommé par JobAgent | 0,5 | appels prévus, pas encore utilisés dans son parcours |
| « Quel CV pour quelle offre ? » | 0,5 | `generations`, `application_packs`, `outcomes` existent ; pas encore alimentés par JobAgent |
| Humain dans la boucle avant tout envoi | 0 | voir le rapport privé |
| Tests de contrat PAI ↔ JobAgent | 0 | absents |

### TESTING — 6 / 9 = 67 %

| Critère | État | Preuve / écart |
| --- | --- | --- |
| Unitaires : parsing, mots-clés, synonymes, factualité, scoring | 1 | `test_engine`, `test_claims`, cas dorés |
| Validation des PDF | 1 | `tests/e2e/test_designs.py` |
| API sur SQLite et PostgreSQL | 1 | `tests/test_api.py` |
| Intégration offre → CV → lettre → pack | 1 | e2e parcours complet, e2e serveur |
| e2e : connexion, profil, nouvelle candidature, import PDF, URL, génération, téléchargement | 0,5 | tout sauf l'import PDF et l'URL côté serveur en e2e |
| CI obligatoire (Python, JS, e2e, migrations, audit) | 1 | `ci.yml` |
| Lint / typage en CI | 0 | absents |
| Build de l'image Docker en CI | 0 | seule la configuration est validée |
| Benchmark réel | 0,5 | structure REAL / LEGACY / SYNTHETIC prête ; pas encore d'offres réelles |

### DOCUMENTATION — 7 / 9 = 78 %

| Fichier demandé | État | Existant |
| --- | --- | --- |
| `README.md`, `RUNBOOK.md`, `PROGRESS.md`, `docs/api.md` | 1 chacun | à jour |
| `docs/architecture.md` | 1 | `ARCHITECTURE.md` (racine) |
| `docs/deployment.md` | 1 | `docs/DEPLOIEMENT_AUTO.md` + RUNBOOK |
| `docs/ai-providers.md` | 0,5 | RUNBOOK § 6 |
| `docs/jobagent-integration.md` | 0,5 | contrat dans `docs/api.md` |
| `docs/ats.md` | 0 | absent |

## 7. Architecture cible (après)

Même application, pas de microservices : un seul service web (FastAPI) + un worker + PostgreSQL, dans le projet
Docker `pai`. Les ajouts se font **à côté** du code existant, derrière des tests.

```
Navigateur ─► Cloudflare (HTTPS, IP d'origine masquée) ─► pai_web ─► services ─► PostgreSQL / fichiers
JobAgent  ─► Cloudflare ─► /v1 (clé d'API)                 └─► pai_worker (génération, PDF)

INGESTION (texte · URL · PDF · HTML) → ATS ENGINE → PROFILE MATCH → GAP ANALYSIS → CV OPTIMIZER (contenu)
→ CV GENERATOR (présentation) → PDF VALIDATOR (re-parsing) → [correction bornée] → LETTER ENGINE
→ APPLICATION PACK → réponse JSON à JobAgent → journal (quel CV, quelle offre, quel résultat)
Fournisseur IA : null par défaut ; OpenAI-compatible, Ollama local ou Anthropic sur choix explicite.
```

Choix proposés, et pourquoi :

- **`pai/ats/`** : un paquet de façade qui regroupe ce qui existe (`parser` → `ingest`, `job_analyzer` →
  `analyzer`, `skill_matcher` → `matching` + synonymes, `gap_analyzer`, `scoring`) et n'ajoute que le neuf :
  `semantic_matcher` (IA optionnelle et mise en cache, résultat toujours **PLAUSIBLE**, jamais compté comme
  preuve), `ats_validator` (contrôles de format ajoutés à `pdf_qa`) et `report` (JSON à la forme demandée). Pas de
  déplacement de code, donc pas de risque de régression.
- **PAI MATCH SCORE** calculé à partir des sous-scores existants, avec composantes REQUIREMENTS, KEYWORD
  COVERAGE, VERIFIED SKILL COVERAGE, CV PARSABILITY, FACTUALITY, RELEVANCE, chacune avec sa justification.
  Jamais présenté comme le score d'un ATS réel.
- **API** : on garde `/v1`, déjà utilisé par le client JobAgent, et on ajoute ce qui manque en suivant ses
  conventions : `POST /v1/cv/analyze`, `POST /v1/cv/validate`, et l'envoi d'une offre en PDF ou HTML dans
  `OfferIn`. Pas de seconde arborescence `/api` à maintenir en parallèle.
- **Cloudflare** : un **Tunnel nommé** (conteneur `cloudflared` dans le projet `pai`, aucun port entrant) si un
  domaine est géré par Cloudflare ; sinon Caddy reste en place. **Cloudflare Pages n'est pas nécessaire** :
  l'interface est servie par le backend sur la même origine, ce qui évite CORS et les cookies intersites.
- **Fournisseur par défaut `null`**, et reconnaissance des variables génériques `AI_PROVIDER`, `AI_MODEL`,
  `AI_BASE_URL`, `AI_API_KEY` en plus des variables actuelles.
- **Observabilité** : `request_id` dans les journaux, les jobs et `llm_calls` (étape, durée, fournisseur,
  modèle, jetons, cache touché / manqué), sans contenu personnel.

## 8. Plan de migration (une étape = une PR, testée, réversible)

| # | Étape | Changements | Tests ajoutés | Retour arrière | Taille |
| --- | --- | --- | --- | --- | --- |
| 2 | Architecture cible validée | ce document + décisions de la section 10 | — | — | S |
| 3 | Indépendance Claude | défaut `null`, alias `AI_*`, `docs/ai-providers.md` | résolution du fournisseur sans aucune clé | revert d'un commit | S |
| 4 | Moteur ATS | `pai/ats/` (façade), `semantic_matcher` optionnel, étiquettes PROUVÉ / PLAUSIBLE / NON PROUVÉ, PAI MATCH SCORE, `report` JSON, `docs/ats.md` | unitaires par niveau, cas « CRM plausible / Salesforce non prouvé / prospection B2B prouvée » | paquet isolé, non branché tant qu'il n'est pas validé | M |
| 5 | Ingestion PDF / HTML | `OfferIn` accepte un PDF (base64) ou du HTML ; même normalisation | offre PDF → analyse, HTML → texte propre | champ optionnel | S |
| 6 | Revalidation PDF | `ats_validator` : coordonnées, dates, sections, colonnes, en-têtes / pieds, texte en image, caractères ; boucle de correction bornée | PDF volontairement fautifs | contrôles « avertissement » avant « bloquant » | M |
| 7 | API | `POST /v1/cv/analyze`, `POST /v1/cv/validate`, tableau de justification mot-clé par mot-clé dans les réponses | API sur SQLite + PostgreSQL | nouveaux endpoints seulement | M |
| 8 | Auth + base | table / vue « candidatures » (offre, CV de base, version, mots-clés prouvés / manquants / non prouvés, PDF, validation, envoyé, résultat) sur les tables existantes | migration upgrade / downgrade | migration réversible | S |
| 9 | Docker + Cloudflare | `cloudflared` optionnel (profil Compose), build de l'image en CI | `docker build` en CI | profil désactivé = Caddy | S |
| 10 | Client JobAgent | clé d'API, tests de contrat, mode MANUEL / ASSISTÉ / AUTOMATIQUE côté JobAgent **sans envoi automatique avant validation** | contrat sur une offre fictive | clé révocable, repli JobAgent existant | M |
| 11 | Benchmark réel | offres réelles fournies (texte), catégories commercial / recrutement / business development / digital / chargé d'affaires ; CV de base vs CV optimisé | métriques documentaires uniquement | données hors Git | S |
| 12 | CI + docs | `ruff`, typage progressif, `docs/jobagent-integration.md`, rapport final | CI verte | — | S |

Tailles : S ≈ une session, M ≈ deux à trois sessions. Aucune étape ne touche au validateur de factualité, sinon
pour lui ajouter des cas.

## 9. Avancement estimé (calculé sur la grille de la section 6)

| Domaine | Score | % |
| --- | --- | --- |
| ATS ENGINE | 9 / 12 | 75 % |
| DOCUMENT ENGINE | 8,5 / 10 | 85 % |
| AI ABSTRACTION | 8,5 / 10 | 85 % |
| API | 7 / 10 | 70 % |
| SECURITY | 7,5 / 10 | 75 % |
| DEPLOYMENT | 4,5 / 7 | 64 % |
| JOBAGENT INTEGRATION | 3 / 7 | 43 % |
| TESTING | 6 / 9 | 67 % |
| DOCUMENTATION | 7 / 9 | 78 % |

## 10. Décisions attendues avant de coder

1. **Envois automatiques de JobAgent** : les suspendre (ne garder que les dossiers validés) tant que le pipeline
   n'est pas validé sur de vraies offres ? (détails dans le rapport privé)
2. **Cloudflare** : un domaine géré par Cloudflare est-il disponible (nécessaire pour un Tunnel nommé stable) ?
3. **Branche** : fusionner d'abord la PR n° 2 dans `master`, puis créer `feature/autonomous-ats-engine` depuis
   `master` ; ou empiler la nouvelle branche sur la PR n° 2 ?
4. **Fournisseur IA sur le serveur** : lequel, avec quel budget mensuel ? (le défaut deviendra « aucun »)
5. **CV de base** : confirmer la liste (MASTER, COMMERCIAL, BUSINESS_DEVELOPER, RECRUTEMENT, DIGITAL,
   CHARGE_AFFAIRES), qui sera rattachée aux profils sectoriels existants.
6. **Benchmark réel** : 10 à 20 offres réelles (texte collé) par catégorie.
