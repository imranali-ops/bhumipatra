"""Integrity core for the land-record platform (stdlib only, no I/O).

Every ownership record is an entry in an append-only hash chain:

    hash(n) = SHA-256( canonical_json({v, seq, prev, payload}) )

Changing, deleting, reordering or inserting any entry breaks verification.
Removing entries from the END cannot be detected by the chain alone; callers
must keep the latest head hash somewhere separate (signed checkpoint, Day 3)
and pass it as `expected_head`.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

VERSION = "LANDREC-v1"
GENESIS_HASH = "0" * 64
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HEX64.match(value) is not None


def _check_json_safe(value: Any, path: str = "payload") -> None:
    """Allow only types with one unambiguous canonical form (no floats)."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _check_json_safe(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: dict keys must be str")
            _check_json_safe(item, f"{path}.{key}")
        return
    raise TypeError(f"{path}: unsupported type {type(value).__name__}")


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no spaces, Bengali kept as-is."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def compute_hash(seq: int, prev_hash: str, payload: Any) -> str:
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError("seq must be a non-negative integer")
    if not _is_hash(prev_hash):
        raise ValueError("prev_hash must be 64 lowercase hex characters")
    _check_json_safe(payload)
    body = {"v": VERSION, "seq": seq, "prev": prev_hash, "payload": payload}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def make_entry(seq: int, prev_hash: str, payload: dict) -> dict:
    payload = copy.deepcopy(payload)  # never alias caller-owned data
    return {
        "seq": seq,
        "prev_hash": prev_hash,
        "payload": payload,
        "hash": compute_hash(seq, prev_hash, payload),
    }


def append_entry(entries: Sequence[dict], payload: dict) -> dict:
    """Build the next entry for an existing (already verified) chain."""
    if entries:
        return make_entry(len(entries), entries[-1]["hash"], payload)
    return make_entry(0, GENESIS_HASH, payload)


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    broken_at: Optional[int] = None
    reason: str = ""


def verify_chain(entries: Sequence[dict],
                 expected_head: Optional[str] = None) -> VerifyResult:
    prev = GENESIS_HASH
    for i, entry in enumerate(entries):
        try:
            seq, stored_prev = entry["seq"], entry["prev_hash"]
            stored_hash, payload = entry["hash"], entry["payload"]
        except (KeyError, TypeError):
            return VerifyResult(False, i, "malformed entry")
        if not (_is_hash(stored_prev) and _is_hash(stored_hash)):
            return VerifyResult(False, i, "malformed hash value")
        if seq != i or isinstance(seq, bool):
            return VerifyResult(False, i, "sequence gap or reordering")
        if not hmac.compare_digest(stored_prev, prev):
            return VerifyResult(False, i, "broken link to previous entry")
        try:
            recomputed = compute_hash(seq, stored_prev, payload)
        except (TypeError, ValueError):
            return VerifyResult(False, i, "malformed payload")
        if not hmac.compare_digest(recomputed, stored_hash):
            return VerifyResult(False, i, "record was altered")
        prev = stored_hash
    if expected_head is not None:
        if not _is_hash(expected_head):
            raise ValueError("expected_head must be 64 lowercase hex characters")
        if not hmac.compare_digest(prev, expected_head):
            return VerifyResult(False, len(entries),
                                "head mismatch (entries removed or replaced)")
    return VerifyResult(True)


class TransferRejected(Exception):
    """A sale/transfer request that must not be applied."""


def check_transfer(entries: Sequence[dict], seller_id: str,
                   expected_head: str) -> str:
    """Gate every transfer. Returns the head hash the new entry will extend.

    `expected_head` is the head the seller/officer saw when they started.
    If anything was appended since (e.g. the same parcel sold twice),
    the head differs and the second request is rejected.
    """
    result = verify_chain(entries)
    if not result.ok:
        raise TransferRejected(f"chain invalid at {result.broken_at}: {result.reason}")
    if not entries:
        raise TransferRejected("parcel has no ownership record")
    if not _is_hash(expected_head):
        raise TransferRejected("malformed expected_head")
    head = entries[-1]["hash"]
    if not hmac.compare_digest(head, expected_head):
        raise TransferRejected("stale request: record changed since it was loaded "
                               "(possible double sale)")
    if entries[-1]["payload"].get("owner_id") != seller_id:
        raise TransferRejected("seller is not the current owner")
    return head
