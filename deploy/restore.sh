#!/usr/bin/env bash
# Restauration d'une sauvegarde chiffrée PAI (base + données). ÉCRASE l'état actuel : demande confirmation.
#
#   PAI_BACKUP_AGE_IDENTITY=~/cle-pai.txt deploy/restore.sh backups/pai_db_20260927T031700Z.dump.age [backups/pai_data_….tar.age]
#   (ajouter --yes pour ne pas demander confirmation ; PAI_BACKUP_MODE=local pour un PostgreSQL local)
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

YES=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--yes" ]; then YES=1; else ARGS+=("$a"); fi
done
DB_FILE="${ARGS[0]:-}"
DATA_FILE="${ARGS[1]:-}"
MODE="${PAI_BACKUP_MODE:-docker}"
IDENTITY="${PAI_BACKUP_AGE_IDENTITY:-}"

[ -n "$DB_FILE" ] && [ -f "$DB_FILE" ] || { echo "Usage : deploy/restore.sh pai_db_….dump.age [pai_data_….tar.age] [--yes]" >&2; exit 1; }
[ -n "$IDENTITY" ] && [ -f "$IDENTITY" ] || { echo "PAI_BACKUP_AGE_IDENTITY : chemin de la clé privée age requis" >&2; exit 1; }
command -v age >/dev/null || { echo "age introuvable (apt install age)" >&2; exit 1; }

if [ "$YES" != 1 ]; then
  read -r -p "Restaurer $(basename "$DB_FILE") et écraser la base actuelle ? Tapez RESTAURER : " answer
  [ "$answer" = "RESTAURER" ] || { echo "Annulé."; exit 1; }
fi

if [ "$MODE" = "docker" ]; then
  docker compose stop pai_web pai_worker >/dev/null 2>&1 || true
  age -d -i "$IDENTITY" "$DB_FILE" | docker compose exec -T pai_db pg_restore -U pai -d pai --clean --if-exists --no-owner
  if [ -n "$DATA_FILE" ]; then
    docker compose run --rm --no-deps -T --entrypoint sh pai_web -c "find /app/data -mindepth 1 -delete" >/dev/null
    age -d -i "$IDENTITY" "$DATA_FILE" | docker compose run --rm --no-deps -T --entrypoint tar pai_web -C /app/data -xf -
  fi
  docker compose up -d pai_web pai_worker
else
  age -d -i "$IDENTITY" "$DB_FILE" | pg_restore --dbname="${DB_URL/+psycopg/}" --clean --if-exists --no-owner
  if [ -n "$DATA_FILE" ]; then
    DATA_DIR="${PAI_DATA_DIR:-./data}"
    mkdir -p "$DATA_DIR"
    [ "$(cd "$DATA_DIR" && pwd -P)" != "/" ] || { echo "PAI_DATA_DIR ne peut pas être la racine" >&2; exit 1; }
    # comme en mode docker : le dossier retrouve exactement l'état sauvegardé (sauf le dossier des sauvegardes)
    find "$DATA_DIR" -mindepth 1 -maxdepth 1 ! -name backups -exec rm -rf -- {} +
    age -d -i "$IDENTITY" "$DATA_FILE" | tar -C "$DATA_DIR" -xf -
  fi
fi
echo "Restauration terminée : $(basename "$DB_FILE")${DATA_FILE:+ + $(basename "$DATA_FILE")}"
