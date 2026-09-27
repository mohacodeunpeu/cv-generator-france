# Progression PAI — point de reprise

Une nouvelle session lit ce fichier, puis `DECISIONS.md` et `RUNBOOK.md`, et reprend à « Reste à faire ».
Branche de travail : `claude/elegant-dirac-vhi4np` (PR brouillon, rien sur `master` : la fusion est ta décision).

## Fait (avec preuve)

| Lot | Contenu | Preuve |
|---|---|---|
| P0 | Commit `master` décalé réparé ; paquet `pai` reconstruit ; règles, prompts, secteurs, designs versionnés | `import pai`, CI |
| P0.5 | Master Profile v1 : `profiles/confirmations.yaml` + `legacy/` (85 faits), **MBA FORBIDDEN**, conflit « Bachelor PSB » en REVIEW, chiffres importés « à confirmer » | `python -m pai bootstrap-profile` |
| P1-P3 | Profil versionné, analyse d'offre (secteur correct 13/13), matching 12 sous-scores, stratégie A/B/C | `tests/test_engine.py`, parité JS |
| P4 | CV : faits liés ligne à ligne, sélection gloutonne des mots-clés prouvés, rendu Chromium 1 page, QA PDF | CV réel envoyé (hors Git) : 1 page, factualité 100 % |
| P5 | Validateur claim → evidence (Python + JS) : MBA, faux diplôme, faux chiffre, outil non prouvé, niveau de langue gonflé, entreprise inventée, fait UNVERIFIED, phrases creuses, fausse date | `tests/golden/validator_cases.json` (23 cas) |
| P6 | Lettre à phrases typées, questions (salaire BLOCKED), Application Pack ZIP versionné | tests + pack réel |
| Studio | **PAI Studio** : https://claude.ai/artifact/DuyUG7Brc5LSKZ9WuoCfNK (version 3), IA via ton compte Claude, base privée (propriétaire seul, vérifié), benchmark et arène importés | e2e Chromium, captures `docs/proofs/studio/` |
| Serveur | API `/v1`, PostgreSQL 16 + Alembic (30 tables), auth argon2 + sessions révocables + CSRF + limitation, clés d'API, jobs SKIP LOCKED idempotents, plafond de coût journalier, même interface servie par le serveur | `tests/test_api.py` (SQLite + PostgreSQL 16.13), e2e serveur |
| Benchmark | Ancien vs PAI, même instrument, 13 offres SYNTHETIC : **92,9 vs 54,6** ; factualité CV 100 vs 0 ; lettre 100 vs 13,6 ; couverture honnête 97,4 vs 91,0 ; seul avantage de l'ancien : couverture brute (76,4 vs 71,7), en partie par bourrage | `python -m pai benchmark`, `tests/test_benchmark.py` |
| Déploiement | Dockerfile (amd64/arm64), `docker-compose.yml` (projet `pai`, réseau interne, limites), Caddy HTTPS, sauvegardes age + rotation, test de fumée | pile Docker réelle lancée ici : pack généré par le worker, sauvegarde → modification → restauration OK ; captures `docs/proofs/server/` |
| Qualité | CI GitHub Actions ; `pip-audit` : aucune vulnérabilité connue | `.github/workflows/ci.yml` |

Tests au dernier passage : **Python 74 réussis, 1 ignoré** (test propre à PostgreSQL, réussi sur PostgreSQL),
**JS 6/6** (dont parité du CV sur 13 offres), 2 e2e navigateur (PAI Studio et serveur).

## À FOURNIR (par toi)

1. **Valider ton profil** dans PAI Studio (onglet Profil) : trancher le conflit de diplôme en file REVIEW,
   confirmer les chiffres importés de l'ancien générateur, dire si l'expérience la plus récente est toujours
   en cours. Tant que ce n'est pas fait, tout reste en BROUILLON.
2. **Clé API Anthropic** : seulement pour le serveur auto-hébergé (PAI Studio n'en a pas besoin).
3. **Serveur Oracle** : instance Ampere A1 + accès SSH (ou lance toi-même le RUNBOOK § 1, environ 20 min).
4. **Accès** : compte Tailscale (le plus simple) ou domaine sur Cloudflare (DNS A vers l'IP Oracle).
5. **JobAgent** : export JSON du profil, ou autoriser son URL dans la politique réseau (le lien trycloudflare
   était bloqué) — rien n'a été lu ni modifié côté JobAgent.
6. **Photo professionnelle** (optionnelle : désactivée par défaut, activée seulement si le pays l'accepte).
7. **Anciens CV et lettres (PDF)** et **offres réelles** (texte collé) pour un benchmark sur de vraies annonces.
8. **Dépôt public** : il contient des coordonnées personnelles dans l'historique (`legacy/amine_profile.py`).
   Recommandé : passer le dépôt en privé (Settings → General → Change visibility) ; option : purge de
   l'historique avec `git filter-repo` (réécrit l'historique, à faire en connaissance de cause).

## Reste à faire (prochaines sessions)

- Benchmark avec juge IA (3 passes, deux ordres) et sur offres réelles dès qu'elles sont fournies.
- Boucle d'apprentissage sur résultats réels (`/v1/outcomes`) : statistiques à partir de 5 cas, conclusions à 20 (A5).
- Branchement JobAgent → `/v1` (lecture seule côté JobAgent aujourd'hui ; contrat dans `docs/api.md`).
- Photo dans les designs `human_premium` ; variantes de gabarits par pays (US/UK sans photo, déjà géré par les règles).
- Si le serveur 24/7 devient l'usage principal : réévaluer une interface Next.js (décision 3).

## Risques connus

- Offres du benchmark fictives : elles mesurent la qualité documentaire, pas les taux de réponse.
- Sans profil validé, aucun document ne passe en FINAL (voulu, A3).
- Un changement de modèle ou de prompt peut changer les sorties IA : versions tracées dans chaque pack,
  validateur déterministe inchangé.
- Le dépôt public expose l'historique legacy (voir À FOURNIR 8).
