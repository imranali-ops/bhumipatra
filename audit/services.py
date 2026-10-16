from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.integrity import VerifyResult, compute_hash, verify_chain

from .models import AuditEvent, AuditHead

ACTIONS = {
    "register", "login_success", "login_failed",
    "parcel_created", "ownership_transferred",
    "mutation_submitted", "mutation_survey_verify", "mutation_survey_reject",
    "mutation_approve", "mutation_reject", "mutation_cancel",
    "permission_denied", "document_uploaded",
}


@transaction.atomic
def log_event(*, actor, action: str, target_type: str = "", target_id="",
              ip: str | None = None, metadata: dict | None = None) -> AuditEvent:
    """Append one event to the global hash-chained audit log.
    Runs inside the caller's transaction, so a change and its log entry
    are saved together or not at all."""
    if action not in ACTIONS:
        raise ValueError(f"unknown audit action: {action}")
    AuditHead.objects.get_or_create(pk=1)
    head = AuditHead.objects.select_for_update().get(pk=1)
    seq = head.last_seq + 1
    now = timezone.now()
    payload = {
        "ts": now.isoformat(),
        "actor_id": actor.pk if actor is not None else None,
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id),
        "ip": ip or "",
        "meta": metadata or {},
    }
    new_hash = compute_hash(seq, head.last_hash, payload)
    event = AuditEvent.objects.create(seq=seq, prev_hash=head.last_hash,
                                      hash=new_hash, payload=payload, created_at=now)
    head.last_seq, head.last_hash = seq, new_hash
    head.save(update_fields=["last_seq", "last_hash"])
    return event


def verify_audit_log() -> VerifyResult:
    head = AuditHead.objects.filter(pk=1).first()
    rows = list(AuditEvent.objects.order_by("seq")
                .values("seq", "prev_hash", "payload", "hash"))
    if head is None:
        return VerifyResult(True) if not rows else VerifyResult(False, 0, "log without head")
    return verify_chain(rows, expected_head=head.last_hash)
