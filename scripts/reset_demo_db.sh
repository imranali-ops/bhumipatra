#!/usr/bin/env bash
# Wipes the LOCAL development database and rebuilds it with fresh demo data.
# The ledger tables are append-only by design, so a reset means dropping the database.
set -eu
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a; source .env; set +a
[ "${DJANGO_DEBUG:-false}" = "true" ] || { echo "Refusing: DJANGO_DEBUG is not true"; exit 1; }
read -r -p "This DELETES database '$DB_NAME' on this computer. Type YES to continue: " answer
[ "$answer" = "YES" ] || { echo "cancelled"; exit 1; }
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DB_NAME\";"
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";"
python manage.py migrate
python manage.py seed_demo
