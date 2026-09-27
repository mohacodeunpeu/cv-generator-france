# Architecture — PAI (Personal Application Intelligence)

PAI transforme une offre (texte, URL publique, PDF) en **Application Pack** : analyse, matching,
stratégie, CV PDF, lettre, réponses aux questions, risques et prochaine action.
Règle d'or : **aucune affirmation sans fait source** (claim → evidence binding, section A2).

## Deux surfaces, un seul moteur de règles

```
                    ┌──────────────── règles versionnées (hors code) ────────────────┐
                    │ rules/  sector_profiles/  design_profiles/  brand/  prompts/   │
                    │ config/models.yaml   profiles/confirmations.yaml               │
                    └───────────────┬───────────────────────────────┬────────────────┘
                                    │                               │ (build : web/build_studio.py)
            ┌───────────────────────▼──────────┐       ┌────────────▼─────────────────────────┐
            │ Serveur PAI (Python 3.12)         │       │ PAI Studio (page claude.ai privée)   │
            │ FastAPI /v1 · SQLAlchemy/Alembic  │       │ IA : capacité `sample` (Claude)       │
            │ PostgreSQL 16 · worker de jobs    │       │ Données : capacité `db` (privée)      │
            │ Claude / OpenAI / local / Null    │       │ PDF : pdfmake (texte vectoriel)       │
            │ PDF : HTML/CSS → Chromium         │       │ Validateur claim→evidence en JS       │
            │ docker compose « pai » + Caddy    │       │ (parité testée avec le Python)        │
            └───────────────────────────────────┘       └───────────────────────────────────────┘
```

- **PAI Studio** est l'URL utilisable dès maintenant : page privée sur claude.ai (connexion au compte
  Claude = login), l'IA passe par le compte Claude de l'utilisateur (aucune clé API), les données restent
  dans la base privée de l'artefact.
- **Le serveur PAI** est le produit auto-hébergeable (Oracle 24/7) et l'API pour le futur JobAgent.
  Il tourne aussi sans IA (mode dégradé) : profil, versions, rendu PDF, validation, scoring, pack.

## Pipeline (identique sur les deux surfaces)

```
ingest ─► analyse ─► match ─► stratégie A/B/C ─► CV (contenu lié aux faits)
   │         │          │           │                 │
 texte     déterm.   déterm.     IA/déterm.     validateur déterministe ──► rejet → réécriture (2×) → suppression
 figé +    + IA      + IA        + garde-fous   juge IA d'exagération
 hash                                            critique (7 juges) ─► correction (1 à 3 cycles)
                                                 rendu PDF ─► PDF QA (pages, marges, contraste, ATS)
                                                      │
                               lettre (phrases typées) ─► validateur ─► contrôles lettre
                               questions (BLOCKED si aucun fait)
                                                      │
                               Application Pack figé (versions offer/profile/cv/letter/answers/engine/prompt/rules)
```

Modes : QUICK (analyse + match + stratégie), STANDARD (pipeline complète, 1 cycle de critique),
DEEP (3 variantes, jusqu'à 3 cycles, QA visuelle).

## Modules (`pai/`)

| Module | Rôle |
|---|---|
| `schemas.py` | Modèles Pydantic partagés (faits, offre, analyse, match, stratégie, CV, lettre, pack) |
| `profile.py`, `bootstrap.py` | Master Profile versionné, statuts, validation, import/export JSON/CSV/MD ; bootstrap legacy + confirmations |
| `ingest.py` | Offre texte/URL/PDF, texte figé + hash (doublons) |
| `analyzer.py` | Extraction déterministe (contrat, lieu, salaire, langues, outils, MUST/IMPORTANT/NICE, secteur) + fusion IA |
| `matching.py` | 12 sous-scores, MATCH / QUALITY / RISK, couverture des mots-clés par les faits |
| `strategy.py` | Positionnements A/B/C, garde-fous (photo selon pays, design ATS) |
| `cv_architect.py` | Plan de contenu (voie déterministe et voie IA), ajustement 1 page |
| `claims.py` | **Validateur claim → evidence** (nombres, dates, noms propres, diplômes, outils, langues/niveaux, responsabilité, termes interdits) |
| `critic.py` | Critique déterministe + intégration du jury IA, grille de points |
| `letter.py`, `questions.py` | Lettre à phrases typées ; réponses HIGH/MEDIUM/LOW/BLOCKED |
| `render.py`, `pdf_qa.py` | HTML/CSS → Chromium → PDF (polices embarquées) ; QA PNG + extraction ATS |
| `pipeline.py`, `pack.py` | Orchestration, repli déterministe, pack ZIP (PDF + JSON + MD) |
| `providers/` | `ClaudeProvider`, `OpenAICompatProvider` (OpenAI, Ollama), `NullProvider`, `CachedProvider` (cache + rejeu) |
| `db/`, `api/` | SQLAlchemy 2 + Alembic, FastAPI `/v1`, auth, jobs |

## Données

Tout contenu généré est immuable et versionné ; suppression douce uniquement.
Les faits portent un statut (CONFIRMED, IMPORTED, INFERRED, UNVERIFIED, FORBIDDEN), une source,
une provenance et une confiance. Tant que le profil n'est pas validé, les documents portent
« BROUILLON — PROFIL NON VALIDÉ » et ne peuvent pas passer en FINAL.

Les expériences, compétences, diplômes, langues et certifications sont des **faits typés** (`kind`)
plutôt que des tables séparées : un seul mécanisme de preuve, moins de concepts.

## Séparation JobAgent

Aucune dépendance au code, aux ports, à la base, aux secrets ou au réseau du JobAgent.
Projet Docker distinct (`pai`, préfixe `pai_`), base distincte, limites CPU/RAM.
Futur contrat d'API décrit dans `docs/api.md`.
