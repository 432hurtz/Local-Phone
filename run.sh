#!/data/data/com.termux/files/usr/bin/bash
#
# run.sh — one-command launcher.
#
# Give it the model you want and it does the rest: starts Ollama and Tor if they
# aren't already running, pulls the model if it isn't present yet, then launches
# the assistant with that model.
#
#     bash run.sh dolphin-mistral:7b
#     bash run.sh qwen2.5:7b --auto
#     bash run.sh                       # no model => use the one in config.yaml
#
# The first bare word is the model. Anything else is passed through to main.py.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

LOGDIR="$ROOT/sessions"
mkdir -p "$LOGDIR"

say()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

# --- parse args: first non-flag token is the model ----------------------------
MODEL=""
if [ "$#" -gt 0 ] && [ "${1#-}" = "$1" ]; then
  MODEL="$1"; shift
fi
# remaining "$@" is passed straight to main.py

# --- readiness checks ---------------------------------------------------------
ollama_up() { curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; }

tor_up() {
  python3 - <<'PY'
import socket, sys
s = socket.socket(); s.settimeout(2)
sys.exit(0 if s.connect_ex(("127.0.0.1", 9050)) == 0 else 1)
PY
}

wait_until() {  # <check-fn> <timeout-seconds> <human-name>
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

# --- Ollama (must be up before we can pull/list models) -----------------------
if ollama_up; then
  say "Ollama already running."
else
  say "Starting Ollama (log: $LOGDIR/ollama.log)…"
  nohup ollama serve >"$LOGDIR/ollama.log" 2>&1 &
  wait_until ollama_up 30 "Ollama" || warn "Continuing; the model backend may be unavailable."
fi

# --- ensure the requested model is present ------------------------------------
if [ -n "$MODEL" ]; then
  if ollama list 2>/dev/null | grep -q -- "$MODEL"; then
    say "Model '$MODEL' already pulled."
  else
    say "Pulling model '$MODEL' (first time only)…"
    ollama pull "$MODEL" || { warn "Failed to pull '$MODEL'."; exit 1; }
  fi
fi

# --- Tor (research/SEARCH channel) --------------------------------------------
if tor_up; then
  say "Tor already running."
else
  say "Starting Tor (log: $LOGDIR/tor.log)…"
  nohup tor >"$LOGDIR/tor.log" 2>&1 &
  if wait_until tor_up 60 "Tor SOCKS proxy"; then
    for _ in $(seq 1 30); do
      grep -q "Bootstrapped 100%" "$LOGDIR/tor.log" 2>/dev/null && { say "Tor bootstrapped."; break; }
      sleep 1
    done
  else
    warn "Tor not ready; SEARCH lookups will fail closed until it bootstraps."
  fi
fi

# --- launch the assistant -----------------------------------------------------
say "Launching assistant…"
if [ -n "$MODEL" ]; then
  exec python3 main.py --model "$MODEL" "$@"
else
  exec python3 main.py "$@"
fi
