#!/bin/sh
# Rôles du conteneur : web (migrations puis API + interface), worker (file de jobs), ou toute commande.
set -eu
case "${1:-web}" in
  web)
    alembic upgrade head
    exec uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers \
      --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" --no-server-header
    ;;
  worker)
    exec python -m pai worker
    ;;
  *)
    exec "$@"
    ;;
esac
