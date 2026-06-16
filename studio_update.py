"""Check and apply Studio client updates from GitHub."""

from __future__ import annotations

import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from studio_branding import (
    DEFAULT_STUDIO_REPO_URL,
    PROJECT_ROOT,
    STUDIO_RELEASE_VERSION,
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
    return STUDIO_RELEASE_VERSION


def _git_available() -> bool:
    return bool(shutil.which("git")) and (PROJECT_ROOT / ".git").is_dir()


def fetch_latest_version(*, timeout: int = 20) -> str:
    req = urllib.request.Request(
        _version_url(),
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


def apply_git_update(log: LogFn | None = None) -> tuple[bool, str]:
    if not _git_available():
        return False, "This folder was not installed with git clone."

    def _log(msg: str) -> None:
        if log:
            log(msg)

    _log("Stopping servers before update…")
    try:
        from launcher_core import StudioManager

        StudioManager(log=log or (lambda _m: None)).stop()
    except Exception:
        pass

    _log("Downloading update (git pull)…")
    proc = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout.strip():
        _log(proc.stdout.strip())
    if proc.stderr.strip():
        _log(proc.stderr.strip())
    if proc.returncode != 0:
        return False, proc.stderr.strip() or "git pull failed."

    from studio_branding import get_studio_release_version

    new_ver = get_studio_release_version()
    _log(f"Update complete. Now at version {new_ver}.")
    return True, f"Update complete. Version {new_ver}."
