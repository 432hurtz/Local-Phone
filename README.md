# Local-Phone — On-Device Red-Team Assistant

A fully local, on-device AI assistant for **authorized** penetration testing,
security research, and learning — built to run on an Android phone (tested
target: **Pixel 9 / Tensor G4 / 12 GB RAM / Android 16**) inside
[Termux](https://termux.dev).

Everything runs on the handset: the language model (via
[Ollama](https://ollama.com)), the toolchain, and the agent loop. Nothing is
sent to a cloud service unless you deliberately configure an API backend.

```
┌──────────────────────────────────────────────┐
│  Termux (Android)                              │
│                                                │
│   local-phone  ──chat──►  Ollama (localhost)   │
│       │                     └─ local model     │
│       │ RUN: <cmd>                             │
│       ▼                                        │
│   confirm + scope gate ──► nmap / nuclei / …   │
│       │                                        │
│       └──── command output ──► back to model   │
└──────────────────────────────────────────────┘
```

---

## ⚠️ Authorized use only

This is offensive tooling. Only run it against systems you **own** or have
**explicit written permission** to test. The assistant enforces a scope file
(`scope.yaml`) and will refuse / warn on out-of-scope targets, but that is a
safety rail, not a license. Unauthorized access to computer systems is illegal
in most jurisdictions. You are responsible for staying in scope and in the law.

---

## Why a phone works here

The Pixel 9 has a Tensor G4 and 12 GB of RAM. That comfortably runs a 7–8B
parameter model quantized to 4-bit (~4–5 GB resident), leaving headroom for
the toolchain. You get a genuinely capable local assistant with no data
leaving the device — good for field work, air-gapped labs, and privacy.

---

## Install (Pixel 9 / Termux)

1. Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/)
   (the Play Store build is outdated — use F-Droid or GitHub releases).

2. Clone this repo inside Termux and run the installer:

   ```bash
   pkg install -y git
   git clone https://github.com/432hurtz/local-phone
   cd local-phone
   bash setup/install.sh
   ```

   The installer sets up Python, Ollama, the common recon toolchain, and the
   assistant's Python dependencies.

3. Pull a model (defaults to a security-capable 7B; see
   [`setup/pull-model.sh`](setup/pull-model.sh) for alternatives):

   ```bash
   bash setup/pull-model.sh
   ```

4. Configure your engagement:

   ```bash
   cp config.example.yaml config.yaml
   cp scope.example.yaml scope.yaml
   $EDITOR scope.yaml     # add the hosts/CIDRs you are authorized to test
   ```

5. Run it:

   ```bash
   bash run.sh            # starts Ollama + Tor if needed, then the assistant
   ```

   `run.sh` is the one-command launcher: it brings up Ollama (model runtime)
   and Tor (research channel) only if they aren't already running, waits until
   each is ready, then starts the assistant. Arguments pass straight through
   (`bash run.sh --auto`). To run pieces by hand instead, see
   [Manual start](#manual-start) below.

---

## Usage

You chat with the assistant in plain English ("do a service scan of the lab
box", "help me understand this nuclei finding"). When it wants to run a
command it emits a line like:

```
RUN: nmap -sV -T4 10.10.10.5
```

The agent:

1. Parses the target(s) out of the command.
2. Checks them against `scope.yaml`.
3. Asks you to confirm (unless `--auto` and the target is in scope).
4. Runs it, logs it, and feeds the output back to the model so it can
   interpret results and plan the next step.

### Research over Tor (privacy)

Web/OSINT lookups use a separate channel that always goes through **Tor**, so
your real IP is never exposed to search engines or the sites you look up. The
model requests these with a `SEARCH:` line, and you can trigger one yourself:

```
you ▸ /search CVE-2024-3400 pan-os exploit details
```

Key properties:

- **Tor-only, and fails closed.** If Tor isn't running, searches are *refused*,
  never sent over your real connection. Start Tor with `tor &`.
- **Research only.** This channel is for reading public information. It never
  touches your engagement target — scans and target commands (`RUN:`) stay on
  the direct interface and are scope-gated as usual.
- Configure it under `research:` in `config.yaml` (proxy, search endpoint,
  timeout, fetched-text cap).

### Manual start

`run.sh` is just a convenience wrapper. To run the three pieces yourself, use a
separate Termux session for each background service:

```bash
ollama serve            # session A — model runtime
tor                     # session B — research channel (wait for "Bootstrapped 100%")
python main.py          # session C — the assistant
```

### Handy flags

| Flag              | Effect                                                       |
| ----------------- | ------------------------------------------------------------ |
| `--auto`          | Auto-run in-scope commands without a prompt (still logs).    |
| `--model NAME`    | Override the model for this session.                         |
| `--backend ollama`| LLM backend: `ollama` (default, local) or `api`.             |
| `--no-scope`      | Disable scope enforcement (lab/CTF only — logs a warning).   |
| `--log FILE`      | Path for the session transcript (default `sessions/…`).      |

---

## What's in the box

- `setup/install.sh` — Termux bootstrap (packages, Ollama, Python deps).
- `setup/pull-model.sh` — pull/pick a local model.
- `assistant/llm.py` — local LLM client (Ollama) + optional API fallback.
- `assistant/tools.py` — command execution with confirmation + logging.
- `assistant/scope.py` — engagement-scope parsing and target matching.
- `assistant/prompts.py` — the red-team system prompt.
- `assistant/agent.py` — the chat + tool-execution loop.
- `main.py` — CLI entry point.

---

## Model choice — and refusals

Refusals mostly live in the **model weights**, not the system prompt. A heavily
aligned mainstream model (llama3.1, qwen2.5) will decline plenty of legitimate
offensive-security tasks no matter how you prompt it. Because this runs on
hardware you control, the fix is to pick an **uncensored / security-tuned**
model:

| Model | Notes | Size |
| ----- | ----- | ---- |
| `hf.co/TheBloke/WhiteRabbitNeo-13B-GGUF:Q4_K_M` | Purpose-built offensive/defensive security (default) | ~8 GB |
| `dolphin-mistral:7b` | Uncensored, fast | ~4.1 GB |
| `dolphin-llama3:8b` | Uncensored, well-rounded | ~4.9 GB |
| `huihui_ai/qwen2.5-abliterated:7b` | Refusal-ablated, strong reasoning | ~4.7 GB |

The system prompt is written to be direct and to skip moralizing preambles on
security work. Paired with one of the models above, the assistant answers
offensive-security questions straight instead of refusing them.

The 13B (~8 GB) fits in the Pixel 9's 12 GB but runs warm; drop to a 7–8B
uncensored model for a snappier, cooler session. `setup/pull-model.sh` lists
all options.

The **operational** guardrails stay in place regardless of model: the scope
gate and the execute-confirmation step protect your own device and keep you
inside your engagement's target list.

---

## License

Provided for authorized security testing and education. See
[`LICENSE`](LICENSE).
