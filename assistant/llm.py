"""LLM backends.

`OllamaBackend` talks to a local Ollama server (the default — nothing leaves the
device). `APIBackend` is an optional OpenAI-compatible chat fallback for when
the operator explicitly wants a remote model.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Iterator

import requests


class LLMError(RuntimeError):
    pass


class LLMConnectionError(LLMError):
    """Raised when the backend server can't be reached (e.g. Ollama is down)."""


class OllamaBackend:
    """Streaming chat client for a local Ollama server."""

    def __init__(self, model: str, host: str = "http://localhost:11434",
                 options: dict | None = None):
        self.model = model
        self.host = host.rstrip("/")
        self.options = options or {}

    def available(self) -> bool:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            return r.ok
        except requests.RequestException:
            return False

    def start_server(self, wait: int = 30) -> bool:
        """(Re)start a local `ollama serve` and wait for it to answer.

        Used to auto-recover when the server process has been killed (common on
        phones under memory pressure). Only meaningful for a local host; returns
        True once the server responds, False if it can't be started.
        """
        if self.available():
            return True
        try:
            # Detached so it survives this process and isn't hit by our Ctrl-C.
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError):
            return False
        for _ in range(wait):
            if self.available():
                return True
            time.sleep(1)
        return False

    def stream(self, messages: list[dict]) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": self.options,
        }
        try:
            with requests.post(
                f"{self.host}/api/chat", json=payload, stream=True, timeout=600
            ) as resp:
                if resp.status_code == 404:
                    raise LLMError(
                        f"Model '{self.model}' not found. "
                        f"Pull it with: ollama pull {self.model}"
                    )
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise LLMError(chunk["error"])
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except requests.RequestException as e:
            raise LLMConnectionError(
                f"Could not reach Ollama at {self.host}. Is 'ollama serve' running? ({e})"
            ) from e


class APIBackend:
    """Optional OpenAI-compatible remote chat backend (opt-in)."""

    def __init__(self, model: str, base_url: str, api_key_env: str = "LLM_API_KEY",
                 options: dict | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ.get(api_key_env, "")
        self.options = options or {}

    def available(self) -> bool:
        return bool(self.api_key)

    def stream(self, messages: list[dict]) -> Iterator[str]:
        if not self.api_key:
            raise LLMError("No API key set for the remote backend.")
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **self.options,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                json=payload, headers=headers, stream=True, timeout=600,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith(b"data: "):
                        continue
                    data = line[len(b"data: "):]
                    if data.strip() == b"[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
        except requests.RequestException as e:
            raise LLMError(f"Remote API request failed: {e}") from e


def build_backend(config: dict, model_override: str | None,
                  backend_override: str | None):
    """Construct the configured LLM backend."""
    kind = backend_override or config.get("backend", "ollama")
    model = model_override or config.get("model", "qwen2.5:7b")
    options = config.get("options", {})

    if kind == "ollama":
        ocfg = config.get("ollama", {})
        return OllamaBackend(
            model=model,
            host=ocfg.get("host", "http://localhost:11434"),
            options=options,
        )
    if kind == "api":
        acfg = config.get("api", {})
        return APIBackend(
            model=model,
            base_url=acfg.get("base_url", "https://api.openai.com/v1"),
            api_key_env=acfg.get("api_key_env", "LLM_API_KEY"),
            options=options,
        )
    raise LLMError(f"Unknown backend: {kind!r}")
