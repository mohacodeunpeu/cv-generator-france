# Architecture — PAI (Personal Application Intelligence)

PAI transforme une offre (texte, lien, PDF, HTML, DOCX) en candidature factuelle : analyse, exigences prouvées,
Score PAI explicable, CV ciblé, lettre, PDF relu comme par un ATS, pack versionné.
Règle d'or : **aucune affirmation sans fait source**. Priorités : factualité > fiabilité > parsing > pertinence >
qualité du document > automatisation.

## Vue d'ensemble

```
 Navigateur ── HTTPS ──▶ Cloudflare ── tunnel nommé ──▶ serveur (projet Docker « pai »)
                                                         │
          ┌──────────────────────────────────────────────┼─────────────────────────────────────────┐
          │ pai_web : FastAPI — interface PAI Studio, /api, /v1, connexion, état du système          │
          │ pai_worker : file de jobs (packs : CV, lettre, PDF via Chromium)                         │
          │ pai_db : PostgreSQL 16 (réseau interne, sans Internet)                                   │
          │ pai_ollama : IA locale (optionnelle)        pai_cloudflared : tunnel (optionnel)          │
          └──────────────────────────────────────────────────────────────────────────────────────────┘
 JobAgent (projet séparé) ── /api (clé d'API, idempotence) ──▶ PAI ── pack ──▶ JobAgent
```

PAI Studio (l'interface) est une seule page servie par le serveur ; la même page existe en artefact claude.ai,
facultatif : PAI ne dépend ni de claude.ai, ni d'un compte Claude, ni d'une clé d'API.

## Couches

```
 entrées ─► ingestion ─► moteur ATS (déterministe) ─► moteur de contenu ─► moteur de design ─► validation ─► pack
 texte      netfetch     analyse, exigences,           faits liés ligne      gabarits         relecture ATS   versions,
 lien       (anti-SSRF)  preuves, Score PAI            à ligne (+ IA         (HTML/CSS ou      du PDF réel,    fichiers,
 PDF/HTML/                                             routée)               pdfmake)          correction      trace
 DOCX
                         ▲                              ▲
                         │ règles versionnées           │ routeur IA : aucune / petit modèle local / grand modèle
                         │ rules/, sector_profiles/,    │ local / externe optionnel ; cache par empreinte ;
                         │ design_profiles/, prompts/   │ toute sortie repasse par le validateur de faits
```

## Modules (`pai/`)

| Module | Rôle |
|---|---|
| `ingest.py`, `netfetch.py` | offre texte / lien / PDF / HTML (JSON-LD JobPosting) / DOCX ; lecture d'URL anti-SSRF, causes d'échec précises |
| `analyzer.py`, `matching.py`, `strategy.py` | analyse déterministe de l'offre, correspondance, positionnements A/B/C |
| `ats/` | moteur ATS : `parser` (lecture d'un CV), `requirements` (classes MUST/IMPORTANT/NICE/CONTEXT et preuves PROUVÉ/PLAUSIBLE/NON PROUVÉ), `lexicon` + `rules/skill_synonyms.yaml`, `rules/taxonomy_fr.yaml` (synonymes, taxonomie métier française), `semantic` (embeddings locaux, jamais une preuve), `scoring` + `report` (Score PAI et dimensions), `scanner` (PDF : deux lectures d'ATS, contrôles OK/WARNING/ERROR, rien de perdu / rien d'ajouté), `variants`, `corpus` (TOP 20/40 seulement avec assez d'offres), `changes` (avant / après / raison / preuve), `cvimport` |
| `cv_architect.py`, `letter.py`, `questions.py` | moteur de contenu : CV et lettre à partir des faits, réponses (BLOCKED sans preuve) |
| `render.py`, `pdf_qa.py` | moteur de design serveur : HTML/CSS → Chromium → PDF ; contrôle du PDF |
| `claims.py`, `critic.py` | validateur claim → evidence (déterministe), critique |
| `pipeline.py`, `pack.py` | orchestration, boucle CV → PDF → relecture → correction (3 passes au plus), pack ZIP |
| `ai/` | `hardware` (détection réelle), `registry` (modèles locaux), `selfeval` (auto-évaluation, porte de vérité), `router` (niveau par tâche et profil eco / balanced / quality), `setup` |
| `providers/` | `AIProvider`, Ollama natif, compatibles OpenAI (OpenAI, Gemini, Mistral, local), Claude, `NullProvider`, `CachedProvider` |
| `obs.py` | journaux structurés : request_id, job_id, étape, durée, fournisseur, modèle, cache — jamais de contenu |
| `api/` | `public.py` (`/api`), `v1.py` (`/v1` historique + passerelle du Studio), `auth.py`, `security.py` (sessions, CSRF, CSP, IP derrière Cloudflare), `jobs.py` (file idempotente), `settings_ai.py` |
| `db/` | SQLAlchemy 2 + Alembic : générations immuables, instantanés de profil, appels IA, jobs, packs |
| `benchmark.py`, `realbench.py` | régression (13 offres fictives) et offres réelles (hors Git) |

Hors paquet : `web/studio/` (interface : `engine.js` et `ats.js` = moteur JS en parité testée avec Python,
`app/*.js` = écrans, `server_shim.js` = pont vers l'API du serveur), `deploy/` (entrypoint, mise à jour avec
retour arrière, sauvegarde / restauration chiffrées, test de fumée), `migrations/`, `docker-compose.yml`.

## Une interface, deux branchements

PAI Studio ne connaît qu'une interface (`db`, `sample`, `downloads`). Sur le serveur, `server_shim.js` les
branche sur `/v1/store` (PostgreSQL), `/v1/ai/complete` (routeur IA du serveur, cache, plafonds) et le
téléchargement navigateur ; le moteur ATS s'exécute dans la page (`ats.js`) et la relecture du PDF passe par
le scanner du serveur (`/api/cv/validate`). Sur claude.ai, ce sont les capacités de la plateforme.

## Parité Python ↔ JavaScript

Le moteur existe en Python (serveur, API, JobAgent) et en JavaScript (interface). Les listes et règles sont
exportées depuis Python à la construction de la page ; des fichiers « golden » (`tests/golden/`) imposent des
résultats identiques (analyse, CV, exigences, mots-clés, dimensions, Score PAI, changements) sur les 13 offres.

## Données

Contenu généré immuable et versionné (`application_id`, `version_id`, empreintes de l'offre et de l'analyse,
version du profil, gabarit, date) ; suppression douce uniquement. Faits typés avec statut (CONFIRMED, IMPORTED,
INFERRED, UNVERIFIED, FORBIDDEN), source, provenance, confiance. Profil non validé → documents « BROUILLON ».

## Sécurité

Voir `SECURITY.md` (secrets, sessions, anti-SSRF, en-têtes, IA, infrastructure, garde-fous de CI).

## Séparation JobAgent

Aucun code, port, base, réseau ou secret partagé. JobAgent appelle `/api` avec une clé à droits limités ;
détails : `docs/jobagent-integration.md`.
