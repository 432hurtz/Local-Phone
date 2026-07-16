#!/data/data/com.termux/files/usr/bin/bash
#
# pull-model.sh — download a local model for the assistant.
#
# On a 12 GB device (Pixel 9) a 4-bit 7–8B model is the sweet spot: capable,
# ~4–5 GB resident, and fast enough for interactive use. Bigger models work but
# run hotter and slower.
#
# For an assistant that WON'T refuse legitimate offensive-security tasks, pick
# an uncensored or security-tuned model. Mainstream instruct models (llama3.1,
# qwen2.5) are heavily aligned and will decline a lot of real pentest work no
# matter what system prompt you use — the refusals are baked into the weights.
#
# Usage:  bash setup/pull-model.sh [model-name]

set -euo pipefail

# Default: an uncensored security-tuned model so offensive tasks aren't refused.
DEFAULT_MODEL="hf.co/TheBloke/WhiteRabbitNeo-13B-GGUF:Q4_K_M"

MODEL="${1:-$DEFAULT_MODEL}"

cat <<EOF
Model options (pick one and pass it as an argument):

  UNCENSORED / SECURITY-TUNED  (won't refuse offensive-security work)
    hf.co/TheBloke/WhiteRabbitNeo-13B-GGUF:Q4_K_M
                          Purpose-built offensive/defensive security  ~8 GB (default)
    dolphin-mistral:7b    Uncensored general model, fast              ~4.1 GB
    dolphin-llama3:8b     Uncensored, well-rounded                    ~4.9 GB
    huihui_ai/qwen2.5-abliterated:7b
                          Refusal-ablated Qwen2.5, strong reasoning   ~4.7 GB

  GENERAL (capable but heavily aligned — expect refusals on offensive tasks)
    qwen2.5:7b            General 7B                                   ~4.7 GB
    llama3.1:8b           General 8B                                   ~4.9 GB

Browse more at https://ollama.com/search — availability of community/HF models
varies; any GGUF on Hugging Face can be pulled with the hf.co/<repo>:<quant> form.

On 12 GB the 13B (~8 GB) fits but runs warm; drop to a 7–8B uncensored model
(dolphin-mistral / qwen2.5-abliterated) if you want it snappier and cooler.

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
