from django.db import models

from core.integrity import GENESIS_HASH

from .base import AppendOnlyModel

HEX64 = r"^[0-9a-f]{64}$"


class AuditHead(models.Model):
    """Single row holding the newest audit hash; locked while appending so
    the global chain never forks."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_seq = models.BigIntegerField(default=-1)
    last_hash = models.CharField(max_length=64, default=GENESIS_HASH)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1),
                                              name="audit_head_singleton")]


class AuditEvent(AppendOnlyModel):
    seq = models.BigIntegerField(unique=True)
    prev_hash = models.CharField(max_length=64, editable=False)
    hash = models.CharField(max_length=64, unique=True, editable=False)
    payload = models.JSONField(editable=False)
    created_at = models.DateTimeField(editable=False)

    class Meta:
        ordering = ["seq"]
        constraints = [
            models.CheckConstraint(condition=models.Q(hash__regex=HEX64),
                                   name="audit_hash_is_hex64"),
            models.CheckConstraint(condition=models.Q(prev_hash__regex=HEX64),
                                   name="audit_prev_hash_is_hex64"),
        ]

    def __str__(self):
        return f"#{self.seq} {self.payload.get('action')}"
