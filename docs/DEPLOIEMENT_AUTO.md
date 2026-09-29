# Déploiement de PAI sur le serveur (Oracle)

L'environnement de développement (session Claude Code dans le cloud) **ne peut pas joindre le serveur** :
le proxy réseau de l'environnement refuse le domaine du serveur PAI (HTTP 403) et il n'a pas d'accès SSH.
Une nouvelle version poussée sur GitHub n'arrive donc sur le serveur que par l'un des trois moyens ci-dessous.
Tous passent par le même script, `deploy/update.sh`.

## Ce que fait `deploy/update.sh`

1. Refuse de continuer si des fichiers suivis par Git ont été modifiés à la main sur le serveur (rien n'est écrasé).
2. Récupère la branche suivie (`PAI_BRANCH`, sinon `.pai-branch`, sinon la branche actuelle).
3. Sauvegarde chiffrée de la base (`deploy/backup.sh`) si `PAI_BACKUP_AGE_RECIPIENT` est défini dans `.env`.
4. Bascule sur le nouveau code et relance le projet Docker **`pai`** (`docker compose up -d --build`) ;
   les migrations Alembic s'appliquent au démarrage de `pai_web`.
5. Vérifie `/health` sur `127.0.0.1:${PAI_HTTP_PORT}`, puis lance le test de fumée (`deploy/smoke_test.py`,
   dans le conteneur `pai_web`).
6. En cas d'échec : **retour automatique à la version précédente** (code de sortie 2) ; la version refusée est
   notée dans `.pai-failed` et le minuteur ne la retente pas en boucle.

Journal : `backups/update.log`. JobAgent n'est jamais touché : autre projet Docker, autres conteneurs,
autre port, autres volumes.

## Moyen 1 — une commande sur le serveur (maintenant)

À lancer une fois en SSH sur le serveur, dans le dossier d'installation de PAI (celui qui contient
`docker-compose.yml` et `.env`, `/opt/pai` dans le RUNBOOK). La première fois, le script n'existe pas encore
dans l'ancienne version : on le lit directement depuis la branche, sans toucher au code en place, pour que le
retour arrière vise bien l'ancienne version.

```bash
cd /opt/pai
git fetch origin claude/elegant-dirac-vhi4np
git show origin/claude/elegant-dirac-vhi4np:deploy/update.sh > /tmp/pai-update.sh
PAI_DIR=/opt/pai PAI_BRANCH=claude/elegant-dirac-vhi4np bash /tmp/pai-update.sh
```

Ensuite, pour chaque nouvelle version : `cd /opt/pai && deploy/update.sh`.

Contrôle : ouvre l'adresse publique de PAI (`https://pai.<ip-avec-tirets>.sslip.io` ou ton domaine) : la page de
connexion affiche le monogramme **PAI**
et l'accueil (après connexion) le grand champ « Analyser une offre ».

## Moyen 2 — mise à jour automatique (minuteur systemd, recommandé)

Le serveur vérifie toutes les 10 minutes si la branche suivie a changé et ne fait rien sinon. L'utilisateur
choisi doit pouvoir lancer `docker` (groupe `docker`).

```bash
cd /opt/pai
echo 'PAI_BRANCH=claude/elegant-dirac-vhi4np' >> .env        # branche suivie (ou master après la fusion)
for f in pai-update.service pai-update.timer; do
  sed -e "s#PAI_USER#$(whoami)#g" -e "s#PAI_DIR#$(pwd)#g" "deploy/systemd/$f" | sudo tee "/etc/systemd/system/$f" >/dev/null
done
sudo systemctl daemon-reload && sudo systemctl enable --now pai-update.timer
systemctl list-timers pai-update.timer                         # prochaine vérification
journalctl -u pai-update.service -n 50                         # dernières mises à jour
```

Arrêter : `sudo systemctl disable --now pai-update.timer`.

## Moyen 3 — bouton dans GitHub (Actions → « Déploiement PAI » → Run workflow)

Le workflow `.github/workflows/deploy.yml` se connecte en SSH avec une clé dédiée et lance `deploy/update.sh`,
puis vérifie l'URL publique. Il ne se lance qu'à la main. Secrets à créer dans
*Settings → Secrets and variables → Actions* :

| Secret | Valeur |
| --- | --- |
| `PAI_DEPLOY_HOST` | IP ou nom du serveur |
| `PAI_DEPLOY_USER` | utilisateur SSH (membre du groupe `docker`) |
| `PAI_DEPLOY_SSH_KEY` | clé privée **dédiée** (`ssh-keygen -t ed25519 -f pai_deploy -N ''`, clé publique dans `~/.ssh/authorized_keys` du serveur) |
| `PAI_DEPLOY_KNOWN_HOSTS` | sortie de `ssh-keyscan -t ed25519 <serveur>` vérifiée à la main (empreinte épinglée, jamais « accepter tout ») |
| `PAI_DEPLOY_PATH` | dossier de PAI (défaut `/opt/pai`) |
| `PAI_PUBLIC_URL` | facultatif : l'adresse publique de PAI (`https://…`) |

Aucun secret n'apparaît dans les journaux du workflow ; sans secrets, le workflow s'arrête avec la liste de ce
qui manque.

## Laisser la session Claude Code vérifier l'URL publique

Dans les réglages de l'environnement cloud (menu de l'environnement dans la barre de titre de la session →
*Edit* → *Network access*), ajouter le domaine du serveur PAI aux domaines autorisés (ou choisir un niveau
d'accès plus large). Niveaux d'accès : https://code.claude.com/docs/en/claude-code-on-the-web.
La session pourra alors vérifier `/health`, les en-têtes de sécurité et la page de connexion ; elle n'a
toujours ni accès SSH ni mot de passe (ne jamais le lui donner).
