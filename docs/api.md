# API PAI : `/api` (contrat recommandé) et `/v1` (historique, conservée)

`/api` est le contrat simple et stable pour l'interface, **JobAgent** et les scripts. `/v1` reste disponible sans
changement (compatibilité). **Aucune route n'exige d'IA ni de clé payante** : sans IA, les réponses viennent des voies
déterministes (mode « SANS IA »). **PAI ne postule jamais et n'envoie aucun message.**

## `/api` en bref

| Méthode | Route | Droit | Rôle |
|---|---|---|---|
| GET | `/api/health` | — | vivant (aucune donnée interne) |
| GET | `/api/ready` | — | prêt : base, migrations, stockage, configuration (`200` ou `503`) ; l'IA n'est jamais bloquante |
| POST | `/api/jobs/ingest` | analyze | lire une offre : texte, URL, **fichier PDF / HTML / DOCX / texte** ; rien n'est enregistré |
| POST | `/api/jobs/analyze` | analyze | analyse + exigences classées et prouvées + Score PAI provisoire ; **cache** (`"cache": "hit"/"miss"`) |
| POST | `/api/cv/analyze` | analyze | **mode A** (CV seul) ou **mode B** (CV + offre) ; CV en PDF, DOCX ou texte |
| POST | `/api/cv/optimize` | analyze | CV ciblé tracé (sans PDF) + changements AVANT / APRÈS / RAISON / PREUVE + Score PAI |
| POST | `/api/cv/generate` | generate | synchrone : CV + lettre, PDF relus (scanner ATS), Score PAI complet, lien du CV |
| POST | `/api/cv/validate` | analyze | scanner ATS d'un PDF (OK / WARNING / ERROR) ; avec `source_text` : relecture « rien de perdu » |
| POST | `/api/letter/generate` | generate | synchrone : lien de la lettre (même version que le CV) |
| POST | `/api/application/prepare` | generate | pack complet ; **asynchrone** par défaut (`202` + `job_id`), `?wait=true` = synchrone ; `Idempotency-Key` |
| GET | `/api/jobs/{job_id}` | read | état du job et résultat (identifiants de version, Score PAI, liens signés) |
| GET | `/api/application/{id}` | read | une version (`pack_…`) ou une candidature (`app_…` : toutes ses versions, la plus récente d'abord) |
| GET | `/api/corpus` | read | corpus métier (TOP 20 / 40 seulement au-delà de 10 / 25 offres, volume toujours affiché) |
| GET | `/api/system/status` | read | PAI, ATS, API, base, IA, modèle local, cache, accès public, JobAgent → OK / WARNING / ERROR |
| GET | `/api/ai/usage?days=30` | read | appels IA par fournisseur / modèle / niveau, cache hit / miss, jetons, temps, coût |

**Entrées directes** — JSON ou `multipart/form-data` :

| Champ | Sens |
|---|---|
| `offer_text` / `offer_url` / `offer_file` | l'offre (priorité : fichier, puis texte, puis URL) ; `title` (ou `role`), `company` en option |
| `cv_file` / `cv_text` | le CV pour `/api/cv/analyze` et `/api/cv/validate` |
| `*_b64` + `*_filename` | fichier en base64 dans un corps JSON (ex. `offer_file_b64`, `offer_filename`) |
| `ai` | `auto` (défaut : le routeur décide) ou `none` (jamais d'IA) |
| `mode`, `questions`, `source`, `offer_id`, `candidate_id` | pack : `STANDARD` / `DEEP`, questions du formulaire, origine (`jobagent`), identifiants de l'appelant |

Fichiers : 8 Mo au plus. Chaque réponse porte l'en-tête `X-Request-ID` (repris de la requête s'il est sûr) : il relie
la requête, ses jobs et ses appels IA dans le journal, sans aucun contenu.

**Erreurs** : `{"detail": {"code": "…", "message": "…"}}`, message affichable. Lecture d'URL : `login_walled`,
`auth_required`, `forbidden`, `anti_bot`, `not_found`, `rate_limited`, `unavailable`, `js_required`, `timeout`,
`too_large`, `bad_url`, `blocked_address`, `unreadable` — le message dit **pourquoi le serveur PAI** n'a pas pu lire la
page (« Le serveur PAI n'a pas pu récupérer cette URL (HTTP 403) : le site bloque les lectures automatiques… ») et
propose le texte collé ou le PDF. Autres : `missing_offer`, `missing_cv`, `missing_pdf`, `no_text` (PDF image),
`unsupported_format`, `too_large`, `bad_json`, `no_profile`.

### Exemples

```bash
H='Authorization: Bearer pai_…'
# Offre depuis un PDF, analyse sans IA
curl -s -H "$H" -F offer_file=@offre.pdf -F ai=none https://<serveur>/api/jobs/analyze
# CV seul (mode A)
curl -s -H "$H" -F cv_file=@mon_cv.pdf https://<serveur>/api/cv/analyze
# CV + offre (mode B) : preuves tirées du CV fourni
curl -s -H "$H" -F cv_file=@mon_cv.pdf -F offer_url=https://exemple.fr/offre/42 https://<serveur>/api/cv/analyze
# Pack complet pour JobAgent (asynchrone, idempotent)
curl -s -H "$H" -H 'Idempotency-Key: jobagent-offre-42' -H 'Content-Type: application/json' \
     -d '{"offer_text": "…", "company": "Nordlys", "source": "jobagent"}' https://<serveur>/api/application/prepare
# → 202 {"job_id": "job_…", "status": "PENDING", "poll": "/api/jobs/job_…"}
```

### Réponse d'un pack (`/api/jobs/{id}` → `result`, `/api/cv/generate`, `?wait=true`)

```json
{
  "application_id": "app_3f2a9c1d7e44",
  "version_id": "pack_2c9f1a7be3d4",
  "status": "DRAFT",
  "pai_score": 86,
  "ats": {
    "score": {"value": 86, "complete": true, "missing": [], "label": "Score PAI",
              "disclaimer": "Score interne PAI … ni le score d'un ATS réel ni une probabilité d'embauche."},
    "dimensions": [{"id": "parsing", "label": "Format & parsing", "value": 100, "available": true, "summary": "…", "weight": 12},
                   {"id": "matching", "label": "Matching offre", "value": 81, "…": "…"}],
    "requirements": {"proven": 11, "plausible": 4, "unproven": 3, "context": 1},
    "unproven_must": [],
    "keywords": [{"term": "HubSpot", "status": "PROUVÉ", "in_cv": true, "priority": "REQUIRED"},
                 {"term": "Salesforce", "status": "NON_PROUVÉ", "in_cv": false, "priority": "NICE"}],
    "variant": {"id": "BUSINESS_DEVELOPER", "label": "Business Developer", "why": "intitulé …"},
    "passes": [{"pass": 1, "status": "OK", "score": 100, "errors": []}]
  },
  "application_pack": {"cv_pdf": "https://<serveur>/v1/files/<jeton signé>", "letter_pdf": "…", "zip": "…", "expires_in_seconds": 300},
  "letter_text": "Madame, Monsieur,\n\n…\n\nCamille Test",
  "versions": {"application_id": "app_…", "offer_v": "…", "profile_v": "…", "analysis_v": "…", "template": "hybrid_modern",
               "cv_v": "…", "letter_v": "…", "engine_v": "…", "prompt_v": "…", "rules_v": "…", "timestamp": "…"},
  "risks": ["…"], "next_action": "…", "…": "champs /v1 inchangés (strategy, match, questions, quality_scores…)"
}
```

`letter_text` : la lettre validée en texte simple (formule d'appel, paragraphes, signature : les mêmes phrases que le
PDF, aucune autre), pour un formulaire de candidature ou un message au recruteur.

Le ZIP du pack contient : CV et lettre (PDF), `pack.json`, `pack.md` (Score PAI, exigences prouvées / possibles / non
prouvées, changements), `versions.json`, `analyse_ats.json`. « Quel CV ai-je envoyé ? » :
`GET /api/application/app_…` liste toutes les versions de la candidature avec leurs fichiers.

---

# API historique `/v1`

API versionnée du serveur PAI, pensée d'abord pour le futur JobAgent (« API first »).
Documentation interactive : `https://<serveur>/docs` (protégée, droit `read`).

**PAI ne postule jamais et n'envoie aucun message** : l'API renvoie des documents à relire.

## Authentification

| Mode | Usage | Détail |
|---|---|---|
| Clé d'API | scripts, JobAgent | `Authorization: Bearer pai_…` ; créée par `python -m pai api-key create NOM --scopes …`, stockée hachée, révocable |
| Session | interface web | cookie `pai_session` (HttpOnly, Secure, SameSite=strict) + en-tête `X-CSRF-Token` pour toute écriture |

Droits d'une clé : `read`, `analyze`, `generate`, `feedback`, `outcomes`, `benchmark`, `admin`.
Réponses : `401` sans authentification valide, `403` si un droit manque ou si le CSRF est absent.

## Contrat JobAgent → PAI

Corps accepté par les routes d'analyse et de génération (tous les champs sont facultatifs sauf l'offre) :

```json
{
  "offer_text": "Texte complet de l'offre (80 à 60 000 caractères)",
  "offer_url": "https://… (page publique ; jamais derrière un login)",
  "role": "Business Developer Junior",
  "company": "Nordlys",
  "offer_id": "id côté JobAgent",
  "candidate_id": "id côté JobAgent",
  "source": "jobagent",
  "profile_version": "v3-…",
  "context": {"canal": "linkedin"},
  "mode": "QUICK | STANDARD | DEEP",
  "questions": "Une question du formulaire par ligne"
}
```

`offer_url` sans `offer_text` : la page est lue avec la même lecture sûre que `POST /v1/ingest/url` (échec → `422`,
`detail` = message). L'interface, elle, lit d'abord l'URL, fait relire le texte, puis envoie `offer_text`.

## Contrat PAI → JobAgent (résultat d'une génération)

```json
{
  "generation_id": "pack_2c9f1a7be3d4",
  "status": "DRAFT | FINAL",
  "mode": "STANDARD",
  "provider": "claude | gemini | mistral | openai | local | null",
  "strategy": {"title": "…", "hook": "…", "ats_mode": "HYBRID", "design_profile": "hybrid_modern", "photo_mode": "OFF", "…": "…"},
  "match": {"match": 91.7, "quality": 100.0, "risk": 4.2, "scores": {"skills": 100.0, "…": 0}},
  "recommended_cv": {"design_profile": "hybrid_modern", "ats_mode": "HYBRID"},
  "cv_version": "a1b2c3d4e5",
  "letter_version": "f6e5d4c3b2",
  "questions": [{"question": "Prétentions salariales ?", "type": "SALARY", "answer": "", "fact_ids": [], "confidence": "BLOCKED", "ask_user": "…"}],
  "application_pack": {
    "cv_pdf": "https://<serveur>/v1/files/<jeton signé>",
    "letter_pdf": "https://<serveur>/v1/files/<jeton signé>",
    "zip": "https://<serveur>/v1/files/<jeton signé>",
    "expires_in_seconds": 300
  },
  "quality_scores": {"factuality_cv": 100.0, "factuality_letter": 100.0, "match": 91.7, "points": {"total": 18, "events": [{"event": "…", "points": 5, "reason": "…"}]}},
  "risks": ["…"],
  "next_action": "Valider le Master Profile … puis relire et postuler vous-même.",
  "missing_profile_data": ["…"],
  "versions": {"offer_v": "…", "profile_v": "…", "cv_v": "…", "letter_v": "…", "engine_v": "1.0.0", "prompt_v": "…", "rules_v": "…"},
  "cost_eur": 0.0
}
```

`status` reste `DRAFT` tant que le Master Profile n'est pas validé ou qu'une ligne n'est pas prouvée à 100 %.
Les liens de fichiers sont signés, expirent vite (`FILE_URL_TTL_SECONDS`) et ne contiennent aucune donnée personnelle.

## Routes

| Méthode | Route | Droit | Rôle |
|---|---|---|---|
| POST | `/v1/ingest/url` | analyze | lire une offre depuis une URL publique (lecture sûre ; rien n'est enregistré) |
| POST | `/v1/analyze-job` | analyze | analyse de l'offre + matching (sans document) |
| POST | `/v1/generate-strategy` | analyze | positionnements A/B/C et stratégie retenue |
| POST | `/v1/generate-cv` | generate | génération synchrone ; renvoie le lien du CV |
| POST | `/v1/generate-letter` | generate | génération synchrone ; renvoie le lien de la lettre |
| POST | `/v1/generate-application-pack` | generate | **asynchrone** (file de jobs), `202` + `job_id` ; en-tête `Idempotency-Key` |
| GET | `/v1/jobs/{job_id}` | read | `PENDING / RUNNING / DONE / FAILED`, progression, résultat |
| GET | `/v1/jobs` | read | 50 derniers jobs |
| GET | `/v1/profile` | read | Master Profile courant (+ `tag` de version) |
| POST | `/v1/profile/import` | admin | importer un profil JSON (export PAI Studio) |
| POST | `/v1/profile/validate` | admin | valider (409 tant qu'un conflit reste en REVIEW) |
| GET | `/v1/versions` | read | versions moteur / prompts / règles / profil + 20 dernières générations |
| POST | `/v1/feedback` | feedback | retour 👍 😐 👎 sur un élément d'une génération |
| POST | `/v1/outcomes` | outcomes | résultat réel : `applied, viewed, answered, response, interview, offer, rejected, no_response, withdrawn` |
| POST | `/v1/benchmark/run` | benchmark | benchmark déterministe asynchrone (ancien vs PAI) |
| GET | `/v1/files/{jeton}` | lien signé | téléchargement (PDF, ZIP) ; `403` si expiré ou modifié |
| POST | `/v1/ai/complete` | generate | passerelle IA de l'interface (fournisseur effectif, plafond de coût journalier) |
| GET | `/v1/settings/ai` | read | réglages IA : fournisseur actif, mode, modèle et indice de clé par fournisseur (jamais la clé) |
| PUT | `/v1/settings/ai` | admin | changer le fournisseur actif, une clé (chiffrée au repos), un modèle, une URL de base |
| POST | `/v1/settings/ai/test` | admin | tester la connexion d'un fournisseur (petit appel réel, journalisé) |
| GET | `/v1/status` | read | version du moteur, mode IA (`REMOTE / LOCAL / DEGRADED`), fournisseur actif, base |
| GET/PUT/DELETE | `/v1/store/doc?path=` | read / admin | magasin de documents de l'interface |
| GET | `/v1/store/query?collection=` | read | lecture d'une collection du magasin |
| GET | `/health` | — | santé (sans données) |

## Offre depuis une URL : `POST /v1/ingest/url`

Route appelée par l'interface quand l'utilisateur colle un lien. **Lecture sûre** (protection SSRF) : `http`/`https`
et ports 80/443 seulement, pas d'identifiants dans l'URL ; toute adresse résolue doit être publique (réseaux privés,
boucle locale, lien local dont `169.254.169.254`, CGNAT, multicast, réservées… refusés, y compris écrits en décimal,
octal ou hexadécimal) ; redirections suivies une à une et revalidées (5 au plus) ; 3 Mo au plus ; un seul délai de
15 s pour tout le parcours ; adresse réellement connectée revérifiée (DNS rebinding) ; proxys de l'environnement ignorés.
Les sites qui exigent une connexion (LinkedIn, Indeed, Glassdoor…) sont refusés **sans aucun appel réseau**, y compris
derrière un lien court (chaque redirection est contrôlée avant d'être suivie).

Contenu : données structurées schema.org `JobPosting` (JSON-LD) d'abord — titre, entreprise, lieu, contrat, salaire,
date, puis description —, sinon texte principal de la page ; un PDF est lu comme un PDF importé. Rien n'est inventé
ni enregistré : l'interface montre le texte à relire, puis lance l'analyse avec `offer_text`.

```bash
curl -s https://pai.example.fr/v1/ingest/url -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"url": "https://jobs.example.fr/offres/business-developer"}'
```
```json
{"offer": {
  "id": "off_3f2a9c81d0e4",
  "text": "Business Developer Junior (H/F)\nEntreprise : Acme SaaS\nLieu : Paris (75009), FR\nContrat : Temps plein, CDI\nSalaire : 40 000 – 45 000 EUR par an\nPubliée le : 2026-09-20\n\nAcme SaaS édite un logiciel…",
  "title_hint": "Business Developer Junior (H/F)",
  "company_hint": "Acme SaaS",
  "source_url": "https://jobs.example.fr/offres/business-developer",
  "text_hash": "3f2a9c81d0e47b65",
  "source_type": "url"
}}
```

`source_type` : `url` (page HTML) ou `pdf` (PDF téléchargé) ; `source_url` : adresse finale, après redirections.
Échec → `422` avec `{"detail": {"code": "…", "message": "…"}}` (message en français, affichable tel quel) :

| `code` | Sens |
|---|---|
| `login_walled` | site fermé (LinkedIn, Indeed, Glassdoor…), directement ou par redirection : coller le texte ou importer le PDF |
| `bad_url` | URL invalide, schéma autre que http/https, port autre que 80/443, identifiants dans l'URL, domaine introuvable |
| `blocked_address` | l'adresse, une redirection ou la connexion réelle mène à un réseau privé, local ou réservé |
| `too_large` | page de plus de 3 Mo (décompression comprise) |
| `timeout` | le site met plus de 15 s à répondre |
| `http_error` | erreur HTTP (403, 404, 5xx…), site injoignable ou plus de 5 redirections |
| `unreadable` | trop peu de texte lisible (page construite par script), format non pris en charge, PDF sans texte |

## Réglages IA : `/v1/settings/ai`

Fournisseurs interchangeables : `claude`, `gemini`, `mistral`, `openai`, `local` (Ollama), `null` (désactivé).
Fournisseur effectif — utilisé par les packs, le worker et `/v1/ai/complete` : réglages enregistrés en base →
environnement (`PAI_AI_PROVIDER`, clés) → `default_provider` de `config/models.yaml` → `null`. Base indisponible →
environnement, sans erreur.

`GET /v1/settings/ai` (droit `read`) — aucune clé n'est jamais renvoyée, seulement ses 4 derniers caractères :

```json
{
  "active": "gemini",
  "mode": "REMOTE",
  "providers": [
    {"id": "claude", "label": "Claude", "configured": false, "key_hint": "", "model": "claude-sonnet-5", "base_url": "", "source": "none"},
    {"id": "gemini", "label": "Gemini", "configured": true, "key_hint": "••••a1b2", "model": "gemini-2.5-flash",
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "source": "db"},
    {"id": "mistral", "label": "Mistral", "configured": false, "key_hint": "", "model": "mistral-large-latest",
     "base_url": "https://api.mistral.ai/v1", "source": "none"},
    {"id": "openai", "label": "OpenAI", "configured": false, "key_hint": "", "model": "", "base_url": "https://api.openai.com/v1", "source": "none"},
    {"id": "local", "label": "Local (Ollama)", "configured": false, "key_hint": "", "model": "", "base_url": "http://localhost:11434/v1", "source": "none"},
    {"id": "null", "label": "Désactivé", "configured": true, "key_hint": "", "model": "", "base_url": "", "source": "none"}
  ]
}
```

- `mode` : `REMOTE` (claude, gemini, mistral ou openai configuré), `LOCAL` (local configuré), sinon `DEGRADED`.
- `configured` : utilisable tout de suite (clé, plus modèle pour openai ; modèle pour local ; toujours vrai pour `null`).
- `source` : `db` (Réglages → IA), `env` (variables d'environnement) ou `none`.
- `model` : pour Claude, le modèle imposé s'il y en a un, sinon le modèle de rédaction de `config/models.yaml`
  (les modèles restent choisis par tâche).

`PUT /v1/settings/ai` (droit `admin`) — tous les champs sont facultatifs ; réponse : même forme que `GET` :

| Champ | Rôle |
|---|---|
| `active` | fournisseur actif (un des 6 identifiants) |
| `provider` | fournisseur à régler (obligatoire avec les champs ci-dessous) |
| `api_key` | nouvelle clé, chiffrée au repos (Fernet, clé dérivée de `SECRET_KEY`) ; vide = inchangée ; claude, gemini, mistral, openai |
| `model` | modèle (vide = retour à l'environnement ou au défaut) ; pour Claude, un seul modèle pour toutes les tâches |
| `base_url` | `openai` et `local` uniquement, `http(s)`, sans identifiants ni paramètres ; la changer efface la clé enregistrée |
| `clear_key` | `true` : efface la clé enregistrée (incompatible avec `api_key`) |

```bash
curl -s -X PUT https://pai.example.fr/v1/settings/ai -H "Authorization: Bearer $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"active": "gemini", "provider": "gemini", "api_key": "…"}'
```

Entrée invalide → `422` `{"detail": {"code": "invalid_argument", "message": "…"}}` (la clé n'est jamais recopiée).
Chaque modification est tracée dans `audit_log` (champs modifiés, jamais de secret). Une clé de l'environnement n'est
jamais envoyée à une URL de base modifiée depuis l'interface. Changer `SECRET_KEY` rend les clés enregistrées
illisibles : elles sont ignorées et sont à ressaisir.

`POST /v1/settings/ai/test` (droit `admin`), corps `{"provider": "gemini"}` : petit appel réel (tâche `extract`,
« Réponds uniquement par OK. ») avec les réglages enregistrés, hors cache et hors plafond de coût, journalisé dans
`llm_calls`. Une erreur du fournisseur donne `ok: false` avec un message court, jamais une erreur 500.

```json
{"ok": true, "latency_ms": 412, "model": "gemini-2.5-flash", "error": null}
{"ok": false, "latency_ms": 180, "model": "gemini-2.5-flash", "error": "gemini : HTTP 401 (clé refusée)"}
```

`GET /v1/status` (droit `read`) :

```json
{"engine_v": "1.0.0", "ai_mode": "REMOTE", "active_provider": "gemini", "db": "ok"}
```

## Exemples

```bash
KEY=pai_…   # python -m pai api-key create jobagent --scopes read,analyze,generate,outcomes

# Analyse
curl -s https://pai.example.fr/v1/analyze-job -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"offer_text": "…texte complet de l'"'"'offre…"}'

# Pack asynchrone, idempotent (même clé = même job, jamais de doublon)
curl -s https://pai.example.fr/v1/generate-application-pack -H "Authorization: Bearer $KEY" \
  -H 'Idempotency-Key: jobagent-offre-4521' -H 'Content-Type: application/json' \
  -d '{"offer_text": "…", "questions": "Pourquoi nous ?\nDisponibilité ?"}'
# → 202 {"job_id": "job_…", "status": "PENDING", "poll": "/v1/jobs/job_…"}

curl -s https://pai.example.fr/v1/jobs/job_… -H "Authorization: Bearer $KEY"   # jusqu'à DONE

# Résultat réel remonté par JobAgent (les statistiques n'apparaissent qu'à partir de 5 cas, A5)
curl -s https://pai.example.fr/v1/outcomes -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"generation_id": "pack_…", "stage": "interview", "occurred_at": "2026-10-02T10:00:00"}'
```

## Erreurs

| Code | Sens |
|---|---|
| 400 | entrée invalide (chemin du magasin, image, prompt vide) |
| 401 | non authentifié |
| 403 | droit manquant, CSRF invalide, lien de fichier expiré ou modifié |
| 404 | génération, job ou fichier introuvable |
| 409 | aucun profil, ou validation refusée (conflit en REVIEW) |
| 413 | document > 256 Kio ou prompt > 64 Kio |
| 422 | offre trop courte ou invalide, réponse IA sans JSON, URL d'offre refusée ou illisible (`detail.code`), réglage IA invalide |
| 429 | trop de tentatives de connexion, ou plafond de coût IA atteint |
| 502 / 503 | fournisseur IA en erreur / aucun fournisseur (mode dégradé) |

Les générations continuent sans IA si le fournisseur échoue ou si le plafond est atteint : chaque étape bascule
sur sa voie déterministe, et le journal du pack l'indique.
