#!/usr/bin/env python3
"""Generate RSA key pair for license signing (run once, keep private key secret)."""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "assets" / "license_public.pem"
PRIVATE = ROOT / "tools" / "license_private.pem"


def main() -> None:
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    if PRIVATE.is_file():
        print(f"Private key already exists: {PRIVATE}")
        print("Delete it first if you want to regenerate.")
        return

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    PUBLIC.write_bytes(
        public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    PRIVATE.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    print(f"Public key : {PUBLIC}")
    print(f"Private key: {PRIVATE}")
    print("Commit license_public.pem only. Never commit license_private.pem.")


if __name__ == "__main__":
    main()
