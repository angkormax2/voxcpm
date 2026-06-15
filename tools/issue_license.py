#!/usr/bin/env python3
"""Issue offline signed licenses (one machine + expiry)."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from license_manager import LICENSE_PREFIX, _b64url_encode, get_machine_id  # noqa: E402

PRIVATE_KEY_PATH = ROOT / "tools" / "license_private.pem"


def private_key_ready() -> bool:
    return PRIVATE_KEY_PATH.is_file()


def _load_private_key():
    from cryptography.hazmat.primitives import serialization

    if not PRIVATE_KEY_PATH.is_file():
        raise FileNotFoundError(
            f"Missing private key: {PRIVATE_KEY_PATH}\n"
            "Run: python tools/generate_license_keys.py"
        )
    return serialization.load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)


def sign_license_payload(payload: dict) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = _load_private_key()
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = private_key.sign(body, padding.PKCS1v15(), hashes.SHA256())
    payload_b64 = _b64url_encode(body)
    sig_b64 = _b64url_encode(signature)
    return f"{LICENSE_PREFIX}.{payload_b64}.{sig_b64}"


def create_offline_license(
    *,
    machine_id: str,
    days: int = 365,
    exp: date | None = None,
    label: str = "",
) -> dict:
    """Create a signed offline license for one machine."""
    machine_id = machine_id.strip()
    if len(machine_id) < 8:
        raise ValueError("Machine ID is too short.")

    if exp is None:
        exp = date.today() + timedelta(days=max(days, 1))

    payload = {
        "lid": str(uuid.uuid4()),
        "exp": exp.isoformat(),
        "mid": machine_id,
    }
    if label.strip():
        payload["label"] = label.strip()

    token = sign_license_payload(payload)
    return {
        "token": token,
        "machine_id": machine_id,
        "expires": exp.isoformat(),
        "label": label.strip(),
        "license_id": payload["lid"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a VoxCPM2 Studio license key")
    parser.add_argument(
        "--machine-id",
        help="Machine ID from the user's launcher (default: this computer)",
    )
    parser.add_argument("--days", type=int, default=365, help="Valid for N days from today")
    parser.add_argument("--exp", help="Expiry date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--label", default="", help="Optional note for your records")
    args = parser.parse_args()

    machine_id = args.machine_id or get_machine_id()
    exp = date.fromisoformat(args.exp) if args.exp else None
    result = create_offline_license(
        machine_id=machine_id,
        days=args.days,
        exp=exp,
        label=args.label,
    )
    print("License issued")
    print(f"  Machine ID : {result['machine_id']}")
    print(f"  Expires    : {result['expires']}")
    if result["label"]:
        print(f"  Label      : {result['label']}")
    print()
    print("Give this key to the user:")
    print(result["token"])


if __name__ == "__main__":
    main()
