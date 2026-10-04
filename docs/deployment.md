# Déploiement de PAI

Guide de référence du déploiement auto-hébergé : architecture Docker, accès public par **Cloudflare Tunnel nommé**,
IA locale (Ollama), mises à jour avec retour arrière, sauvegardes chiffrées et **restauration vérifiée**.
Les opérations courantes sont dans `RUNBOOK.md` ; la mise à jour automatique dans `docs/DEPLOIEMENT_AUTO.md`.

Coût de fonctionnement : **0 €** (serveur Oracle Cloud Free Tier, Cloudflare Tunnel gratuit, Ollama et modèles
ouverts gratuits). Seul un nom de domaine géré par Cloudflare est nécessaire pour un nom d'hôte public stable
(quelques euros par an) ; sans domaine, l'accès privé par Tailscale reste gratuit.

## 1. Architecture

```
Navigateur ── HTTPS ──▶ Cloudflare (pai.votre-domaine.fr, certificat, protection)
                              │  tunnel NOMMÉ : connexion sortante du serveur, aucun port ouvert
                              ▼
┌──────────────────────── serveur (projet Docker « pai ») ─────────────────────────┐
│ pai_cloudflared ──▶ pai_web  (interface + API, migrations au démarrage)            │
│                        │   └── 127.0.0.1:8080 (accès local : Tailscale, tunnel SSH)│
│                        ├──▶ pai_db      PostgreSQL 16, réseau interne sans Internet│
│ pai_worker (packs, PDF)┘                                                           │
│ pai_ollama (IA locale, optionnelle) ◀── pai_web / pai_worker                       │
└───────────────────────────────────────────────────────────────────────────────────┘
```

| Service | Rôle | Profil | Réseaux | Ports publiés |
|---|---|---|---|---|
| `pai_db` | PostgreSQL 16 (données, file de jobs) | toujours | `pai_internal` (sans Internet) | aucun |
| `pai_web` | interface PAI Studio, API `/v1` et `/api`, migrations Alembic | toujours | interne + `pai_edge` | `127.0.0.1:8080` |
| `pai_worker` | génération des packs (Chromium pour les PDF) | toujours | interne + `pai_edge` | aucun |
| `pai_cloudflared` | Cloudflare Tunnel nommé | `cloudflare` | `pai_edge` | aucun |
| `pai_ollama` | IA locale (version mesurée : Ollama 0.34.4) | `ai-local` | interne + `pai_edge` | aucun |
| `pai_caddy` | alternative : HTTPS direct (ports 80/443 ouverts) | `caddy` | `pai_edge` | 80, 443 |

Isolation : projet Docker `pai`, noms préfixés `pai_`, réseaux, volumes et secrets propres. Rien n'est partagé
avec JobAgent. Images épinglées (multi-architecture amd64 + arm64, vérifiées) : `postgres:16-alpine`,
`cloudflare/cloudflared:2026.9.3`, `ollama/ollama:0.34.4`, image PAI construite depuis le `Dockerfile`.

Les profils actifs se règlent une fois pour toutes dans `.env` : `COMPOSE_PROFILES=cloudflare,ai-local`.
`docker compose up -d` et `deploy/update.sh` les reprennent alors sans option. `cloudflare` et `caddy` sont deux
accès alternatifs : n'en activer qu'un (`deploy/update.sh` refuse les deux ensemble).

## 2. Installation

Serveur conseillé : Oracle Cloud **Ampere A1** (ARM), Ubuntu 24.04. 2 OCPU / 12 Go suffisent sans IA locale ;
avec l'IA locale, 4 OCPU / 24 Go (le maximum gratuit).

```bash
sudo apt update && sudo apt install -y git age
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER && newgrp docker
git clone <URL du dépôt> /opt/pai && cd /opt/pai
cp .env.example .env && chmod 600 .env        # .env n'est jamais commité (.gitignore, .dockerignore)
```

Dans `.env` (secrets générés sur le serveur, jamais copiés ailleurs) :

| Variable | Valeur |
|---|---|
| `PAI_DB_PASSWORD` | `python3 -c "import secrets; print(secrets.token_urlsafe(24))"` |
| `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `BASE_URL` | l'adresse publique finale, ex. `https://pai.votre-domaine.fr` |
| `COMPOSE_PROFILES` | `cloudflare,ai-local` (ou `cloudflare` seul, sans IA locale) |
| `PAI_ACCESS` | `cloudflare` (voir § 3 : adresse IP réelle du visiteur) |
| `CLOUDFLARE_TUNNEL_TOKEN` | jeton du tunnel (§ 3) |
| `AI_PROVIDER` | `local` (défaut : Ollama si présent, sinon sans IA) ou `none` |
| `PAI_BACKUP_AGE_RECIPIENT` | clé publique `age1…` (§ 6) |

