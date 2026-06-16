"""Log helpers for the Studio launcher (colors + progress markers)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class LogEvent:
    text: str
    level: str = "info"
    progress: float | None = None
    progress_text: str = ""
    progress_detail: str = ""


_PROGRESS_RE = re.compile(r"^PROGRESS\|(\d+(?:\.\d+)?)\|(.*)$")
_PHASE_RE = re.compile(r"^PHASE\|(\d+(?:\.\d+)?)\|(.*)$")


def parse_log_message(msg: str) -> LogEvent:
    msg = msg.rstrip("\n")
    phase = _PHASE_RE.match(msg)
    if phase:
        return LogEvent(
            "",
            level="info",
            progress=float(phase.group(1)),
            progress_text=phase.group(2).strip(),
        )
    prog = _PROGRESS_RE.match(msg)
    if prog:
        detail = prog.group(2).strip()
        return LogEvent(
            "",
            level="info",
            progress=float(prog.group(1)),
            progress_detail=detail,
            progress_text=detail,
        )

    lower = msg.lower()
    if msg.startswith("=== ") and msg.endswith(" ==="):
        return LogEvent(msg.strip("= ").strip(), level="title")
    if msg.startswith("$ "):
        return LogEvent(msg, level="cmd")
    if any(x in lower for x in ("failed", "error", "cannot ", "setup error")):
        return LogEvent(msg, level="err")
    if any(x in lower for x in ("complete", "finished", "ready", "already present", "up to date", "activated")):
        return LogEvent(msg, level="ok")
    if any(
        x in lower
        for x in ("warning", "may take", "installing", "downloading", "waiting", "checking", "fetching")
    ):
        return LogEvent(msg, level="warn")
    if msg.startswith("["):
        return LogEvent(msg, level="dim")
    return LogEvent(msg, level="info")
