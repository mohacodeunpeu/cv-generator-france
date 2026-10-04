# RUNBOOK — exploiter PAI

Toutes les commandes se lancent depuis le dossier du dépôt. Le serveur tourne dans le projet Docker **`pai`**
(conteneurs `pai-pai_db-1`, `pai-pai_web-1`, `pai-pai_worker-1`, et selon les profils `pai-pai_cloudflared-1`,
`pai-pai_ollama-1` ou `pai-pai_caddy-1`), sans rien partager avec JobAgent : ne jamais lancer de commande Docker
visant ses conteneurs ou ses volumes. Guide complet du déploiement (architecture, Cloudflare Tunnel, IA locale,
restauration vérifiée) : `docs/deployment.md`.

## 0. PAI Studio (sans serveur)

- URL privée : **https://claude.ai/artifact/DuyUG7Brc5LSKZ9WuoCfNK**, en étant connecté à votre compte Claude.
- Premier usage : **Profil** → relire les faits → confirmer, corriger ou supprimer → **Valider le profil**
  (le badge « Brouillon » disparaît et les documents peuvent passer en FINAL).
- **Nouvelle candidature** → coller l'offre → *Analyser et générer*. L'IA passe par votre compte Claude.
  Si l'IA est refusée ou indisponible, PAI bascule sur les voies déterministes (toujours 100 % factuelles).
- Sauvegarde : **Réglages → Exporter le profil (JSON)**, à réimporter dans le serveur (§ 5).

## 1. Installation sur Oracle Cloud (Free Tier)

1. Créer une instance **Ampere A1** (ARM, 2 OCPU / 12 Go suffisent), **Ubuntu 24.04**, avec votre clé SSH.
   Le rendu PDF (Chromium) ne tient pas sur les instances AMD à 1 Go.
2. Sur le serveur :
   ```bash
   sudo apt update && sudo apt install -y git age
   curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER && newgrp docker
   git clone <URL du dépôt> /opt/pai && cd /opt/pai
   cp .env.example .env && chmod 600 .env
   ```
3. Remplir `.env` :
   - `PAI_DB_PASSWORD` : `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`
   - `SECRET_KEY` : `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `AI_PROVIDER=local` (défaut gratuit : Ollama s'il est là, sinon sans IA) ou `none` ; un fournisseur externe
     reste possible (`docs/ai-providers.md`)
   - `BASE_URL` : l'adresse finale (`https://pai.votre-domaine.fr` ou l'adresse Tailscale)
   - `COMPOSE_PROFILES` : `cloudflare` (accès public, recommandé), `ai-local` (IA locale), séparés par des virgules
4. Démarrer :
   ```bash
   docker compose up -d --build        # base + interface/API + worker ; migrations appliquées au démarrage
   docker compose ps                   # pai_db et pai_web « healthy »
   ```
5. Créer votre compte (mot de passe provisoire affiché une seule fois, changement imposé au premier login) :
   ```bash
   docker compose run --rm pai_web python -m pai create-user amine --stdout
   ```
6. Profil : importer l'export JSON de PAI Studio…
   ```bash
   docker compose cp profil.json pai_web:/tmp/profil.json
   docker compose exec pai_web python -m pai import-profile /tmp/profil.json
   ```
   …ou le reconstruire : `docker compose exec pai_web python -m pai bootstrap-profile`.
7. Vérifier l'installation :
   ```bash
   KEY=$(docker compose exec -T pai_web python -m pai api-key create smoke --scopes read,analyze,generate | tail -1)
   PAI_URL=http://127.0.0.1:8080 PAI_API_KEY=$KEY python3 deploy/smoke_test.py   # tout doit être « OK »
   docker compose exec pai_web python -m pai api-key revoke smoke
   ```

