"""License server URL for online activation (set before distributing the app)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_SERVER = "VOXCPM_LICENSE_SERVER"
URL_FILE = PROJECT_ROOT / "assets" / "license_server.url"


def get_license_server_url() -> str:
    url = os.environ.get(ENV_SERVER, "").strip().rstrip("/")
    if url:
        return url
    if URL_FILE.is_file():
        line = URL_FILE.read_text(encoding="utf-8").strip()
        if line and not line.startswith("#"):
            return line.rstrip("/")
    return ""
