#!/usr/bin/env bash
# One command to run both servers for a demo:  bash scripts/start_demo.sh
# Ctrl+C stops both.
set -u
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Run the setup steps in README.md first (.venv missing)"; exit 1; }
[ -d frontend/node_modules ] || { echo "Run 'npm install' in frontend/ first"; exit 1; }
[ -f frontend/.env.local ] || cp frontend/.env.example frontend/.env.local
source .venv/bin/activate
trap 'echo; echo "stopping..."; kill 0' EXIT INT TERM
python manage.py runserver 127.0.0.1:8000 &
( cd frontend && npm run dev ) &
echo
echo "Open http://localhost:3000   (Ctrl+C to stop both)"
wait