Puis :

```bash
docker compose up -d --build          # migrations appliquées au démarrage de pai_web
docker compose ps                     # pai_db, pai_web (et pai_ollama) « healthy »
docker compose run --rm pai_web python -m pai create-user <identifiant> --stdout   # mot de passe provisoire
```

## 3. Accès public : Cloudflare Tunnel nommé (recommandé)

Pourquoi : aucun port entrant ouvert sur le serveur (le connecteur `cloudflared` ouvre une connexion sortante),
nom d'hôte **stable** sur votre domaine, HTTPS géré par Cloudflare, adresse IP du serveur jamais exposée.
Un tunnel « rapide » `trycloudflare.com` (adresse aléatoire, changeante) n'est jamais utilisé.

1. Le domaine est géré par Cloudflare (DNS chez Cloudflare, offre gratuite).
2. Tableau de bord Cloudflare → **Zero Trust → Networks → Tunnels → Create a tunnel** → type *Cloudflared*,
   nom `pai`.
3. Copier le **jeton** affiché dans la commande d'installation (`… --token <JETON>`) et le placer dans `.env` :
   `CLOUDFLARE_TUNNEL_TOKEN=<JETON>`. Ce jeton est un secret : jamais dans Git, jamais dans un journal.
4. Onglet **Public Hostname** du tunnel : sous-domaine `pai`, domaine `votre-domaine.fr`, service **HTTP**,
   URL **`pai_web:8000`** (le nom du service Docker : le connecteur est dans le même réseau `pai_edge`).
5. `.env` : `COMPOSE_PROFILES=cloudflare` (ajouter `,ai-local` si besoin), `PAI_ACCESS=cloudflare`,
   `BASE_URL=https://pai.votre-domaine.fr`, puis `docker compose up -d`.
6. Vérifier : `docker compose logs pai_cloudflared` affiche « Registered tunnel connection » (4 connexions),
   et la page **État du système** de PAI indique « Cloudflare Tunnel : OK · 4 connexions actives » (PAI lit les
   métriques du connecteur, `http://pai_cloudflared:2000/ready`).

Adresse IP du visiteur : derrière le tunnel, `X-Forwarded-For` peut contenir ce que le visiteur a lui-même envoyé.
Avec `PAI_ACCESS=cloudflare` (ou `COMPOSE_PROFILES` contenant `cloudflare` sans `caddy`), PAI prend l'adresse de
`CF-Connecting-IP`, que Cloudflare pose et écrase à chaque requête : la limite de tentatives de connexion ne peut
pas être contournée en changeant d'en-tête. Ne jamais activer `PAI_ACCESS=cloudflare` avec Caddy.

Protection supplémentaire (optionnelle, gratuite) : **Zero Trust → Access → Applications** → application
*self-hosted* sur `pai.votre-domaine.fr`, règle « e-mail = le vôtre » (code à usage unique). Un client
automatisé (JobAgent, scripts) passe alors par un *service token* Access (en-têtes `CF-Access-Client-Id` et
`CF-Access-Client-Secret`), en plus de sa clé d'API PAI.

Passer de Caddy au tunnel : `docker compose --profile caddy stop pai_caddy && docker compose --profile caddy rm -f
pai_caddy`, retirer `caddy` de `COMPOSE_PROFILES`, refermer les ports 80/443 (Security List Oracle et iptables),
puis suivre les étapes ci-dessus. Rien d'autre ne change (même base, mêmes volumes).

Alternatives : **Tailscale** (accès privé à vos seuls appareils, `RUNBOOK.md` § 1) ou **Caddy** (profil `caddy`,
`PAI_DOMAIN`, ports 80/443 ouverts).

## 4. IA locale (profil `ai-local`)

PAI fonctionne entièrement sans IA (voies déterministes, 100 % factuelles). L'IA locale améliore la rédaction,
gratuitement, sans qu'aucune donnée ne quitte le serveur.

```bash
# .env : COMPOSE_PROFILES=cloudflare,ai-local et AI_PROVIDER=local
docker compose up -d
docker compose exec pai_web python -m pai ai setup --pull   # télécharge les modèles adaptés, les mesure, choisit
docker compose exec pai_web python -m pai ai status         # Ollama joignable, modèles, choix enregistré
```

- Les modèles vivent dans le volume `pai_ollama` (survivent aux mises à jour).
- Le choix du modèle se fait sur les ressources **du conteneur Ollama** (`PAI_AI_HOST_CPUS=3`,
  `PAI_AI_HOST_RAM_GB=8`, égales à ses limites dans `docker-compose.yml`), jamais sur celles du conteneur de PAI.
