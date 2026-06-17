"""Check and apply Studio client updates from GitHub."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from studio_branding import (
    DEFAULT_STUDIO_REPO_URL,
    PROJECT_ROOT,
    get_studio_release_version,
    get_studio_repo_url,
)

LogFn = Callable[[str], None]


@dataclass
class UpdateStatus:
    current: str
    latest: str
    update_available: bool
    can_git_update: bool
    repo_url: str
    zip_url: str
    error: str = ""


def _parse_version(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in re.split(r"[.\-]", text.strip()):
        if not piece:
            continue
        if piece.isdigit():
            parts.append(int(piece))
        else:
            break
    return tuple(parts) if parts else (0,)


def version_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def _repo_slug() -> str:
    url = (get_studio_repo_url() or DEFAULT_STUDIO_REPO_URL).rstrip("/")
    if "github.com/" in url:
        slug = url.split("github.com/", 1)[1].strip("/")
        return slug.split("/")[0] + "/" + slug.split("/")[1] if "/" in slug else slug
    return "angkormax2/voxcpm"


def _version_url() -> str:
    return f"https://raw.githubusercontent.com/{_repo_slug()}/main/assets/studio_version.txt"


def _zip_url() -> str:
    return f"https://github.com/{_repo_slug()}/archive/refs/heads/main.zip"


def _repo_page() -> str:
    return get_studio_repo_url() or DEFAULT_STUDIO_REPO_URL


def get_local_version() -> str:
    """Always read from disk so git pull / ZIP replace is detected."""
    return get_studio_release_version()


def _git_available() -> bool:
    if not shutil.which("git"):
        return False
    git_dir = PROJECT_ROOT / ".git"
    if not git_dir.exists():
        return False
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except Exception:
        return False


def fetch_latest_version(*, timeout: int = 20) -> str:
    url = f"{_version_url()}?t={int(time.time())}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "VoxCPM2-Studio-Updater/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line.split()[0]
    raise ValueError("Remote version file is empty.")


def check_for_updates() -> UpdateStatus:
    current = get_local_version()
    repo = _repo_page()
    zip_url = _zip_url()
    try:
        latest = fetch_latest_version()
        error = ""
    except Exception as exc:
        latest = current
        error = str(exc)
    return UpdateStatus(
        current=current,
        latest=latest,
        update_available=version_newer(latest, current),
        can_git_update=_git_available(),
        repo_url=repo,
        zip_url=zip_url,
        error=error,
    )


def _git_run(args: list[str], log: LogFn | None = None) -> subprocess.CompletedProcess[str]:
    if log:
        log(f"$ git {' '.join(args)}")
    return subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def apply_git_update(log: LogFn | None = None) -> tuple[bool, str]:
    if not _git_available():
        return False, "This folder was not installed with git clone."

    def _log(msg: str) -> None:
        if log:
            log(msg)

    before = get_local_version()
    try:
        remote_latest = fetch_latest_version()
    except Exception as exc:
        remote_latest = before

    _log("Stopping servers before update…")
    try:
        from launcher_core import StudioManager

        StudioManager(log=log or (lambda _m: None)).stop()
    except Exception:
        pass

    _log("Fetching latest files from GitHub…")
    fetch = _git_run(["fetch", "origin", "main"], log)
    if fetch.stdout.strip():
        _log(fetch.stdout.strip())
    if fetch.stderr.strip():
        _log(fetch.stderr.strip())

    _log("Applying update (git pull)…")
    pull = _git_run(["pull", "--ff-only", "origin", "main"], log)
    if pull.stdout.strip():
        _log(pull.stdout.strip())
    if pull.stderr.strip():
        _log(pull.stderr.strip())
    if pull.returncode != 0:
        return False, pull.stderr.strip() or pull.stdout.strip() or "git pull failed."

    after = get_local_version()
    if version_newer(remote_latest, after):
        return (
            False,
            "Git pull finished but this folder is still on an older version.\n\n"
            "Use “No” on the update dialog to download the ZIP, or run:\n"
            "  git fetch origin main\n"
            "  git reset --hard origin/main\n"
            "(Your license in data\\license.json is kept — it is not in git.)",
        )

    if before == after and version_newer(remote_latest, after):
        return (
            False,
            "Already up to date according to git, but version file is still old.\n\n"
            "Please download the ZIP from GitHub and replace the app folder.",
        )

    _log(f"Update complete. Now at version {after}.")
    return True, f"Update complete. Version {after}."
