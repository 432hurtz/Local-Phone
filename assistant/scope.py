"""Engagement-scope parsing and target matching.

The scope file declares the hosts, domains, and CIDR ranges the operator is
authorized to test. Before any command runs, the agent extracts target-looking
tokens from it and checks them here.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Tokens in a command that look like a host/IP we should scope-check.
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
_HOST_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
)
# Tokens that are hosts syntactically but never real targets.
_IGNORE_HOSTS = {"localhost"}


@dataclass
class Scope:
    """A parsed engagement scope."""

    hosts: set[str] = field(default_factory=set)
    networks: list[ipaddress._BaseNetwork] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def load(cls, path: str | Path) -> "Scope":
        """Load a scope from a YAML file.

        Expected shape:
            targets:
              - 10.10.10.0/24
              - 192.168.1.50
              - lab.example.com
        Bare IPs, CIDRs, and hostnames may be mixed freely.
        """
        data = yaml.safe_load(Path(path).read_text()) or {}
        targets = data.get("targets") or []
        scope = cls()
        for raw in targets:
            token = str(raw).strip().lower()
            if not token:
                continue
            net = _as_network(token)
            if net is not None:
                scope.networks.append(net)
            else:
                scope.hosts.add(token)
        return scope

    def contains(self, target: str) -> bool:
        """True if `target` (an IP, CIDR, or hostname) is in scope."""
        token = target.strip().lower().rstrip(".")
        if not token:
            return False
        net = _as_network(token)
        if net is not None:
            return any(_net_subset(net, allowed) for allowed in self.networks)
        # Hostname: exact match or a subdomain of an allowed host.
        return any(token == h or token.endswith("." + h) for h in self.hosts)

    def check_command(self, command: str) -> tuple[list[str], list[str]]:
        """Return (in_scope_targets, out_of_scope_targets) found in a command."""
        found = _extract_targets(command)
        in_scope, out = [], []
        for t in found:
            (in_scope if self.contains(t) else out).append(t)
        return in_scope, out


def _as_network(token: str) -> ipaddress._BaseNetwork | None:
    """Parse an IP or CIDR into a network; None if it isn't one."""
    try:
        if "/" in token:
            return ipaddress.ip_network(token, strict=False)
        return ipaddress.ip_network(ipaddress.ip_address(token))
    except ValueError:
        return None


def _net_subset(candidate, allowed) -> bool:
    """True if `candidate` is contained by `allowed` (same address family)."""
    if candidate.version != allowed.version:
        return False
    return (
        candidate.network_address >= allowed.network_address
        and candidate.broadcast_address <= allowed.broadcast_address
    )


def _extract_targets(command: str) -> list[str]:
    """Pull host/IP-looking tokens out of a command string, de-duplicated."""
    seen: list[str] = []
    for match in _IP_RE.findall(command) + _HOST_RE.findall(command):
        tok = match.lower().rstrip(".")
        if tok in _IGNORE_HOSTS:
            continue
        if tok not in seen:
            seen.append(tok)
    return seen
