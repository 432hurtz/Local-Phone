#!/data/data/com.termux/files/usr/bin/bash
#
# pull-model.sh — download a local model for the assistant.
#
# On a 12 GB device (Pixel 9) a 4-bit 7–8B model is the sweet spot: capable,
# ~4–5 GB resident, and fast enough for interactive use. Bigger models work but
# run hotter and slower.
#
# Usage:  bash setup/pull-model.sh [model-name]

set -euo pipefail

# Default: a strong general 7B instruct model (good recon reasoning + explains
# tool output well). Override by passing a name or editing DEFAULT_MODEL.
DEFAULT_MODEL="qwen2.5:7b"

MODEL="${1:-$DEFAULT_MODEL}"

cat <<EOF
Model options (pick one and pass it as an argument):

  qwen2.5:7b        General 7B, strong reasoning         ~4.7 GB   (default)
  llama3.1:8b       General 8B, well-rounded             ~4.9 GB
  mistral:7b        Fast, lightweight                    ~4.1 GB
  deepseek-coder-v2:16b   Heavier, strong at code/exploits  ~9 GB  (needs headroom)

Security-tuned community models (for offensive/defensive reasoning) can be
browsed at https://ollama.com/search?q=security — availability varies.

Pulling: $MODEL
EOF

# Make sure the runtime is up.
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[!] Ollama server not responding on :11434 — starting it in the background."
  (ollama serve >/dev/null 2>&1 &) || {
    echo "[x] Could not start 'ollama serve'. Start it manually and re-run." >&2
    exit 1
  }
  sleep 3
fi

ollama pull "$MODEL"

echo
echo "[+] Pulled $MODEL"
echo "    Set it as default in config.yaml (model: $MODEL) or pass --model $MODEL."
