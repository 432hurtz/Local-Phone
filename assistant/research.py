"""Tor-routed research / OSINT lookups.

This is the ONLY component that reaches the public internet, and it always goes
through Tor. It exists so the operator can look things up (CVE details, docs,
OSINT, a web page) without exposing their real IP.

Privacy guarantee: it fails CLOSED. If the Tor SOCKS proxy isn't reachable it
refuses to fetch rather than falling back to the clear interface — a search
never silently leaves Tor.

Deliberately separate from tools.py: scans and target commands go through the
direct interface (RUN:), research goes through Tor (SEARCH:). The two never mix.
"""

from __future__ import annotations

import html
import re
import socket
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from rich.console import Console

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_INLINE_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_RE = re.compile(r"\n\s*\n\s*")
_URL_RE = re.compile(r"^https?://", re.I)


@dataclass
class ResearchResult:
    query: str
    url: str
    ok: bool
    text: str


class Researcher:
    """Fetches web/OSINT results strictly over Tor."""

    def __init__(self, config: dict, console: Console, log_path: str | Path):
        cfg = config.get("research", {}) or {}
        self.enabled = cfg.get("enabled", True)
        self.socks = cfg.get("tor_socks", "socks5h://127.0.0.1:9050")
        self.search_url = cfg.get(
            "search_url", "https://lite.duckduckgo.com/lite/?q={query}"
        )
        self.user_agent = cfg.get(
            "user_agent",
            "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
        )
        self.timeout = int(cfg.get("timeout", 45))
        self.fail_closed = bool(cfg.get("fail_closed", True))
        self.max_chars = int(cfg.get("max_chars", 6000))
        self.console = console
        self.log_path = Path(log_path)
        self._host, self._port = _parse_socks(self.socks)

    # -- public API ----------------------------------------------------------
    def tor_up(self) -> bool:
        """True if the Tor SOCKS proxy is accepting connections."""
        try:
            with socket.create_connection((self._host, self._port), timeout=3):
                return True
        except OSError:
            return False

    def fetch(self, target: str) -> ResearchResult:
        """Fetch a URL directly, or run a search if `target` is a bare query."""
        target = target.strip()
        if _URL_RE.match(target):
            return self._get(target, target)
        return self.search(target)

    def search(self, query: str) -> ResearchResult:
        url = self.search_url.format(query=urllib.parse.quote_plus(query))
        return self._get(query, url)

    # -- internals -----------------------------------------------------------
    def _get(self, label: str, url: str) -> ResearchResult:
        if not self.enabled:
            return self._fail(label, url, "research is disabled in config")

        # Fail closed: never fetch unless Tor is actually up.
        if not self.tor_up():
            reason = (
                f"Tor SOCKS proxy not reachable at {self._host}:{self._port} — "
                f"start it with 'tor &'. Nothing was fetched (fail-closed)."
            )
            return self._fail(label, url, reason)

        self.console.print(f"[magenta]SEARCH (via Tor):[/] {url}")
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                proxies={"http": self.socks, "https": self.socks},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            return self._fail(label, url, f"request failed over Tor: {e}")

        text = _html_to_text(resp.text)[: self.max_chars]
        self.console.print(f"[dim]  {len(text)} chars via Tor exit node[/]")
        return self._record(ResearchResult(label, url, True, text))

    def _fail(self, label: str, url: str, reason: str) -> ResearchResult:
        self.console.print(f"[yellow]SEARCH unavailable:[/] {reason}")
        return self._record(ResearchResult(label, url, False, f"[{reason}]"))

    def _record(self, result: ResearchResult) -> ResearchResult:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {ts}  SEARCH (tor) ok={result.ok}\n")
            fh.write(f"query/url: {result.query} -> {result.url}\n")
        return result


def _parse_socks(uri: str) -> tuple[str, int]:
    m = re.match(r"socks5h?://([^:/]+):(\d+)", uri, re.I)
    if not m:
        return "127.0.0.1", 9050
    return m.group(1), int(m.group(2))


def _html_to_text(raw: str) -> str:
    """Crude HTML → text: drop script/style, strip tags, tidy whitespace."""
    raw = _SCRIPT_RE.sub(" ", raw)
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = _INLINE_WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n", text)
    return text.strip()
