#!/usr/bin/env bash
# start_dev.sh — CaVDesign dev environment launcher
#
# Kills orphaned/zombie processes on ports 8000 and 3000, then starts the
# FastAPI backend (nohup + disown — survives terminal close) and the Next.js
# frontend.  Safe to run repeatedly; already-running healthy processes are
# left alone.
#
# Usage:
#   bash scripts/start_dev.sh            # start both
#   bash scripts/start_dev.sh backend     # backend only
#   bash scripts/start_dev.sh frontend    # frontend only

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=3000
BACKEND_PID_FILE="$ROOT/.backend.pid"
BACKEND_LOG="$ROOT/backend.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[start_dev]${NC} $*"; }
warn() { echo -e "${YELLOW}[start_dev]${NC} $*"; }
err()  { echo -e "${RED}[start_dev]${NC} $*"; }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Kill any process whose cmdline matches a grep pattern.
kill_by_pattern() {
    local pattern="$1"
    local label="$2"
    local killed=0
    for pid in $(python3 -c "
import os
for p in os.listdir('/proc'):
    if not p.isdigit(): continue
    try:
        with open(f'/proc/{p}/cmdline') as f:
            if '$pattern' in f.read().replace(chr(0),' '):
                print(p)
    except: pass
" 2>/dev/null); do
        # Never kill our own script / parent chain.
        if [ "$pid" = "$$" ] || [ "$pid" = "$PPID" ]; then continue; fi
        kill -9 "$pid" 2>/dev/null || true
        killed=$((killed + 1))
    done
    if [ "$killed" -gt 0 ]; then
        warn "Killed $killed $label process(es)"
    fi
}

# Check whether a TCP port is available for binding.
port_is_free() {
    python3 -c "
import socket
s = socket.socket()
s.settimeout(2)
try:
    s.bind(('127.0.0.1', $1))
    s.close()
    exit(0)
except OSError:
    exit(1)
" 2>/dev/null
}

# Wait for an HTTP endpoint to return 200 (up to TIMEOUT seconds).
wait_for_http() {
    local url="$1"
    local timeout="${2:-30}"
    local elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null | grep -q '200'; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

cleanup_zombies() {
    log "Cleaning up zombie processes..."
    # Only kill uvicorn if it is NOT responding to health checks.
    if ! port_is_free "$BACKEND_PORT"; then
        if ! curl -s "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null | grep -q '"ok"'; then
            warn "Backend port $BACKEND_PORT occupied but not healthy — killing stale uvicorn..."
            kill_by_pattern "uvicorn" "uvicorn"
        fi
    fi
    # Always kill orphaned next processes (they're per-session and stale).
    kill_by_pattern "next-server" "next-server"
    kill_by_pattern "next dev" "next dev"
    sleep 2
}

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

start_backend() {
    if port_is_free "$BACKEND_PORT"; then
        # Port is free — start fresh.
        :
    else
        # Something is on the port.  Check if it's healthy.
        if curl -s "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null | grep -q '"ok"'; then
            log "Backend already running and healthy on port $BACKEND_PORT"
            return 0
        fi
        warn "Port $BACKEND_PORT occupied by non-responsive process — cleaning up..."
        kill_by_pattern "uvicorn" "uvicorn"
        sleep 2
    fi

    log "Starting FastAPI backend on port $BACKEND_PORT..."
    cd "$ROOT"
    nohup python3 -m uvicorn api:app --host 127.0.0.1 --port "$BACKEND_PORT" \
        > "$BACKEND_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$BACKEND_PID_FILE"
    disown "$pid" 2>/dev/null || true

    if wait_for_http "http://127.0.0.1:$BACKEND_PORT/health" 15; then
        log "Backend ready (PID $pid) — http://127.0.0.1:$BACKEND_PORT"
    else
        err "Backend failed to start — check $BACKEND_LOG"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

start_frontend() {
    # On Android/Termux, killed processes can leave TCP sockets in
    # TIME_WAIT (up to 120 s).  Wait for the port to free; fall back
    # to the next available port if 3000 stays stuck.
    local chosen_port="$FRONTEND_PORT"

    # Wait up to 15 s for port 3000 to free (TIME_WAIT).
    local waited=0
    while ! port_is_free "$chosen_port" && [ "$waited" -lt 15 ]; do
        sleep 1
        waited=$((waited + 1))
    done

    # If 3000 is still stuck, find the next free port.
    if ! port_is_free "$chosen_port"; then
        warn "Port $FRONTEND_PORT still stuck after ${waited}s — scanning for free port..."
        local offset=0
        while [ "$offset" -lt 20 ]; do
            offset=$((offset + 1))
            local try_port="$((FRONTEND_PORT + offset))"
            if port_is_free "$try_port"; then
                chosen_port="$try_port"
                warn "Using port $chosen_port instead"
                break
            fi
        done
    fi

    if ! port_is_free "$chosen_port"; then
        err "No free port available — giving up"
        return 1
    fi

    log "Starting Next.js frontend on port $chosen_port..."
    cd "$ROOT/web"
    nohup npm run dev -- --port "$chosen_port" > /dev/null 2>&1 &
    local pid=$!
    disown "$pid" 2>/dev/null || true

    if wait_for_http "http://127.0.0.1:$chosen_port" 60; then
        log "Frontend ready (PID $pid) — http://127.0.0.1:$chosen_port"
    else
        err "Frontend failed to start"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TARGET="${1:-all}"

case "$TARGET" in
    all)
        cleanup_zombies
        start_backend
        start_frontend
        ;;
    backend)
        cleanup_zombies
        start_backend
        ;;
    frontend)
        cleanup_zombies
        start_frontend
        ;;
    *)
        echo "Usage: $0 [all|backend|frontend]"
        exit 1
        ;;
esac

echo ""
log "All services ready:"
echo "  Backend:  http://127.0.0.1:$BACKEND_PORT/health"
echo "  Frontend: http://127.0.0.1:$FRONTEND_PORT"
