#!/data/data/com.termux/files/usr/bin/bash
#
# run.sh — one-command launcher.
#
# Brings up the two background services the assistant needs — Ollama (local
# model runtime) and Tor (the research/SEARCH channel) — only if they aren't
# already running, waits until each is ready, then starts the assistant.
#
# Any arguments are passed straight through to main.py, e.g.:
#     bash run.sh --auto
#     bash run.sh --model dolphin-mistral:7b

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

LOGDIR="$ROOT/sessions"
mkdir -p "$LOGDIR"

say()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

# --- readiness checks ----------------------------------------------------------
ollama_up() { curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; }

# True when the Tor SOCKS port is accepting connections.
tor_up() {
  python3 - <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(2)
sys.exit(0 if s.connect_ex(("127.0.0.1", 9050)) == 0 else 1)
PY
}

# wait_until <check-fn> <timeout-seconds> <human-name>
wait_until() {
  local fn="$1" timeout="$2" name="$3" i=0
  while ! "$fn"; do
    i=$((i + 1))
    if [ "$i" -ge "$timeout" ]; then
      warn "$name did not become ready within ${timeout}s (check $LOGDIR)."
      return 1
    fi
    sleep 1
  done
  say "$name is ready."
}

# --- Ollama --------------------------------------------------------------------
if ollama_up; then
  say "Ollama already running."
else
  say "Starting Ollama (log: $LOGDIR/ollama.log)…"
  nohup ollama serve >"$LOGDIR/ollama.log" 2>&1 &
  wait_until ollama_up 30 "Ollama" || warn "Continuing; the model backend may be unavailable."
fi

# --- Tor (research channel) ----------------------------------------------------
if tor_up; then
  say "Tor already running."
else
  say "Starting Tor (log: $LOGDIR/tor.log)…"
  nohup tor >"$LOGDIR/tor.log" 2>&1 &
  if wait_until tor_up 60 "Tor SOCKS proxy"; then
    # SOCKS port is open; give circuits a moment to finish bootstrapping so the
    # first search doesn't fail. Best-effort — the research channel is
    # fail-closed anyway, so a not-yet-ready Tor just refuses rather than leaks.
    for _ in $(seq 1 30); do
      grep -q "Bootstrapped 100%" "$LOGDIR/tor.log" 2>/dev/null && { say "Tor bootstrapped."; break; }
      sleep 1
    done
  else
    warn "Tor not ready; SEARCH lookups will fail closed until it bootstraps."
  fi
fi

# --- assistant -----------------------------------------------------------------
say "Launching assistant…"
exec python3 main.py "$@"
