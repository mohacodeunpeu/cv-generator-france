# API PAI `/v1`

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

## Contrat PAI → JobAgent (résultat d'une génération)

```json
{
  "generation_id": "pack_2c9f1a7be3d4",
  "status": "DRAFT | FINAL",
  "mode": "STANDARD",
  "provider": "claude | openai | local | null",
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
| POST | `/v1/ai/complete` | generate | passerelle IA de l'interface (plafond de coût journalier) |
| GET/PUT/DELETE | `/v1/store/doc?path=` | read / admin | magasin de documents de l'interface |
| GET | `/v1/store/query?collection=` | read | lecture d'une collection du magasin |
| GET | `/health` | — | santé (sans données) |

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
| 422 | offre trop courte ou invalide, réponse IA sans JSON |
| 429 | trop de tentatives de connexion, ou plafond de coût IA atteint |
| 502 / 503 | fournisseur IA en erreur / aucun fournisseur (mode dégradé) |

Les générations continuent sans IA si le fournisseur échoue ou si le plafond est atteint : chaque étape bascule
sur sa voie déterministe, et le journal du pack l'indique.
