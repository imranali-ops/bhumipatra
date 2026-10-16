from django.test import TestCase

from accounts.models import User
from core.integrity import compute_hash, verify_chain

from .models import AuditEvent
from .services import log_event, verify_audit_log

PW = "Zx9!kLm2#Qw8vB"


class AuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("auditor1", password=PW)

    def test_empty_log_is_valid(self):
        self.assertTrue(verify_audit_log().ok)

    def test_events_are_chained_and_verified(self):
        for i in range(3):
            log_event(actor=self.user, action="login_success", ip="127.0.0.1",
                      metadata={"n": i})
        events = list(AuditEvent.objects.order_by("seq"))
        self.assertEqual([e.seq for e in events], [0, 1, 2])
        self.assertEqual(events[1].prev_hash, events[0].hash)
        self.assertTrue(verify_audit_log().ok)

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            log_event(actor=self.user, action="made_up")

    def test_anonymous_actor_allowed(self):
        e = log_event(actor=None, action="login_failed", ip="10.0.0.1")
        self.assertIsNone(e.payload["actor_id"])

    def test_tampered_rows_detected(self):
        for _ in range(3):
            log_event(actor=self.user, action="login_success")
        rows = list(AuditEvent.objects.order_by("seq")
                    .values("seq", "prev_hash", "payload", "hash"))
        rows[1]["payload"]["action"] = "login_failed"
        self.assertFalse(verify_chain(rows).ok)
        rows = list(AuditEvent.objects.order_by("seq")
                    .values("seq", "prev_hash", "payload", "hash"))
        rows[1]["payload"]["ip"] = "9.9.9.9"
        rows[1]["hash"] = compute_hash(1, rows[1]["prev_hash"], rows[1]["payload"])
        self.assertFalse(verify_chain(rows).ok)
