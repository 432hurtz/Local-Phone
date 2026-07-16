#!/data/data/com.termux/files/usr/bin/bash
#
# install.sh — bootstrap the Local-Phone red-team assistant on Termux (Android).
# Target: Pixel 9 / arm64 / Android 16, but works on any recent Termux install.
#
# Idempotent: safe to re-run.

set -euo pipefail

say()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

# --- sanity: are we in Termux? -------------------------------------------------
if [ -z "${PREFIX:-}" ] || [ ! -d /data/data/com.termux ]; then
  warn "This doesn't look like Termux. Continuing anyway, but paths may differ."
fi

# --- base packages -------------------------------------------------------------
say "Updating package lists…"
pkg update -y && pkg upgrade -y

say "Installing base packages…"
# python/git/build tools + a practical on-device recon toolchain.
pkg install -y \
  python \
  git \
  curl \
  wget \
  openssh \
  nmap \
  ncat \
  tsu \
  jq \
  dnsutils \
  net-tools \
  tcpdump \
  whois \
  tor \
  || warn "Some packages failed to install; you can add them individually later."

# Optional heavier tools — don't fail the whole install if a repo lacks them.
say "Installing optional security tools (best-effort)…"
for p in hydra nikto sqlmap; do
  pkg install -y "$p" 2>/dev/null && say "  installed $p" || warn "  skipped $p (not in repo)"
done

# --- Ollama (local LLM runtime) ------------------------------------------------
if command -v ollama >/dev/null 2>&1; then
  say "Ollama already installed."
else
  say "Installing Ollama…"
  # Termux ships an ollama package on many mirrors; fall back to the script.
  if pkg install -y ollama 2>/dev/null; then
    say "  installed ollama from Termux repo."
  else
    warn "  ollama not in Termux repo; trying the official install script."
    curl -fsSL https://ollama.com/install.sh | sh \
      || die "Ollama install failed. Install it manually, then re-run this script."
  fi
fi

# --- Python dependencies -------------------------------------------------------
say "Installing Python dependencies…"
python -m pip install --upgrade pip
python -m pip install -r "$(dirname "$0")/../requirements.txt"

# --- config scaffolding --------------------------------------------------------
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/config.yaml" ] || { cp "$ROOT/config.example.yaml" "$ROOT/config.yaml"; say "Created config.yaml"; }
[ -f "$ROOT/scope.yaml" ]  || { cp "$ROOT/scope.example.yaml"  "$ROOT/scope.yaml";  say "Created scope.yaml (EDIT THIS before testing)"; }
mkdir -p "$ROOT/sessions"

cat <<'EOF'

[+] Base install complete.

Next:
  1) Edit your engagement scope:      $EDITOR scope.yaml
  2) Launch everything with a model:  bash run.sh dolphin-mistral:7b

  run.sh starts Ollama + Tor if they aren't already up, pulls the model if you
  don't have it yet, then starts the assistant with it. Omit the model to use
  the one in config.yaml. To run the pieces by hand instead:
     ollama serve &   |   tor &   |   python main.py --model <name>

Notes:
  - Tor powers only the research/SEARCH channel (web/OSINT lookups) for privacy.
    Scans and target commands never go through it. If Tor isn't running,
    searches fail closed (they are refused, never sent in the clear).
  - Authorized targets only. Keep scope.yaml accurate.
EOF
