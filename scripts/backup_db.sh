#!/usr/bin/env bash
# Compressed backup of the database:  bash scripts/backup_db.sh
# Keep backups off this machine and encrypted; they contain personal data.
set -eu
cd "$(dirname "$0")/.."
set -a; source .env; set +a
mkdir -p backups
out="backups/${DB_NAME}-$(date +%Y%m%d-%H%M%S).sql.gz"
PGPASSWORD="$DB_PASSWORD" pg_dump -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "$DB_USER" "$DB_NAME" | gzip > "$out"
chmod 600 "$out"
echo "backup written to $out"
echo "restore:  gunzip -c $out | PGPASSWORD=... psql -h HOST -U $DB_USER $DB_NAME"
