#!/usr/bin/env bash
# Sauvegarde chiffrée de PAI : base PostgreSQL (pg_dump -Fc) + volume de données (profil, cache IA),
# chiffrées avec age (clé publique uniquement sur le serveur), puis rotation.
#
#   deploy/backup.sh                    # mode docker (par défaut) : docker compose exec pai_db pg_dump …
#   PAI_BACKUP_MODE=local DB_URL=postgresql://… deploy/backup.sh   # PostgreSQL local (sans Docker)
#
# Cron conseillé (tous les jours à 3 h 17) : 17 3 * * * cd /opt/pai && deploy/backup.sh >> backups/backup.log 2>&1
set -euo pipefail
umask 077

cd "$(dirname "$0")/.."
# .env complète l'environnement sans l'écraser : une variable passée à l'appel (PAI_BACKUP_MODE=local DB_URL=… ) prime.
ENV_FILE="${PAI_ENV_FILE:-.env}"
if [ -f "$ENV_FILE" ]; then
  _caller_env="$(export -p | grep -v '^declare -[a-zA-Z]*r')"
  set -a; . "$ENV_FILE"; set +a
  eval "$_caller_env"
fi

MODE="${PAI_BACKUP_MODE:-docker}"
DIR="${PAI_BACKUP_DIR:-./backups}"
KEEP="${PAI_BACKUP_KEEP:-14}"
RECIPIENT="${PAI_BACKUP_AGE_RECIPIENT:-}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

command -v age >/dev/null || { echo "age introuvable (apt install age)" >&2; exit 1; }
[ -n "$RECIPIENT" ] || { echo "PAI_BACKUP_AGE_RECIPIENT manquant (.env) : clé publique age1…" >&2; exit 1; }
mkdir -p "$DIR"

db_dump() {
  if [ "$MODE" = "docker" ]; then
    docker compose exec -T pai_db pg_dump -U pai -d pai -Fc --no-owner
  else
    pg_dump --dbname="${DB_URL/+psycopg/}" -Fc --no-owner
  fi
}

data_dump() {
  if [ "$MODE" = "docker" ]; then
    docker compose exec -T pai_web tar -C /app/data -cf - .
  else
    tar -C "${PAI_DATA_DIR:-./data}" --exclude=./backups -cf - .
  fi
}

DB_OUT="$DIR/pai_db_$STAMP.dump.age"
DATA_OUT="$DIR/pai_data_$STAMP.tar.age"
db_dump | age -r "$RECIPIENT" -o "$DB_OUT.part"
mv "$DB_OUT.part" "$DB_OUT"
data_dump | age -r "$RECIPIENT" -o "$DATA_OUT.part"
mv "$DATA_OUT.part" "$DATA_OUT"
echo "$(date -u +%FT%TZ) sauvegarde OK : $(basename "$DB_OUT") ($(du -h "$DB_OUT" | cut -f1)), $(basename "$DATA_OUT") ($(du -h "$DATA_OUT" | cut -f1))"

# Rotation : on garde les $KEEP plus récentes de chaque type.
for kind in pai_db pai_data; do
  ls -1t "$DIR"/"$kind"_*.age 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f -- "$old"
    echo "rotation : $(basename "$old") supprimée"
  done
done
