#!/usr/bin/env bash
# Start the backend (FastAPI/uvicorn) and frontend (Next.js) dev servers
# together. Ctrl+C stops both. Output from each process interleaves
# directly in this terminal (no prefixing) so signal handling stays simple
# and robust across bash versions.
#
# Env overrides (all optional):
#   BACKEND_PORT, FRONTEND_PORT       default 8000 / 3000 (see note below)
#   JWT_SECRET_KEY                    default: freshly generated per run
#   SEED_ATTORNEY_EMAIL/_PASSWORD/_NAME
#     default: attorney@example.com / devpassword123 / "Dev Attorney"
#     (idempotent: only seeds if no user with that email exists yet)
#
# Before starting, any process already bound to BACKEND_PORT/FRONTEND_PORT
# is killed (e.g. a stale server left over from a previous run that didn't
# shut down cleanly). On exit (Ctrl+C or otherwise), both servers are
# stopped -- including child processes they spawn that don't always die
# with their parent, like uvicorn --reload's worker subprocess -- by
# sweeping those same ports again rather than relying solely on the
# top-level PIDs this script started.
#
# backend/.env (if present, e.g. copied from backend/.env.example) is
# loaded automatically by main.py on startup -- useful for settings this
# script doesn't set itself, like EMAIL_BACKEND=resend for a live demo.
#
# Note: the backend's CORS config only allows http://localhost:3000, so
# changing FRONTEND_PORT will break direct browser->backend requests (not
# that this app makes any -- all backend calls go through Next.js Server
# Actions/Components -- but keep it in mind if that changes).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
SEED_ATTORNEY_EMAIL="${SEED_ATTORNEY_EMAIL:-attorney@example.com}"
SEED_ATTORNEY_PASSWORD="${SEED_ATTORNEY_PASSWORD:-devpassword123}"
SEED_ATTORNEY_NAME="${SEED_ATTORNEY_NAME:-Dev Attorney}"

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}
JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(generate_secret)}"

pids_on_port() {
  lsof -ti ":$1" -sTCP:LISTEN 2>/dev/null || true
}

# Kill whatever's bound to a port and wait for it to actually free up.
# Used both before starting (clear stale servers from a previous run) and
# on shutdown (catch child processes -- e.g. uvicorn --reload's worker, or
# npm run dev's spawned next-server -- that don't always exit with their
# direct parent PID).
clear_port() {
  local port=$1 label=$2
  local pids
  pids=$(pids_on_port "$port")
  if [ -z "$pids" ]; then
    return 0
  fi

  echo "→ Clearing old $label process(es) on :$port (pid: $(echo "$pids" | tr '\n' ' '))"
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 10); do
    pids=$(pids_on_port "$port")
    if [ -z "$pids" ]; then
      return 0
    fi
    sleep 0.5
  done

  pids=$(pids_on_port "$port")
  if [ -n "$pids" ]; then
    echo "→ Still running, forcing: $pids"
    kill -9 $pids 2>/dev/null || true
    sleep 0.5
  fi
}

clear_port "$BACKEND_PORT" "backend"
clear_port "$FRONTEND_PORT" "frontend"

if [ ! -d backend/.venv ]; then
  echo "→ Setting up backend virtualenv (first run only)..."
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "→ Installing frontend dependencies (first run only)..."
  (cd frontend && npm install)
fi

if [ ! -f frontend/.env.local ]; then
  echo "→ Creating frontend/.env.local from .env.example..."
  cp frontend/.env.example frontend/.env.local
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "→ Shutting down..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  # Safety net: uvicorn --reload's worker subprocess and npm run dev's
  # spawned next-server don't always exit when their direct parent does.
  # Sweep by port so nothing is left holding it for the next run.
  clear_port "$BACKEND_PORT" "backend"
  clear_port "$FRONTEND_PORT" "frontend"
  echo "→ Stopped."
}
trap cleanup EXIT INT TERM

wait_for_url() {
  local url=$1 label=$2 timeout=${3:-30} waited=0
  until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    sleep 1
    waited=$((waited + 1))
    if [ "$waited" -ge "$timeout" ]; then
      echo "✗ $label did not become ready within ${timeout}s ($url)" >&2
      return 1
    fi
  done
}

echo "→ Starting backend on :$BACKEND_PORT..."
(
  cd backend
  exec env \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    SEED_ATTORNEY_EMAIL="$SEED_ATTORNEY_EMAIL" \
    SEED_ATTORNEY_PASSWORD="$SEED_ATTORNEY_PASSWORD" \
    SEED_ATTORNEY_NAME="$SEED_ATTORNEY_NAME" \
    .venv/bin/uvicorn main:app --reload --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

echo "→ Starting frontend on :$FRONTEND_PORT..."
(
  cd frontend
  exec npm run dev -- --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

if ! wait_for_url "http://127.0.0.1:$BACKEND_PORT/api/health" "Backend" 30; then
  exit 1
fi
if ! wait_for_url "http://localhost:$FRONTEND_PORT/" "Frontend" 60; then
  exit 1
fi

cat <<EOF

========================================================
 Alma dev environment is up
   Frontend:  http://localhost:$FRONTEND_PORT
   Backend:   http://127.0.0.1:$BACKEND_PORT
   Attorney login: $SEED_ATTORNEY_EMAIL / $SEED_ATTORNEY_PASSWORD
 Press Ctrl+C to stop both.
========================================================

EOF

wait
