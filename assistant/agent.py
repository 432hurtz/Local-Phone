"""The chat + tool-execution loop."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

from .llm import LLMError
from .prompts import SYSTEM_PROMPT
from .tools import Executor, extract_commands

# Cap on consecutive automatic RUN rounds before we hand control back to the
# operator — stops the model from looping on tool calls forever.
MAX_TOOL_ROUNDS = 6


class Agent:
    def __init__(self, backend, executor: Executor, console: Console):
        self.backend = backend
        self.executor = executor
        self.console = console
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _generate(self) -> str:
        """Stream one assistant turn, printing as it arrives; return full text."""
        self.console.print("[bold green]assistant[/] ", end="")
        parts: list[str] = []
        for piece in self.backend.stream(self.messages):
            self.console.print(piece, end="", highlight=False)
            parts.append(piece)
        self.console.print()  # newline
        return "".join(parts)

    def send(self, user_input: str) -> None:
        """Handle one operator message, including any tool-call rounds."""
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                reply = self._generate()
            except LLMError as e:
                self.console.print(f"[bold red]LLM error:[/] {e}")
                return
            self.messages.append({"role": "assistant", "content": reply})

            commands = extract_commands(reply)
            if not commands:
                return  # plain answer / question — hand back to operator

            # Run each proposed command and feed results back for the next round.
            results_blob = []
            for cmd in commands:
                result = self.executor.run(cmd)
                status = "ran" if result.ran else f"NOT RUN ({result.reason})"
                results_blob.append(
                    f"$ {result.command}\n[{status}, exit={result.returncode}]\n"
                    f"{result.output.strip()}"
                )
            self.messages.append({
                "role": "user",
                "content": "Command results:\n\n" + "\n\n".join(results_blob)
                           + "\n\nInterpret these and continue, or ask me for input.",
            })
        else:
            self.console.print(
                "[yellow]Reached the tool-round limit for this turn. "
                "Type 'continue' to let it keep going.[/]"
            )

    def repl(self) -> None:
        self.console.print(
            Markdown(
                "**Local-Phone** — on-device red-team assistant. "
                "Authorized targets only. Type `exit` to quit."
            )
        )
        while True:
            try:
                user_input = self.console.input("\n[bold blue]you[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]bye[/]")
                return
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", ":q"}:
                self.console.print("[dim]bye[/]")
                return
            self.send(user_input)
