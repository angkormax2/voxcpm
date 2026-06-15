"""License validation for VoxCPM2 Studio (offline + online, machine-bound + expiry)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from license_config import get_license_server_url

PROJECT_ROOT = Path(__file__).resolve().parent
LICENSE_FILE = PROJECT_ROOT / "data" / "license.json"
PUBLIC_KEY_PATH = PROJECT_ROOT / "assets" / "license_public.pem"
LICENSE_PREFIX = "VCPM2"
ONLINE_KEY_PREFIX = "VCPM-"
ENV_SKIP = "VOXCPM_LICENSE_SKIP"
ONLINE_GRACE_HOURS = 24


@dataclass
class LicenseStatus:
    ok: bool
    message: str
    expires: str | None = None
    machine_id: str | None = None
    license_id: str | None = None
    source: str | None = None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def get_machine_id() -> str:
    """Stable fingerprint for this computer."""
    parts: list[str] = [platform.node() or "unknown", str(uuid.getnode())]
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as key:
                parts.append(str(winreg.QueryValueEx(key, "MachineGuid")[0]))
        except Exception:
            pass
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


def _load_public_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes

    pem = PUBLIC_KEY_PATH.read_bytes()
    public_key = serialization.load_pem_public_key(pem)
    return public_key, padding.PKCS1v15(), hashes.SHA256()


def _parse_signed_license(token: str) -> tuple[dict[str, Any] | None, bytes | None, str]:
    token = token.strip()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != LICENSE_PREFIX:
        return None, None, "Invalid license format."
    try:
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        signature = _b64url_decode(parts[2])
    except Exception:
        return None, None, "License data is corrupted."
    if not isinstance(payload, dict):
        return None, None, "Invalid license payload."
    return payload, signature, ""


def _is_online_key(key: str) -> bool:
    key = key.strip().upper()
    return key.startswith(ONLINE_KEY_PREFIX) and not key.startswith(f"{LICENSE_PREFIX}.")


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    data = None
    req_headers = {"Content-Type": "application/json", "User-Agent": "VoxCPM2-Studio/1.0"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.reason or "Request failed"
        try:
            err_body = json.loads(exc.read().decode("utf-8"))
            detail = err_body.get("detail", detail)
        except Exception:
            pass
        raise RuntimeError(str(detail)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach license server: {exc.reason}") from exc


def _license_record() -> dict[str, Any]:
    if not LICENSE_FILE.is_file():
        return {}
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def verify_signed_license(token: str, *, machine_id: str | None = None) -> LicenseStatus:
    if os.environ.get(ENV_SKIP) == "1":
        return LicenseStatus(True, "License check skipped (dev mode).", expires="dev", source="dev")

    try:
        public_key, pad, hash_algo = _load_public_key()
    except Exception as exc:
        return LicenseStatus(False, f"License system not ready: {exc}")

    payload, signature, err = _parse_signed_license(token)
    if payload is None or signature is None:
        return LicenseStatus(False, err)

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    try:
        public_key.verify(signature, body, pad, hash_algo)
    except Exception:
        return LicenseStatus(False, "License signature is invalid.")

    mid = str(payload.get("mid", ""))
    current = machine_id or get_machine_id()
    if mid != current:
        return LicenseStatus(
            False,
            "This license is registered to another computer.",
            machine_id=current,
        )

    exp_raw = payload.get("exp")
    try:
        exp_date = date.fromisoformat(str(exp_raw))
    except Exception:
        return LicenseStatus(False, "License expiry date is invalid.")

    if exp_date < datetime.now(timezone.utc).date():
        return LicenseStatus(False, f"License expired on {exp_date.isoformat()}.")

    source = str(payload.get("src", "offline"))
    return LicenseStatus(
        True,
        f"Licensed until {exp_date.isoformat()} ({source}).",
        expires=exp_date.isoformat(),
        machine_id=current,
        license_id=str(payload.get("lid", "")),
        source=source,
    )


def save_license(token: str, *, last_online_check: str | None = None) -> None:
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {"token": token.strip()}
    if last_online_check:
        record["last_online_check"] = last_online_check
    LICENSE_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")


def load_saved_license() -> str | None:
    record = _license_record()
    token = record.get("token")
    return str(token).strip() if token else None


def clear_saved_license() -> None:
    if LICENSE_FILE.is_file():
        LICENSE_FILE.unlink()


def _activate_online_key(key: str) -> LicenseStatus:
    server = get_license_server_url()
    if not server:
        return LicenseStatus(
            False,
            "Online activation is not configured. Contact the author for an offline VCPM2 key.",
            machine_id=get_machine_id(),
        )

    machine_id = get_machine_id()
    try:
        result = _http_json(
            "POST",
            f"{server}/activate",
            {"key": key.strip(), "machine_id": machine_id},
        )
    except RuntimeError as exc:
        return LicenseStatus(False, str(exc), machine_id=machine_id)

    token = str(result.get("token", "")).strip()
    if not token:
        return LicenseStatus(False, "License server returned an invalid response.", machine_id=machine_id)

    status = verify_signed_license(token, machine_id=machine_id)
    if not status.ok:
        return status

    now = datetime.now(timezone.utc).isoformat()
    save_license(token, last_online_check=now)
    return LicenseStatus(
        True,
        f"Online license activated until {status.expires}.",
        expires=status.expires,
        machine_id=machine_id,
        license_id=status.license_id,
        source="online",
    )


def revalidate_online_license(*, force: bool = False) -> LicenseStatus:
    """Re-check online licenses with the server (revocation / expiry)."""
    token = load_saved_license()
    if not token:
        return LicenseStatus(False, "No license activated.", machine_id=get_machine_id())

    status = verify_signed_license(token)
    if not status.ok:
        return status

    if status.source != "online":
        return status

    server = get_license_server_url()
    if not server:
        return status

    record = _license_record()
    last_check_raw = record.get("last_online_check")
    if not force and last_check_raw:
        try:
            last_check = datetime.fromisoformat(str(last_check_raw))
            if last_check.tzinfo is None:
                last_check = last_check.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last_check < timedelta(hours=1):
                return status
        except Exception:
            pass

    license_id = status.license_id or ""
    machine_id = status.machine_id or get_machine_id()
    try:
        _http_json(
            "POST",
            f"{server}/validate",
            {"license_id": license_id, "machine_id": machine_id},
        )
    except RuntimeError as exc:
        if last_check_raw:
            try:
                last_check = datetime.fromisoformat(str(last_check_raw))
                if last_check.tzinfo is None:
                    last_check = last_check.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - last_check < timedelta(hours=ONLINE_GRACE_HOURS):
                    return LicenseStatus(
                        True,
                        f"{status.message} (offline grace — server unreachable)",
                        expires=status.expires,
                        machine_id=machine_id,
                        license_id=license_id,
                        source="online",
                    )
            except Exception:
                pass
        return LicenseStatus(False, str(exc), machine_id=machine_id, license_id=license_id, source="online")

    now = datetime.now(timezone.utc).isoformat()
    save_license(token, last_online_check=now)
    return status


def current_license_status() -> LicenseStatus:
    token = load_saved_license()
    if not token:
        return LicenseStatus(False, "No license activated.", machine_id=get_machine_id())
    status = verify_signed_license(token)
    if status.ok and status.source == "online":
        return revalidate_online_license()
    return status


def activate_license_key(key: str) -> LicenseStatus:
    """Activate offline VCPM2.... or online VCPM-XXXX-XXXX keys."""
    key = key.strip()
    if not key:
        return LicenseStatus(False, "Enter a license key.", machine_id=get_machine_id())

    if _is_online_key(key):
        return _activate_online_key(key)

    if not key.startswith(f"{LICENSE_PREFIX}."):
        return LicenseStatus(
            False,
            "Invalid key. Use VCPM-.... (online) or VCPM2.... (offline) from the author.",
            machine_id=get_machine_id(),
        )

    status = verify_signed_license(key)
    if status.ok:
        save_license(key)
    return status


def require_valid_license(*, revalidate_online: bool = True) -> LicenseStatus:
    status = current_license_status()
    if not status.ok:
        raise RuntimeError(status.message)
    if revalidate_online and status.source == "online":
        status = revalidate_online_license(force=True)
        if not status.ok:
            clear_saved_license()
            raise RuntimeError(status.message)
    return status
