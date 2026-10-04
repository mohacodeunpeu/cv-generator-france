# PAI — Personal Application Intelligence

PAI transforme une offre d'emploi en **candidature factuelle** : il lit l'offre (texte, lien, PDF, HTML, DOCX),
classe ses exigences, vérifie ce que votre profil **prouve**, calcule un **Score PAI** explicable, puis produit
un CV ciblé et une lettre dont chaque ligne cite un fait de votre profil, relit le PDF comme un ATS et range le
tout dans un pack versionné.

- **Autonome** : votre navigateur → votre domaine (Cloudflare Tunnel) → votre serveur → PAI → PostgreSQL.
  Aucun compte Claude, aucune clé d'API, aucun abonnement nécessaires.
- **Gratuit par défaut** : IA locale (Ollama) ou aucune IA ; tout fonctionne sans IA. Un fournisseur externe
  (Claude, OpenAI, Gemini, Mistral…) reste une option.
- **Factuel** : aucune affirmation sans preuve. Le validateur déterministe retire tout chiffre, diplôme, outil,
  niveau de langue ou responsabilité non prouvé ; une correspondance sémantique n'est jamais une preuve.
- **PAI ne postule jamais et n'envoie rien.** JobAgent (projet séparé) peut l'appeler par API.

## Ce que voit l'utilisateur (exemple)

```
                 SCORE PAI
                    85 %
   FORMAT & PARSING · STRUCTURE · MATCHING OFFRE · MOTS-CLÉS · EXPÉRIENCE · FACTUALITÉ
        92 %            100 %        84 %            86 %         90 %         100 %
                         Voir les détails →   (critères internes, à la demande)
```

Puis : points forts et à améliorer ; exigences **Prouvé / Correspondance possible / Non prouvé** ; mots-clés
avec la raison de leur présence ou de leur absence ; stratégie ; CV, lettre, pack. Dans le CV Studio : CV
original et CV ciblé, changements ligne par ligne (avant, après, raison, preuve), version. Le Score PAI est un
indicateur interne : **ni le score d'un ATS réel, ni une probabilité d'embauche**.

## Le moteur

1. **Offre** : texte, lien lu par le serveur (protection SSRF, cause précise en cas d'échec : anti-bot, connexion
   requise, page en JavaScript…), PDF, HTML, DOCX ; texte figé et haché (doublons, cache).
2. **Analyse** (déterministe) : poste, entreprise, lieu, contrat, salaire, langues, outils, exigences
   Obligatoire / Important / Un plus / Contexte, secteur, variante de CV (MASTER, COMMERCIAL,
   BUSINESS_DEVELOPER, RECRUTEMENT, DIGITAL, CHARGE_AFFAIRES).
3. **Preuves** : exact, synonyme (taxonomie métier française), sémantique (embeddings locaux, en option) →
   PROUVÉ / PLAUSIBLE / NON PROUVÉ.
4. **CV et lettre** : contenu choisi par le moteur (faits liés), rendu par le design ; IA seulement pour la
   rédaction et la stratégie, via le routeur (aucune IA pour le parsing, les dates, les mots-clés exacts, la
   factualité, le PDF, les scores) et un cache par empreinte.
5. **Boucle de validation** : CV → PDF → relecture ATS (deux lectures : flux du fichier, ligne à ligne) → rien
   de perdu, rien d'ajouté → correction → nouvelle relecture (trois passes au plus).
6. **Pack** : CV, lettre, analyse, questions, risques, versions (`application_id`, `version_id`, empreintes de
   l'offre et de l'analyse, version du profil, gabarit, date) : « quel CV ai-je envoyé ? » a toujours une réponse.

## Résultats mesurés

Benchmark de régression, 13 offres **fictives**, même instrument pour l'ancien générateur et PAI (texte extrait
du PDF, comme un ATS), PAI sans IA :

| Critère | Ancien générateur | PAI |
|---|---:|---:|
| Score global | 54,6 | **92,9** |
| Factualité du CV | 0 (terme interdit dans 13/13, 9 lignes non prouvées par CV) | **100** (0 ligne non prouvée) |
| Factualité de la lettre | 13,6 | **100** |
| Couverture honnête des mots-clés (prouvés) | 91,0 | **97,4** |
| Qualité du PDF | 70 | **100** |
| Couverture brute des mots-clés | **76,4** | 71,7 |

IA locale en conditions réelles (Docker, 3 cœurs CPU, sans GPU) : pack complet en 320 s avec la lettre rédigée
par `qwen3:4b-instruct`, factualité 100 %. Méthodes et limites : `docs/benchmark.md`, `docs/ai-providers.md`.

## Démarrage

```bash
# Serveur (Docker) — détails : docs/deployment.md
cp .env.example .env && chmod 600 .env      # secrets, COMPOSE_PROFILES=cloudflare,ai-local, BASE_URL
docker compose up -d --build                 # PostgreSQL + interface/API + worker (+ tunnel, + Ollama)
docker compose run --rm pai_web python -m pai create-user <identifiant> --stdout

# Local (Python 3.12)
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && python -m playwright install chromium
python -m pai build-studio --server && python -m pai create-user moi && uvicorn app:app
```

Une variante de l'interface existe aussi en page privée claude.ai (PAI Studio) : facultative, PAI n'en dépend pas.

## Documentation

| Document | Contenu |
|---|---|
| `docs/deployment.md` | architecture Docker, Cloudflare Tunnel nommé, IA locale, mises à jour, sauvegarde et restauration vérifiée |
| `RUNBOOK.md` | opérations courantes, incidents |
| `docs/api.md` | API `/api` (et `/v1` historique), entrées directes, réponses |
| `docs/ats.md` | moteur ATS : classes d'exigences, preuves, Score PAI, scanner PDF |
| `docs/ai-providers.md` | fournisseurs, routeur, choix mesuré du modèle local |
| `docs/benchmark.md` | régression, offres réelles, auto-évaluation |
| `docs/jobagent-integration.md` | pont JobAgent ↔ PAI (off / assisted / auto) |
| `ARCHITECTURE.md`, `DECISIONS.md`, `PROGRESS.md`, `SECURITY.md` | architecture, choix, avancement, sécurité |

⚠️ Ce dépôt est **public** et l'historique Git contient d'anciennes coordonnées personnelles (`legacy/`).
Recommandation : passer le dépôt en privé (voir `SECURITY.md`).