### Accès public — Cloudflare Tunnel nommé (recommandé)
Aucun port ouvert, nom d'hôte stable sur votre domaine (jamais trycloudflare) : créer le tunnel dans Cloudflare
Zero Trust, mettre son jeton dans `CLOUDFLARE_TUNNEL_TOKEN`, publier `pai.votre-domaine.fr` → `http://pai_web:8000`,
puis `COMPOSE_PROFILES=cloudflare`, `PAI_ACCESS=cloudflare` et `docker compose up -d`. Pas à pas :
`docs/deployment.md` § 3. Contrôle : page **État du système** → « Cloudflare Tunnel : OK · 4 connexions actives ».

### Accès — option A : Tailscale (privé, rien d'exposé sur Internet)
```bash
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up
sudo tailscale serve --bg --https=443 http://127.0.0.1:8080
```
PAI est alors disponible en HTTPS sur `https://<machine>.<tailnet>.ts.net`, pour vos seuls appareils.

### Accès — option B : domaine public + Caddy (HTTPS automatique)
1. DNS : enregistrement A `pai.votre-domaine.fr` → IP publique de l'instance (Cloudflare : proxy désactivé au début).
2. Oracle : *Security List* → autoriser TCP 80 et 443 ; sur l'instance :
   `sudo iptables -I INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT && sudo netfilter-persistent save`
3. `.env` : `PAI_DOMAIN=pai.votre-domaine.fr`, `BASE_URL=https://pai.votre-domaine.fr`
4. `docker compose --profile caddy up -d`

## 2. Opérations courantes

| Action | Commande |
|---|---|
| État | `docker compose ps` |
| Journaux | `docker compose logs -f pai_web pai_worker` |
| Arrêter / démarrer | `docker compose stop` / `docker compose up -d` |
| Redémarrer après changement de `.env` | `docker compose up -d --force-recreate pai_web pai_worker` |
| Générer un pack en ligne de commande | `docker compose exec pai_web python -m pai generate fichier_offre.txt` |
| Benchmark (historique + page Benchmark) | `docker compose exec pai_web python -m pai benchmark --persist` |

## 3. Mise à jour

Recommandé : `cd /opt/pai && deploy/update.sh`, qui fait sauvegarde chiffrée → nouveau code → reconstruction →
santé → test de fumée, avec retour arrière automatique en cas d'échec. Première fois, mise à jour automatique
(minuteur systemd) et bouton GitHub Actions : `docs/DEPLOIEMENT_AUTO.md`.

À la main :

```bash
cd /opt/pai && deploy/backup.sh          # toujours sauvegarder avant
git pull
docker compose up -d --build             # les migrations Alembic s'appliquent au démarrage de pai_web
PAI_URL=http://127.0.0.1:8080 PAI_API_KEY=… python3 deploy/smoke_test.py
```
Retour arrière : `git checkout <version précédente> && docker compose up -d --build`. Si une migration a
modifié la base, restaurer la sauvegarde faite juste avant (§ 4).

## 4. Sauvegardes chiffrées

- **Une fois, sur votre ordinateur (pas sur le serveur)** : `age-keygen -o cle-pai.txt`. Gardez `cle-pai.txt`
  en lieu sûr (gestionnaire de mots de passe) : sans elle, les sauvegardes sont illisibles, par vous aussi.
- Sur le serveur, dans `.env` : `PAI_BACKUP_AGE_RECIPIENT=age1…` (la ligne « Public key » affichée).
- Sauvegarde manuelle : `deploy/backup.sh` → `backups/pai_db_*.dump.age` + `backups/pai_data_*.tar.age`
  (rotation : `PAI_BACKUP_KEEP`, 14 par défaut).
- Automatique, chaque nuit : `crontab -e` puis
  `17 3 * * * cd /opt/pai && deploy/backup.sh >> backups/backup.log 2>&1`
