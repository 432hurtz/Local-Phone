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
   python main.py
   ```

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

## Model choice

The default is a general 7–8B instruct model, which is a good all-rounder for
recon reasoning and explaining output. For heavier offensive/defensive
security reasoning, `setup/pull-model.sh` also lists security-tuned community
models. Larger models are slower on-device; start small and scale up if your
thermals/RAM allow.

---

## License

Provided for authorized security testing and education. See
[`LICENSE`](LICENSE).
