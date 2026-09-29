# PAI — Personal Application Intelligence

PAI transforme une offre d'emploi en **Application Pack** prêt à relire : analyse de l'offre, matching,
stratégie de positionnement, CV PDF d'une page, lettre, réponses aux questions, risques et prochaine action.

**Règle d'or : aucune affirmation sans preuve.** Chaque ligne du CV et de la lettre est liée aux faits du
Master Profile qui la prouvent. Un validateur déterministe rejette tout le reste : chiffres, diplômes, outils,
langues, noms propres ou responsabilités non prouvés, termes interdits. S'y ajoute un juge IA de factualité.
**PAI ne postule jamais et n'envoie rien** : il prépare, vous relisez et vous postulez vous-même.

## Deux façons de l'utiliser

| | PAI Studio (URL claude.ai) | Serveur PAI (auto-hébergé) |
|---|---|---|
| Accès | page privée sur claude.ai, connexion = votre compte Claude | votre serveur (Oracle Cloud, etc.), identifiant + mot de passe |
| IA | votre compte Claude (aucune clé API) | Claude, OpenAI, modèle local (Ollama) ou aucun (mode dégradé) |
| Données | base privée de la page (vous seul) | PostgreSQL 16 sur votre serveur |
| Interface | PAI Studio | **la même** PAI Studio, servie par le serveur |
| API | — | `/v1` pour le futur JobAgent (clés d'API à droits limités) |

Les deux surfaces partagent les mêmes règles, prompts, profils de secteur et de design. Le moteur est écrit
en Python (serveur) et en JavaScript (PAI Studio) ; la parité est vérifiée par des tests communs
(`tests/golden/`).

## Ce que fait le pipeline

1. **Offre** : texte collé, URL publique ou PDF ; texte figé et haché (doublons). Aucune collecte derrière un login.
2. **Analyse** : contrat, lieu, pays, langue, salaire, séniorité, exigences REQUIRED/IMPORTANT/NICE, secteur (11 profils).
3. **Matching** : 12 sous-scores, MATCH / QUALITY / RISK, couverture des mots-clés par des faits prouvés.
4. **Stratégie** : positionnements A/B/C, garde-fous (photo selon le pays, mode ATS, design).
5. **CV** : contenu lié aux faits → validateur → réécriture ciblée (2 essais) ou suppression → critique → rendu PDF → contrôle qualité du PDF (pages, marges, contraste, extraction ATS).
6. **Lettre** et **réponses** : phrases typées, citations exactes de l'offre, questions sans preuve marquées BLOCKED (le salaire n'est jamais inventé).
7. **Pack** figé et versionné (offre, profil, CV, lettre, réponses, moteur, prompts, règles) : PDF + ZIP + JSON.

Tant que le Master Profile n'est pas validé, chaque document porte « BROUILLON — PROFIL NON VALIDÉ » et
ne peut pas passer en FINAL.

## Résultats mesurés

Benchmark déterministe sur 13 offres **SYNTHETIC** (fictives, marquées comme telles), même instrument pour
l'ancien générateur et PAI (texte extrait du PDF, comme un ATS) :

| Critère | Ancien générateur | PAI |
|---|---:|---:|
| Score global | 54,6 | **92,9** |
| Factualité du CV | 0 (MBA dans 13/13 CV, 9 lignes non prouvées par CV) | **100** (0 ligne non prouvée) |
| Factualité de la lettre | 13,6 | **100** |
| Couverture honnête des mots-clés (ceux que le profil prouve) | 91,0 | **97,4** |
| Qualité PDF | 70 | **100** |
| Couverture brute des mots-clés | **76,4** | 71,7 |

L'ancien générateur n'a l'avantage que sur la couverture brute, qu'il obtient en partie avec des mots-clés
non prouvés (bourrage), ce que PAI refuse. Détails et limites : `python -m pai benchmark`, `DECISIONS.md`.
PAI a été mesuré sans IA, c'est-à-dire à son niveau minimum.

## Démarrage rapide

```bash
# Local (Python 3.12)
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && python -m playwright install chromium
python -m pai bootstrap-profile           # Master Profile v1 (hors Git, dans data/)
python -m pai generate benchmark/offers/01_bd_saas_paris.yaml --provider null
python -m pai build-studio --server && python -m pai create-user moi
uvicorn app:app                            # http://localhost:8000

# Serveur (Docker) : voir RUNBOOK.md
cp .env.example .env && docker compose up -d --build
```

## Documentation

- `RUNBOOK.md` : installation Oracle Cloud, démarrage, mise à jour, sauvegarde et restauration chiffrées, changement de fournisseur IA ou de mot de passe, clés d'API.
- `docs/api.md` : API `/v1` et contrat JobAgent ↔ PAI.
- `ARCHITECTURE.md` : surfaces, pipeline, modules, données, sécurité.
- `DECISIONS.md` : choix faits, alternatives écartées et pourquoi.
- `PROGRESS.md` : état d'avancement, preuves, ce qu'il reste à fournir.

## Sécurité et données personnelles

- Secrets uniquement dans `.env` (ignoré par Git) ; aucun mot de passe, jeton ou cookie dans les journaux.
- Le Master Profile et tout fichier généré vivent dans `data/` (ignoré par Git) ou en base privée.
- Mots de passe argon2, cookies HttpOnly/Secure/SameSite=strict, CSRF, limitation des tentatives,
  révocation des sessions, CSP à nonce, liens de fichiers signés de courte durée, `noindex` partout.
- JobAgent n'est jamais modifié : projet Docker, réseau, base, ports et secrets séparés.

⚠️ Ce dépôt est **public** et l'historique Git contient déjà des coordonnées personnelles
(`legacy/amine_profile.py`). Recommandation : passer le dépôt en privé (voir `PROGRESS.md`).
