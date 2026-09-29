#!/usr/bin/env bash
# Mise à jour sûre de PAI sur le serveur : sauvegarde chiffrée → nouveau code → reconstruction → santé →
# test de fumée → retour arrière automatique en cas d'échec. Ne touche jamais à JobAgent (projet Docker
# « pai » isolé : ses propres conteneurs, réseau, volumes et port).
#
#   cd /opt/pai && deploy/update.sh                          # branche suivie : PAI_BRANCH (.env) ou la branche actuelle
#   PAI_BRANCH=claude/elegant-dirac-vhi4np deploy/update.sh  # choisir la branche
#   PAI_UPDATE_IF_CHANGED=1 deploy/update.sh                 # ne fait rien si le code n'a pas changé (minuteur systemd)
#   PAI_DIR=/opt/pai bash /tmp/pai-update.sh                 # 1re fois : script lu depuis la branche (docs/DEPLOIEMENT_AUTO.md)
#
# Code de sortie : 0 = à jour (ou déjà à jour), 1 = échec avant bascule, 2 = échec après bascule → retour arrière fait.
set -euo pipefail
umask 077
cd "${PAI_DIR:-$(dirname "$0")/..}"
ASKED_BRANCH="${PAI_BRANCH:-}"   # la branche donnée en ligne de commande l'emporte sur .env
[ -f .env ] && { set -a; . ./.env; set +a; }

PORT="${PAI_HTTP_PORT:-8080}"
BRANCH="${ASKED_BRANCH:-${PAI_BRANCH:-$(cat .pai-branch 2>/dev/null || git rev-parse --abbrev-ref HEAD)}}"
[ "$BRANCH" = "HEAD" ] && { echo "Branche inconnue (HEAD détaché) : précise PAI_BRANCH (ex. PAI_BRANCH=claude/elegant-dirac-vhi4np)." >&2; exit 1; }
LOG="${PAI_UPDATE_LOG:-./backups/update.log}"
mkdir -p "$(dirname "$LOG")"
say() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG"; }

git diff --quiet && git diff --cached --quiet || { say "Modifications locales non enregistrées dans $(pwd) : mise à jour annulée (rien n'est écrasé)."; exit 1; }
PREV="$(git rev-parse HEAD)"
git fetch --quiet origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
NEXT="$(git rev-parse "origin/$BRANCH")"
if [ "${PAI_UPDATE_IF_CHANGED:-0}" = "1" ]; then
  [ "$PREV" = "$NEXT" ] && exit 0
  # une version déjà refusée (santé ou test de fumée en échec) n'est pas retentée toutes les 10 minutes
  [ "$(cat .pai-failed 2>/dev/null)" = "$NEXT" ] && exit 0
fi
say "Mise à jour ${PREV:0:7} → ${NEXT:0:7} (branche $BRANCH)"

if [ -n "${PAI_BACKUP_AGE_RECIPIENT:-}" ]; then
  deploy/backup.sh >> "$LOG" 2>&1 || { say "Sauvegarde impossible : mise à jour annulée."; exit 1; }
  say "Sauvegarde chiffrée faite."
else
  say "ATTENTION : PAI_BACKUP_AGE_RECIPIENT absent de .env, pas de sauvegarde avant mise à jour."
fi

healthy() {
  for _ in $(seq 1 90); do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}
smoke() { docker compose exec -T -e PAI_URL=http://127.0.0.1:8000 -e PAI_API_KEY="${PAI_SMOKE_API_KEY:-}" pai_web python deploy/smoke_test.py >> "$LOG" 2>&1; }
deploy_rev() {
  git checkout --quiet "$1"
  docker compose up -d --build >> "$LOG" 2>&1
}

if ! git merge-base --is-ancestor "$PREV" "$NEXT" 2>/dev/null; then
  say "Note : ${NEXT:0:7} ne descend pas de ${PREV:0:7} (historique réécrit en amont ?) : déploiement quand même, retour arrière possible."
fi
if deploy_rev "$NEXT" && healthy && smoke; then
  echo "$BRANCH" > .pai-branch
  rm -f .pai-failed
  say "OK : PAI ${NEXT:0:7} en ligne (santé + test de fumée)."
  exit 0
fi
say "ÉCHEC après bascule : retour à ${PREV:0:7}."
echo "$NEXT" > .pai-failed
deploy_rev "$PREV" || true
if healthy; then say "Retour arrière terminé : ${PREV:0:7} en ligne."; else say "Retour arrière : PAI ne répond pas, voir « docker compose logs pai_web »."; fi
say "Si une migration a modifié la base, restaure la sauvegarde faite juste avant (RUNBOOK § 4)."
exit 2
