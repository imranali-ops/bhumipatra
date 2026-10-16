#!/bin/sh
set -e
# Migrations are part of the project. If models changed without a migration,
# stop loudly instead of starting with a broken database layout.
if ! python manage.py makemigrations --check --dry-run >/dev/null 2>&1; then
  echo "ERROR: missing migrations. Run 'python manage.py makemigrations accounts audit records mutations' and rebuild." >&2
  exit 1
fi
python manage.py migrate --noinput
python manage.py collectstatic --noinput >/dev/null
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 30 --access-logfile -
