"""The chat + tool-execution loop."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

from .llm import LLMError
from .prompts import SYSTEM_PROMPT
from .research import Researcher
from .tools import Executor, extract_commands, extract_searches

# Cap on consecutive automatic tool rounds before we hand control back to the
# operator — stops the model from looping on tool calls forever.
MAX_TOOL_ROUNDS = 6


class Agent:
    def __init__(self, backend, executor: Executor, researcher: Researcher,
                 console: Console):
        self.backend = backend
        self.executor = executor
        self.researcher = researcher
        self.console = console
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _generate(self) -> tuple[str, bool]:
        """Stream one assistant turn, printing as it arrives.

        Returns (text_so_far, interrupted). Ctrl-C during streaming stops the
        reply (and the server-side generation, by closing the connection) and
        hands control back — it does not exit the program.
        """
        self.console.print("[bold green]assistant[/] ", end="")
        parts: list[str] = []
        interrupted = False
        stream = self.backend.stream(self.messages)
        try:
            for piece in stream:
                self.console.print(piece, end="", highlight=False)
                parts.append(piece)
        except KeyboardInterrupt:
            interrupted = True
            self.console.print("\n[yellow][stopped][/]")
        finally:
            # Closing the generator exits the `with requests.post(...)` block,
            # which drops the connection and tells the model to stop generating.
            close = getattr(stream, "close", None)
            if close:
                close()
        if not interrupted:
            self.console.print()  # newline
        return "".join(parts), interrupted

    def _run_searches(self, queries: list[str]) -> list[str]:
        """Run each research query over Tor; return blocks for the model."""
        blocks = []
        for q in queries:
            result = self.researcher.fetch(q)
            status = "ok" if result.ok else "unavailable"
            blocks.append(
                f"SEARCH (via Tor) {q!r} [{status}]\n{result.text.strip()}"
            )
        return blocks

    def _run_commands(self, commands: list[str]) -> list[str]:
        """Run each command through the scope-gated executor."""
        blocks = []
        for cmd in commands:
            result = self.executor.run(cmd)
            state = "ran" if result.ran else f"NOT RUN ({result.reason})"
            blocks.append(
                f"$ {result.command}\n[{state}, exit={result.returncode}]\n"
                f"{result.output.strip()}"
            )
        return blocks

    def send(self, user_input: str) -> None:
        """Handle one operator message, including any tool-call rounds."""
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                reply, interrupted = self._generate()
            except LLMError as e:
                self.console.print(f"[bold red]LLM error:[/] {e}")
                return
            self.messages.append({"role": "assistant", "content": reply})
            if interrupted:
                return  # operator stopped it; don't act on a partial reply

            searches = extract_searches(reply)
            commands = extract_commands(reply)
            if not searches and not commands:
                return  # plain answer / question — hand back to operator

            # Research (Tor) first, then local/target commands (direct).
            blocks = self._run_searches(searches) + self._run_commands(commands)
            self.messages.append({
                "role": "user",
                "content": "Results:\n\n" + "\n\n".join(blocks)
                           + "\n\nInterpret these and continue, or ask me for input.",
            })
        else:
            self.console.print(
                "[yellow]Reached the tool-round limit for this turn. "
                "Type 'continue' to let it keep going.[/]"
            )

    def _operator_search(self, query: str) -> None:
        """Operator-initiated Tor search: fetch, then let the model summarize."""
        if not query.strip():
            self.console.print("[yellow]usage: /search <query or url>[/]")
            return
        block = self._run_searches([query])[0]
        self.messages.append({
            "role": "user",
            "content": f"I ran this research lookup over Tor:\n\n{block}\n\n"
                       f"Summarize the relevant findings.",
        })
        try:
            reply, _ = self._generate()
        except LLMError as e:
            self.console.print(f"[bold red]LLM error:[/] {e}")
            return
        self.messages.append({"role": "assistant", "content": reply})

    def repl(self) -> None:
        self.console.print(
            Markdown(
                "**Local-Phone** — on-device red-team assistant. "
                "Authorized targets only. `/search <q>` researches over Tor. "
                "**Ctrl-C** stops the current reply; type `exit` (or Ctrl-D) to quit."
            )
        )
        while True:
            try:
                user_input = self.console.input("\n[bold blue]you[/] ").strip()
            except KeyboardInterrupt:
                # Ctrl-C at the prompt cancels the line, it does not quit.
                self.console.print("[dim](ctrl-c — type 'exit' or Ctrl-D to quit)[/]")
                continue
            except EOFError:
                self.console.print("\n[dim]bye[/]")
                return
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", ":q"}:
                self.console.print("[dim]bye[/]")
                return
            if user_input.startswith("/search "):
                self._operator_search(user_input[len("/search "):])
                continue
            self.send(user_input)
