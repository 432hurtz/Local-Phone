"""Command execution: confirmation gate, scope enforcement, and logging."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

from .scope import Scope

# Commands the assistant should never run unattended, even with --auto.
# These are irreversible or clearly out-of-mission; require explicit confirmation.
_ALWAYS_CONFIRM = re.compile(
    r"\b(rm|mkfs|dd|shutdown|reboot|:\(\)\{|fork|passwd|useradd|userdel)\b"
)

# The single-line markers the model uses. RUN goes through the local/direct
# executor (scope-gated); SEARCH goes through the Tor research channel.
RUN_MARKER = re.compile(r"^\s*RUN:\s*(.+?)\s*$", re.MULTILINE)
SEARCH_MARKER = re.compile(r"^\s*SEARCH:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class ToolResult:
    command: str
    returncode: int
    output: str
    ran: bool
    reason: str = ""


class Executor:
    """Runs commands proposed by the model, subject to scope + confirmation."""

    def __init__(self, scope: Scope, console: Console, log_path: Path,
                 auto: bool = False, timeout: int = 300):
        self.scope = scope
        self.console = console
        self.log_path = log_path
        self.auto = auto
        self.timeout = timeout

    def run(self, command: str) -> ToolResult:
        command = command.strip()
        if not command:
            return ToolResult(command, -1, "", ran=False, reason="empty command")

        in_scope, out_of_scope = ([], [])
        if self.scope.enabled:
            in_scope, out_of_scope = self.scope.check_command(command)

        # Scope enforcement --------------------------------------------------
        if out_of_scope:
            self.console.print(
                f"[bold red]Scope violation:[/] {', '.join(out_of_scope)} "
                f"is not in scope.yaml."
            )
            if not Confirm.ask(
                "[bold red]Run anyway?[/] (only if you are authorized)",
                default=False, console=self.console,
            ):
                return self._record(command, -1, "", ran=False,
                                     reason=f"blocked: out of scope ({out_of_scope})")

        # Confirmation gate --------------------------------------------------
        dangerous = bool(_ALWAYS_CONFIRM.search(command))
        needs_prompt = dangerous or not self.auto or not self.scope.enabled

        self.console.print(f"\n[bold cyan]RUN:[/] {command}")
        if in_scope:
            self.console.print(f"[dim]  targets in scope: {', '.join(in_scope)}[/]")
        if dangerous:
            self.console.print("[bold yellow]  ⚠ potentially destructive command[/]")

        if needs_prompt:
            if not Confirm.ask("Execute?", default=not dangerous, console=self.console):
                return self._record(command, -1, "", ran=False, reason="declined by operator")

        # Execute ------------------------------------------------------------
        started = time.time()
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=self.timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            output = f"[timed out after {self.timeout}s]"
            rc = 124
        except Exception as e:  # noqa: BLE001 - surface any exec error to the model
            output = f"[execution error: {e}]"
            rc = 1
        elapsed = time.time() - started

        self.console.print(
            output.rstrip() or "[dim](no output)[/]",
            highlight=False,
        )
        self.console.print(f"[dim]  exit={rc}  {elapsed:.1f}s[/]")
        return self._record(command, rc, output, ran=True)

    # ------------------------------------------------------------------ log
    def _record(self, command: str, rc: int, output: str, *, ran: bool,
                reason: str = "") -> ToolResult:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {ts}  (ran={ran} rc={rc}) {reason}\n")
            fh.write(f"$ {command}\n")
            if output:
                fh.write(output.rstrip() + "\n")
        return ToolResult(command, rc, output, ran=ran, reason=reason)


def extract_commands(text: str) -> list[str]:
    """Return every `RUN:` command the model emitted, in order."""
    return [m.group(1).strip() for m in RUN_MARKER.finditer(text)]


def extract_searches(text: str) -> list[str]:
    """Return every `SEARCH:` research query/URL the model emitted, in order."""
    return [m.group(1).strip() for m in SEARCH_MARKER.finditer(text)]
