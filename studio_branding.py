"""Shared display name for the Studio app."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
STUDIO_NAME = "VoxCPM2 Studio By BONG Pisith"
LICENSE_CONTACT_URL = "https://t.me/rornpisith"
LICENSE_CONTACT_LABEL = "Telegram @rornpisith"
LICENSE_CONTACT_HINT = "Send your Machine ID to get a license key"
DEFAULT_STUDIO_REPO_URL = "https://github.com/angkormax2/voxcpm"
STUDIO_VERSION_FILE = PROJECT_ROOT / "assets" / "studio_version.txt"
STUDIO_REPO_URL_FILE = PROJECT_ROOT / "assets" / "studio_repo.url"
ENV_STUDIO_REPO = "VOXCPM_STUDIO_REPO_URL"


def get_studio_release_version() -> str:
    if STUDIO_VERSION_FILE.is_file():
        for line in STUDIO_VERSION_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line.split()[0]
    return "0.0.0"


STUDIO_RELEASE_VERSION = get_studio_release_version()


def get_studio_repo_url() -> str:
    url = os.environ.get(ENV_STUDIO_REPO, "").strip().rstrip("/")
    if url:
        return url
    if STUDIO_REPO_URL_FILE.is_file():
        line = STUDIO_REPO_URL_FILE.read_text(encoding="utf-8").strip()
        if line and not line.startswith("#"):
            return line.rstrip("/")
    return ""
