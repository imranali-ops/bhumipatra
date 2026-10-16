"""All writes to ownership history go through this module.

Rules enforced here (not in the views, so no code path can skip them):
  * only an active 'ac_land' officer may create or change records
  * every change is hash-chained, signed (checkpoint) and audit-logged,
    all inside ONE database transaction
"""
from __future__ import annotations

import datetime
import uuid
from functools import lru_cache
from typing import Optional

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction

from accounts.models import Role
from audit.services import log_event
from core.integrity import (
    TransferRejected, VerifyResult, append_entry, check_transfer, verify_chain,
)
from core.signing import (
    load_private_key, public_key_of, sign_checkpoint, verify_checkpoint,
)

from .models import Checkpoint, Owner, OwnershipEntry, Parcel

TRANSFER_KINDS = {"sale", "inheritance", "gift", "court_order"}
MAX_REF_LENGTH = 100


@lru_cache(maxsize=1)
def _private_key():
    return load_private_key(settings.SIGNING_PRIVATE_KEY)


def _require_land_officer(actor) -> None:
    if (actor is None or not getattr(actor, "is_active", False)
            or actor.role != Role.AC_LAND):
        raise PermissionDenied("only an active Assistant Commissioner (Land) may change records")


def _payload(owner_id, kind: str, ref: str, effective_date: datetime.date) -> dict:
    if not isinstance(effective_date, datetime.date):
        raise ValueError("effective_date must be a date")
    if len(ref) > MAX_REF_LENGTH:
        raise ValueError("ref is too long")
    return {
        "owner_id": str(owner_id),
        "kind": kind,
        "ref": ref,
        "effective_date": effective_date.isoformat(),
    }


def _chain(parcel: Parcel) -> list[dict]:
    return list(parcel.entries.order_by("seq").values("seq", "prev_hash", "payload", "hash"))


def _write_checkpoint(parcel: Parcel, seq: int, head_hash: str) -> Checkpoint:
    signature = sign_checkpoint(_private_key(), parcel.id, seq, head_hash)
    return Checkpoint.objects.create(parcel=parcel, seq=seq, head_hash=head_hash,
                                     signature=signature, key_id=settings.SIGNING_KEY_ID)


@transaction.atomic
def create_parcel_with_owner(*, actor, owner: Owner, effective_date: datetime.date,
                             ref: str = "", ip: str | None = None,
                             **parcel_fields) -> Parcel:
    _require_land_officer(actor)
    parcel = Parcel(**parcel_fields)
    parcel.full_clean()
    parcel.save()
    entry = append_entry([], _payload(owner.id, "initial", ref, effective_date))
    OwnershipEntry.objects.create(parcel=parcel, **entry)
    _write_checkpoint(parcel, entry["seq"], entry["hash"])
    log_event(actor=actor, action="parcel_created", target_type="parcel",
              target_id=parcel.id, ip=ip, metadata={"owner_id": str(owner.id)})
    return parcel


def current_head(parcel: Parcel) -> str:
    chain = _chain(parcel)
    if not chain:
        raise ValueError("parcel has no ownership record")
    return chain[-1]["hash"]


def current_owner(parcel: Parcel) -> Owner:
    chain = _chain(parcel)
    if not chain:
        raise ValueError("parcel has no ownership record")
    return Owner.objects.get(pk=uuid.UUID(chain[-1]["payload"]["owner_id"]))


def verify_parcel(parcel: Parcel) -> VerifyResult:
    """Chain intact + every signed checkpoint matches + nothing newer than the
    latest checkpoint was added or removed."""
    chain = _chain(parcel)
    checkpoints = list(parcel.checkpoints.order_by("seq"))
    if not chain:
        return VerifyResult(not checkpoints, None, "" if not checkpoints else "checkpoint without entries")
    if not checkpoints:
        return VerifyResult(False, None, "no signed checkpoint")
    public = public_key_of(_private_key())
    for cp in checkpoints:
        if cp.key_id != settings.SIGNING_KEY_ID:
            return VerifyResult(False, cp.seq, "checkpoint signed with unknown key")
        if not verify_checkpoint(public, parcel.id, cp.seq, cp.head_hash, cp.signature):
            return VerifyResult(False, cp.seq, "checkpoint signature invalid")
        if cp.seq >= len(chain) or chain[cp.seq]["hash"] != cp.head_hash:
            return VerifyResult(False, cp.seq, "checkpoint does not match history")
    latest = checkpoints[-1]
    result = verify_chain(chain, expected_head=latest.head_hash)
    if result.ok and len(chain) - 1 != latest.seq:
        return VerifyResult(False, latest.seq, "entries exist beyond the latest checkpoint")
    return result


@transaction.atomic
def transfer_ownership(*, actor, parcel_id, seller_id, buyer_id, expected_head: str,
                       kind: str, ref: str, effective_date: datetime.date,
                       ip: str | None = None) -> OwnershipEntry:
    """Apply one ownership change.

    The parcel row is locked for the duration, so two simultaneous sales of
    the same parcel run one after another; the second fails because its
    `expected_head` is no longer the head.
    """
    _require_land_officer(actor)
    if kind not in TRANSFER_KINDS:
        raise ValueError(f"kind must be one of {sorted(TRANSFER_KINDS)}")
    if str(seller_id) == str(buyer_id):
        raise TransferRejected("seller and buyer are the same person")
    if not Owner.objects.filter(pk=buyer_id).exists():
        raise TransferRejected("buyer is not a registered owner")

    parcel = Parcel.objects.select_for_update().get(pk=parcel_id)
    chain = _chain(parcel)
    check_transfer(chain, str(seller_id), expected_head)
    entry_data = append_entry(chain, _payload(buyer_id, kind, ref, effective_date))
    entry = OwnershipEntry.objects.create(parcel=parcel, **entry_data)
    _write_checkpoint(parcel, entry.seq, entry.hash)
    log_event(actor=actor, action="ownership_transferred", target_type="parcel",
              target_id=parcel.id, ip=ip,
              metadata={"seq": entry.seq, "kind": kind,
                        "seller_id": str(seller_id), "buyer_id": str(buyer_id)})
    return entry
