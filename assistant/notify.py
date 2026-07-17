"""Wakelock + notifications for long-running turns (Termux/Android).

While the assistant is working on a turn it holds a CPU wakelock so generation
keeps running with the screen off, then releases it when idle so the phone can
sleep normally. When a long turn finishes it posts an Android notification so
you can walk away and get pinged when the reply is ready.

Everything degrades gracefully: if the Termux commands aren't present (not on a
phone, or Termux:API not installed) the calls become no-ops.
"""

from __future__ import annotations

import shutil
import subprocess


class Notifier:
    NOTIFY_ID = "local-phone"

    def __init__(self, config: dict, console):
        cfg = config.get("notify", {}) or {}
        self.enabled = cfg.get("enabled", True)
        self.use_wake_lock = cfg.get("wake_lock", True)
        self.min_seconds = int(cfg.get("min_seconds", 20))
        self.console = console
        # termux-wake-lock ships with Termux core; termux-notification needs the
        # termux-api package + the Termux:API app.
        self._have_wake = shutil.which("termux-wake-lock") is not None
        self._have_notify = shutil.which("termux-notification") is not None
        self._locked = False

    # -- wakelock ------------------------------------------------------------
    def wake_lock(self) -> None:
        if not (self.enabled and self.use_wake_lock and self._have_wake):
            return
        if self._locked:
            return
        if self._run(["termux-wake-lock"]):
            self._locked = True

    def wake_unlock(self) -> None:
        if self._locked:
            self._run(["termux-wake-unlock"])
            self._locked = False

    # -- notification --------------------------------------------------------
    def notify(self, title: str, content: str) -> None:
        if not (self.enabled and self._have_notify):
            return
        self._run([
            "termux-notification",
            "--id", self.NOTIFY_ID,
            "--title", title,
            "--content", content,
        ])

    # -- internals -----------------------------------------------------------
    @staticmethod
    def _run(cmd: list[str]) -> bool:
        try:
            subprocess.run(
                cmd, check=False, timeout=15,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            return False
