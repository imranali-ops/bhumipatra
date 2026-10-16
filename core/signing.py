"""Ed25519 signed checkpoints.

After every ownership change the server signs (parcel, seq, head hash).
Someone who rewrites history cannot forge a matching signature without the
private key, which is kept outside the database (environment/KMS)."""
from __future__ import annotations

import base64
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .integrity import _is_hash, canonical_bytes

CHECKPOINT_VERSION = "LANDCHK-v1"


def load_private_key(b64: str) -> Ed25519PrivateKey:
    raw = base64.b64decode(b64, validate=True)
    if len(raw) != 32:
        raise ValueError("signing key must be exactly 32 bytes (base64 encoded)")
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_key_of(private_key: Ed25519PrivateKey) -> Ed25519PublicKey:
    return private_key.public_key()


def _message(parcel_id: Any, seq: int, head_hash: str) -> bytes:
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError("seq must be a non-negative integer")
    if not _is_hash(head_hash):
        raise ValueError("head_hash must be 64 lowercase hex characters")
    return canonical_bytes({"v": CHECKPOINT_VERSION, "parcel": str(parcel_id),
                            "seq": seq, "head": head_hash})


def sign_checkpoint(private_key: Ed25519PrivateKey, parcel_id: Any,
                    seq: int, head_hash: str) -> str:
    return private_key.sign(_message(parcel_id, seq, head_hash)).hex()


def verify_checkpoint(public_key: Ed25519PublicKey, parcel_id: Any, seq: int,
                      head_hash: str, signature_hex: str) -> bool:
    try:
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, _message(parcel_id, seq, head_hash))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