- Choix mesuré sur une machine de référence (4 cœurs, 15 Go, sans GPU) : grand modèle `qwen3:4b-instruct-2507`
  (Q4_K_M, ≈ 4 Go), petit modèle `qwen3:1.7b`, embeddings `embeddinggemma` ; méthode et résultats :
  `docs/ai-providers.md`.
- Ollama ailleurs (autre machine) : `PAI_OLLAMA_URL=http://hôte:11434`, et ses ressources dans
  `PAI_AI_HOST_CPUS` / `PAI_AI_HOST_RAM_GB`.
- Sans modèle, ou Ollama arrêté : PAI passe en « Sans IA », sans erreur (page État du système : WARNING).

## 5. Mises à jour et retour arrière

`deploy/update.sh` (à la main, par le minuteur systemd ou par GitHub Actions, `docs/DEPLOIEMENT_AUTO.md`) :

1. refuse de continuer si des fichiers suivis ont été modifiés à la main ;
2. vérifie les profils (`COMPOSE_PROFILES`) : jeton du tunnel présent, domaine Caddy présent, pas les deux accès ;
3. sauvegarde chiffrée (base + données) ;
4. bascule sur le nouveau code, `docker compose up -d --build` ; migrations Alembic au démarrage de `pai_web` ;
5. santé (`/health`) puis test de fumée (`deploy/smoke_test.py` : analyse, pack par le worker, PDF signé) ;
6. échec → retour automatique à la version précédente ; si une migration a déjà modifié la base, restaurer la
   sauvegarde faite à l'étape 3 (§ 6).

Contrôles après chaque déploiement : `curl -fsS http://127.0.0.1:8080/api/ready` (base, migrations, stockage,
configuration), page **État du système**.

## 6. Sauvegardes chiffrées et restauration vérifiée

- Clé `age` créée **sur votre ordinateur** (`age-keygen -o cle-pai.txt`), jamais sur le serveur ; seule la clé
  publique va dans `.env` (`PAI_BACKUP_AGE_RECIPIENT`). Sans la clé privée, une sauvegarde est illisible.
- `deploy/backup.sh` : `pg_dump -Fc` de la base + archive du volume de données, chiffrés, rotation
  (`PAI_BACKUP_KEEP`). Nuit : `17 3 * * * cd /opt/pai && deploy/backup.sh >> backups/backup.log 2>&1`.
- `deploy/restore.sh` : restaure base et données à l'identique (demande de taper RESTAURER).
- **Vérifié automatiquement à chaque modification** (`tests/test_backup_restore.py`, en CI sur PostgreSQL 16) :
  les vrais scripts sauvegardent une base PAI (schéma des migrations, profil versionné, utilisateur), le test la
  modifie (ligne ajoutée, lignes supprimées, fichiers changés), restaure, puis compare **table par table et
  fichier par fichier** l'empreinte de l'état restauré avec celle de l'état sauvegardé. Il vérifie aussi que les
  fichiers de sauvegarde sont chiffrés (aucun contenu lisible en clair).
- Exercice trimestriel conseillé, sur votre ordinateur (la clé privée n'y quitte pas) :
  ```bash
  docker run -d --name pai_restore_check -e POSTGRES_USER=pai -e POSTGRES_PASSWORD=verif -e POSTGRES_DB=pai \
      -p 127.0.0.1:55432:5432 postgres:16-alpine
  age -d -i cle-pai.txt pai_db_<date>.dump.age | docker exec -i pai_restore_check pg_restore -U pai -d pai --no-owner
  docker exec pai_restore_check psql -U pai -d pai -c "select count(*) from store_documents; select count(*) from jobs;"
  docker rm -f pai_restore_check
  ```

## 7. Ce que vérifie l'intégration continue

À chaque push (`.github/workflows/ci.yml`) :

- tests Python sur SQLite et PostgreSQL 16, migrations (upgrade, check, downgrade), parité Python ↔ JS, tests
  navigateur (PAI Studio et serveur, CSP stricte), sauvegarde → modification → restauration → comparaison ;
- job **Docker** : les trois configurations Compose (sans profil, `cloudflare` + `ai-local`, `caddy`), construction
  de l'image, démarrage de la pile (PostgreSQL, interface/API, worker) avec `--wait`, `/api/ready` avec migrations
  à jour, puis test de fumée complet dans le conteneur.

Limites connues (dites, pas cachées) : la CI ne joint pas Cloudflare (pas de jeton de tunnel en CI) ni de vrai
modèle Ollama (trop lourd) ; le tunnel se vérifie sur le serveur (page État du système), l'IA locale par
`python -m pai ai status`.