- Copie hors serveur (recommandé) : `rclone copy /opt/pai/backups remote:pai-backups` ou `scp`.
- **Restaurer** (écrase l'état actuel, demande de taper RESTAURER) :
  ```bash
  scp cle-pai.txt serveur:/tmp/ && ssh serveur
  cd /opt/pai && PAI_BACKUP_AGE_IDENTITY=/tmp/cle-pai.txt deploy/restore.sh \
      backups/pai_db_<date>.dump.age backups/pai_data_<date>.tar.age
  shred -u /tmp/cle-pai.txt
  ```
- Vérifiée en continu : à chaque modification, la CI lance les vrais scripts sur PostgreSQL 16 (sauvegarde →
  modification → restauration → comparaison table par table et fichier par fichier, `tests/test_backup_restore.py`).
- Exercice trimestriel conseillé sur votre ordinateur (restauration dans un PostgreSQL jetable) :
  `docs/deployment.md` § 6.

## 5. Profil

- Importer : `docker compose exec pai_web python -m pai import-profile /tmp/profil.json` (ou onglet Profil).
- Valider : onglet **Profil → Valider** (refusé tant qu'un conflit reste en REVIEW) ou `POST /v1/profile/validate`.
- Exporter : `docker compose exec pai_web python -m pai export-profile --format md`.
- Chaque modification crée une nouvelle version ; les packs gardent la version exacte utilisée.

## 6. Changer de fournisseur IA

PAI est autonome : sans IA, tout fonctionne (voies déterministes). Par défaut `local` (Ollama, gratuit ; profil
Docker `ai-local`, puis `docker compose exec pai_web python -m pai ai setup --pull`). Choix mesuré du modèle,
routeur par tâche et fournisseurs externes : `docs/ai-providers.md`. Noms courts : `AI_PROVIDER`, `AI_MODEL`,
`AI_MODEL_SMALL`, `AI_BASE_URL`, `AI_API_KEY`, `AI_PROFILE` (les anciens noms ci-dessous restent lus).
Aucun module métier n'importe de SDK : changer de fournisseur ne touche pas au code.

**Depuis l'interface (recommandé, sans redémarrage)** : Réglages → IA → choisir le fournisseur, saisir la clé,
enregistrer, puis « Tester la connexion ». La clé est chiffrée en base et n'est plus jamais réaffichée (seul un
indice `••••a1b2` apparaît). API équivalente : `GET/PUT /v1/settings/ai`, `POST /v1/settings/ai/test` (droit
`admin` pour écrire ; voir `docs/api.md`).

**Par l'environnement** (`.env`, puis `docker compose up -d --force-recreate pai_web pai_worker`) :

| Fournisseur | Réglages |
|---|---|
| Claude | `PAI_AI_PROVIDER=claude`, `ANTHROPIC_API_KEY=…` (modèles par tâche : `config/models.yaml`) |
| Gemini | `PAI_AI_PROVIDER=gemini`, `GEMINI_API_KEY=…`, `GEMINI_MODEL=…` (défaut `gemini-2.5-flash`) |
| Mistral | `PAI_AI_PROVIDER=mistral`, `MISTRAL_API_KEY=…`, `MISTRAL_MODEL=…` (défaut `mistral-large-latest`) |
| OpenAI | `PAI_AI_PROVIDER=openai`, `OPENAI_API_KEY=…`, `OPENAI_MODEL=…` |
| Local (Ollama) | `AI_PROVIDER=local` ; Docker : profil `ai-local` (URL `http://pai_ollama:11434` automatique) |
| Sans IA | `PAI_AI_PROVIDER=null` : voies déterministes, 100 % factuelles, coût nul |

- **Priorité** : Réglages → IA (base) → environnement → `default_provider` de `config/models.yaml` → sans IA.
  Base indisponible → environnement, sans erreur. Le worker et `python -m pai generate` utilisent le même choix.
- **État** : `GET /v1/status` → `ai_mode` = `REMOTE` (fournisseur distant configuré), `LOCAL` (modèle local
  configuré) ou `DEGRADED` (sans IA : clé ou modèle manquant, ou `null`).
- **Clés** : chiffrées au repos (Fernet, clé dérivée de `SECRET_KEY`), jamais renvoyées ni journalisées ; chaque
  modification est tracée dans `audit_log`, sans secret. **Changer `SECRET_KEY` rend les clés enregistrées
  illisibles** : elles sont ignorées (mode dégradé si c'était la seule clé) et sont à ressaisir.
- **URL de base** (OpenAI, local) : la changer efface la clé enregistrée de ce fournisseur (à ressaisir) ; une clé
  venant de `.env` n'est jamais envoyée à une URL de base modifiée depuis l'interface.

Plafonds : `COST_CAP_EUR_PER_PACK` et `COST_CAP_EUR_PER_DAY`. Une fois un plafond atteint, chaque étape bascule
sur sa voie déterministe, sans erreur. Seuls les appels Claude sont chiffrés en euros (grille de
`config/models.yaml`) : pour Gemini, Mistral et OpenAI, fixer aussi un plafond de dépense dans la console du
fournisseur. Les réponses IA sont mises en cache (`data/cache`, `PAI_AI_CACHE`) ; le test de connexion contourne
cache et plafond (un très petit appel, journalisé comme les autres).

## 7. Mot de passe et accès

- Changer son mot de passe : menu de l'interface ou `https://…/change-password` (toutes les autres sessions
  sont révoquées).
- Mot de passe oublié : `docker compose run --rm pai_web python -m pai create-user amine --stdout`
  (nouveau mot de passe provisoire, sessions existantes révoquées).
- Trop de tentatives de connexion : attendre 5 minutes (`LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_SECONDS`).
- Se déconnecter partout : bouton de déconnexion (révocation côté serveur).

## 8. Clés d'API (futur JobAgent, scripts)

```bash
docker compose exec pai_web python -m pai api-key create jobagent --scopes read,analyze,generate,outcomes
docker compose exec pai_web python -m pai api-key list
docker compose exec pai_web python -m pai api-key revoke jobagent
```
La clé n'est affichée qu'une fois (stockée hachée). Droits : `read, analyze, generate, feedback, outcomes,
benchmark, admin`. Donner le minimum. Référence : `docs/api.md`.

## 9. Incidents

| Symptôme | Cause probable | Action |
|---|---|---|
| `pai_web` « unhealthy » | migration ou `.env` invalide | `docker compose logs pai_web` ; `SECRET_KEY` requise en production |
| Page « Interface non construite » | image construite sans PAI Studio | `docker compose up -d --build` |
| Packs bloqués en PENDING | worker arrêté | `docker compose up -d pai_worker` ; les jobs interrompus sont repris |
| Génération sans IA inattendue | clé absente, plafond atteint, fournisseur indisponible | voir le journal du pack (étapes « voie déterministe ») |
| Disque plein | sauvegardes, journaux Docker | `docker system df`, baisser `PAI_BACKUP_KEEP`, copier les sauvegardes ailleurs |
| Connexion impossible en HTTP simple | cookie `Secure` | passer par HTTPS (tunnel Cloudflare, Caddy, Tailscale) ou `http://localhost` (tunnel SSH `ssh -L 8080:127.0.0.1:8080`) |
| État du système : « Cloudflare Tunnel » en erreur | jeton absent ou révoqué, sortie réseau bloquée | `docker compose logs pai_cloudflared` ; jeton dans `CLOUDFLARE_TUNNEL_TOKEN` ; `docker compose up -d` |
| « Modèle local » en avertissement | Ollama arrêté ou sans modèle | `docker compose --profile ai-local up -d` puis `python -m pai ai setup --pull` (PAI marche sans) |

## 10. Développement

```bash
python -m pytest tests                       # + PAI_TEST_PG_URL=postgresql+psycopg://… pour PostgreSQL
python web/build_studio.py --data-json tests/js/.data.json && node --test tests/js/*.test.js
python tests/golden/make_golden.py           # après un changement volontaire du moteur (parité Python ↔ JS)
python -m pai build-studio                   # page claude.ai (web/dist/pai_studio.html)
alembic revision --autogenerate -m "…"       # après un changement de pai/db/models.py
```
