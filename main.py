#!/usr/bin/env python3
"""Local-Phone — on-device red-team assistant.

Entry point: wires config, scope, the LLM backend, and the execution gate
together, then drops into an interactive session.

Authorized security testing and research only.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console

from assistant.agent import Agent
from assistant.llm import build_backend, LLMError
from assistant.notify import Notifier
from assistant.research import Researcher
from assistant.scope import Scope
from assistant.tools import Executor

ROOT = Path(__file__).resolve().parent


def load_config(path: Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="On-device red-team assistant.")
    p.add_argument("--config", default=str(ROOT / "config.yaml"),
                   help="Path to config.yaml.")
    p.add_argument("--scope", default=str(ROOT / "scope.yaml"),
                   help="Path to the engagement scope file.")
    p.add_argument("--model", default=None, help="Override the model name.")
    p.add_argument("--backend", default=None, choices=["ollama", "api"],
                   help="LLM backend override.")
    p.add_argument("--auto", action="store_true",
                   help="Auto-run in-scope, non-destructive commands.")
    p.add_argument("--no-scope", action="store_true",
                   help="Disable scope enforcement (lab/CTF only).")
    p.add_argument("--log", default=None, help="Session transcript path.")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    console = Console()

    config = load_config(Path(args.config))

    # --- scope ---------------------------------------------------------------
    scope_path = Path(args.scope)
    if args.no_scope:
        scope = Scope(enabled=False)
        console.print("[yellow]⚠ Scope enforcement disabled. Lab/CTF use only.[/]")
    elif scope_path.exists():
        scope = Scope.load(scope_path)
        if not scope.hosts and not scope.networks:
            console.print(
                "[yellow]⚠ scope.yaml has no targets. Every target will need "
                "manual confirmation. Add your authorized targets.[/]"
            )
    else:
        # No scope file: start in research/build mode rather than refusing to
        # launch. Chat, tool creation, and Tor research all work; executing a
        # command against a target stays blocked until targets are added to
        # scope.yaml (an empty scope treats every target as out of scope).
        scope = Scope()
        console.print(
            "[yellow]No scope.yaml — research/build mode. Research and tool "
            "creation work; executing against a target is blocked until you add "
            "authorized targets to scope.yaml.[/]"
        )

    # --- llm backend ---------------------------------------------------------
    try:
        backend = build_backend(config, args.model, args.backend)
    except LLMError as e:
        console.print(f"[red]{e}[/]")
        return 1

    if hasattr(backend, "available") and not backend.available():
        # Try to bring a local backend up on our own before giving up.
        starter = getattr(backend, "start_server", None)
        if starter:
            console.print("[yellow]Ollama not running — starting it…[/]")
        if not (starter and starter()):
            console.print(
                "[red]LLM backend is not reachable.[/] For the local backend, run "
                "'ollama serve' and pull a model with setup/pull-model.sh."
            )
            return 1

    console.print(f"[dim]model={backend.model}[/]")

    # --- logging -------------------------------------------------------------
    sessions_dir = ROOT / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    log_path = Path(args.log) if args.log else (
        sessions_dir / f"session-{datetime.now():%Y%m%d-%H%M%S}.md"
    )
    log_path.write_text(f"# Local-Phone session {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    console.print(f"[dim]log={log_path}[/]")

    # --- run -----------------------------------------------------------------
    executor = Executor(
        scope=scope, console=console, log_path=log_path,
        auto=args.auto, timeout=config.get("command_timeout", 300),
    )
    researcher = Researcher(config, console, log_path)
    if researcher.enabled:
        status = "up" if researcher.tor_up() else "DOWN (searches will fail-closed)"
        console.print(f"[dim]tor research proxy: {researcher.socks} — {status}[/]")

    notifier = Notifier(config, console)
    if notifier.enabled:
        wl = "on" if notifier._have_wake else "unavailable"
        nt = "on" if notifier._have_notify else "install termux-api for alerts"
        console.print(f"[dim]wakelock: {wl} · notifications: {nt}[/]")

    agent = Agent(backend, executor, researcher, notifier, console)
    try:
        agent.repl()
    finally:
        notifier.wake_unlock()  # never leave a wakelock held on exit
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
