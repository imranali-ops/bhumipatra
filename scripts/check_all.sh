#!/usr/bin/env bash
# Runs every check in one go:  bash scripts/check_all.sh
set -u
cd "$(dirname "$0")/.."
[ -d .venv ] && source .venv/bin/activate
fail=0
step() { echo; echo "=== $1 ==="; shift; if "$@"; then echo "PASS"; else echo "FAIL"; fail=1; fi; }
step "core unit tests (no database)" python -m unittest core.test_integrity core.test_signing core.test_workflow core.test_uploads
step "django system check" python manage.py check
step "migrations are up to date" python manage.py makemigrations --check --dry-run
step "django tests" python manage.py test
step "integrity of stored records" python manage.py verify_integrity
if [ -d frontend/node_modules ]; then
  step "frontend production build" bash -c "cd frontend && npm run build"
else
  echo; echo "(skipped frontend build: run 'npm install' in frontend/ first)"
fi
echo
if [ "$fail" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED"; exit 1; fi
