#!/usr/bin/env bash
# Starts a local frontend dev session: Flask backend (debug/reload) +
# Vite dev server (HMR), per docs/frontend.md and docs/deployment.md.
# Browse to http://localhost:5173 — Vite proxies /api, /scripts, /health to Flask.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d .venv ]; then
    echo "==> Creating virtualenv (.venv)"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

export FLASK_APP=drawbridge/main.py
export FLASK_DEBUG=1
export DATABASE_PATH="${DATABASE_PATH:-./tests/dev-data/drawbridge.db}"
export SCRIPTS_PATH="${SCRIPTS_PATH:-./scripts}"
export KEA_CTRL_URL="${KEA_CTRL_URL:-http://localhost:8081}"
export SECRET_KEY="${SECRET_KEY:-dev-only-insecure-secret-key}"
mkdir -p tests/dev-data

if [ ! -d frontend/node_modules ]; then
    echo "==> Installing frontend dependencies"
    (cd frontend && npm install)
fi

script_args=("$@")
pids=()
cleaned_up=0
cleanup() {
    [ "$cleaned_up" -eq 1 ] && return
    cleaned_up=1
    echo "==> Stopping dev session"
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}

post_session_prompt() {
    echo
    read -rp "Run the test suite before exiting? [y/N] " run_tests
    [[ "$run_tests" =~ ^[Yy]$ ]] || return

    if pytest; then
        echo "==> Tests passed"
        read -rp "Build a new container image? [y/N] " build_image
        if [[ "$build_image" =~ ^[Yy]$ ]]; then
            podman build -t localhost/drawbridge:latest .
        fi
    else
        echo "==> Tests failed"
        read -rp "Start the dev session again? [y/N] " restart
        if [[ "$restart" =~ ^[Yy]$ ]]; then
            exec "$0" "${script_args[@]}"
        fi
    fi
}

trap cleanup EXIT TERM
trap 'cleanup; post_session_prompt' INT

echo "==> Starting Flask backend on :8080"
flask run --port 8080 &
pids+=($!)

echo "==> Starting Vite dev server on :5173"
(cd frontend && npm run dev) &
pids+=($!)

wait
