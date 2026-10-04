# Intégration JobAgent ↔ PAI

Deux projets distincts qui collaborent par API, sans rien partager d'autre (code, base, réseau Docker, secrets).

| Projet | Spécialité | Dépôt |
|---|---|---|
| **JobAgent** | recherche, collecte, filtrage, orchestration et envoi des candidatures | `hellowork-automation-pro` |
| **PAI** | analyse d'offre, exigences prouvées, Score PAI, CV ciblé, lettre, validation du PDF, pack | `cv-generator-france` |

**PAI ne postule jamais et n'envoie rien** : il rend des documents. L'envoi reste le métier de JobAgent.

## Flux

```
JobAgent : offre détectée → filtre → lecture de l'annonce
   │
   │  POST /api/application/prepare   (texte de l'annonce, sinon son lien ; Idempotency-Key ; X-Request-ID)
   ▼
PAI : analyse → exigences PROUVÉ / POSSIBLE / NON PROUVÉ → variante de CV → CV ciblé → lettre
      → PDF → relecture ATS (rien de perdu, rien d'ajouté) → correction bornée → pack versionné
   │
   │  GET /api/jobs/{id} (jusqu'à DONE) → CV PDF (lien signé), letter_text, Score PAI, version
   ▼
JobAgent : choisit les documents selon PAI_MODE → suite de son pipeline (formulaire, dossier, trace)
```

## Côté JobAgent (`services/pai.py`)

| `PAI_MODE` | Documents envoyés | Rôle de PAI |
|---|---|---|
| `off` (défaut) | ceux de JobAgent | aucun appel |
| `assisted` | ceux de JobAgent | pack rangé dans `queue/pai/<offre>/` pour relecture |
| `auto` | **ceux de PAI** si prêts à temps, `FINAL`, 100 % factuels, à la taille du formulaire ; sinon ceux de JobAgent | rend le pack |

Variables : `JOBAGENT_PAI_URL` (aucune valeur par défaut), `PAI_API_KEY` ou `donnees/secrets/pai_cle`,
`PAI_MODE`, `PAI_ENABLED`, `PAI_REQUIRED` (mode auto : l'offre attend plutôt que de partir avec un autre
document), `PAI_TIMEOUT_S` (90 s).

Robustesse : demande idempotente (même offre, même texte → même pack, repris au passage suivant s'il
n'était pas prêt), nouveaux essais sur réseau coupé / 429 / 5xx, attente bornée, pause de 10 minutes après
3 échecs réseau, fichiers demandés uniquement à l'adresse configurée. La trace de chaque candidature dit
quel moteur a fait les documents et quelle version PAI est partie (`pai_version`, `pai_application`).

Branchement : `core/apply_runner.py` (HelloWork) et `core/ft_run.py` (France Travail), à l'endroit exact où
JobAgent fabriquait déjà son CV et sa lettre. Pull request : `mohacodeunpeu/hellowork-automation-pro#1`
(brouillon ; rien n'est déployé avant sa fusion).

## Côté PAI

- Clé d'API dédiée, droits minimaux : `python -m pai api-key create jobagent --scopes read,analyze,generate`
  (ajouter `outcomes` pour remonter les résultats réels via `/v1/outcomes`).
- Contrat : `docs/api.md` (`/api/application/prepare`, `/api/jobs/{id}`, `/api/application/{id}`) ;
  `letter_text` donne la lettre validée en texte simple pour les formulaires.
- La page **État du système** indique le dernier appel de JobAgent (`source = jobagent`).
- Le pack d'un profil non validé reste `DRAFT` : en mode auto, JobAgent ne l'envoie pas (repli).

## Accès réseau

JobAgent appelle PAI par son nom d'hôte public (tunnel Cloudflare, `docs/deployment.md`). Si Cloudflare Access
protège PAI, JobAgent ajoute un *service token* Access (en-têtes `CF-Access-Client-Id` / `CF-Access-Client-Secret`)
en plus de sa clé d'API PAI.

## Vérifié

- JobAgent : 11 tests du pont contre un faux serveur PAI (modes, replis, pause, idempotence, en-têtes, aucune
  adresse ni clé dans le code) ; suite complète de JobAgent : 534 réussis.
- De bout en bout, vrai serveur PAI (SQLite, profil fictif validé, sans IA) : mode `auto` → pack `FINAL` en 5 s,
  CV PDF de 51 Ko et lettre de 1 022 caractères utilisés ; mode `assisted` → même pack réutilisé, documents
  JobAgent conservés, pack rangé.
