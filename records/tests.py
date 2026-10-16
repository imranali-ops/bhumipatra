from datetime import date
from decimal import Decimal
from unittest import skipUnless

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from accounts.models import Role, User
from audit.models import AuditEvent
from audit.services import verify_audit_log
from core.integrity import TransferRejected
from core.signing import sign_checkpoint

from .models import Checkpoint, ImmutableRecordError, LandType, Owner, OwnershipEntry
from .services import (
    _private_key, create_parcel_with_owner, current_head, current_owner,
    transfer_ownership, verify_parcel,
)

PARCEL = dict(district="নমুনা জেলা", upazila="নমুনা উপজেলা", mouza="নমুনা মৌজা",
              khatian_no="1245", dag_no="883", area_decimal=Decimal("33.00"),
              land_type=LandType.AGRICULTURAL)
PW = "Zx9!kLm2#Qw8vB"


class OwnerTests(TestCase):
    def test_nid_not_stored_in_plaintext(self):
        o = Owner.register("কাল্পনিক ক", "1234567890")
        self.assertEqual(o.nid_last4, "7890")
        self.assertNotIn("1234567890", o.nid_hmac)
        self.assertEqual(len(o.nid_hmac), 64)

    def test_bengali_digits_normalised(self):
        self.assertEqual(Owner.hash_nid("১২৩৪৫৬৭৮৯০"), Owner.hash_nid("1234567890"))

    def test_invalid_nid_rejected(self):
        for bad in ("123", "12345678901", "12345abcde", ""):
            with self.assertRaises(ValidationError):
                Owner.register("কাল্পনিক", bad)

    def test_duplicate_nid_rejected(self):
        Owner.register("কাল্পনিক ক", "1234567890")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Owner.register("কাল্পনিক খ", "1234567890")


class OwnershipTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user("officer1", password=PW, role=Role.AC_LAND)
        self.a = Owner.register("কাল্পনিক ক", "1234567890")
        self.b = Owner.register("কাল্পনিক খ", "1234567891")
        self.c = Owner.register("কাল্পনিক গ", "1234567892")
        self.parcel = create_parcel_with_owner(
            actor=self.officer, owner=self.a, effective_date=date(2020, 1, 1), **PARCEL)

    def sell(self, seller, buyer, head, actor=None):
        return transfer_ownership(
            actor=actor or self.officer, parcel_id=self.parcel.id,
            seller_id=seller.id, buyer_id=buyer.id, expected_head=head,
            kind="sale", ref="দলিল-নমুনা-১", effective_date=date(2024, 5, 1))

    def test_initial_state(self):
        self.assertEqual(current_owner(self.parcel), self.a)
        self.assertTrue(verify_parcel(self.parcel).ok)
        self.assertEqual(self.parcel.checkpoints.count(), 1)

    def test_transfer_moves_ownership_and_checkpoints(self):
        self.sell(self.a, self.b, current_head(self.parcel))
        self.assertEqual(current_owner(self.parcel), self.b)
        self.assertEqual(self.parcel.entries.count(), 2)
        self.assertEqual(self.parcel.checkpoints.count(), 2)
        self.assertTrue(verify_parcel(self.parcel).ok)

    def test_double_sale_blocked(self):
        head = current_head(self.parcel)
        self.sell(self.a, self.b, head)
        with self.assertRaises(TransferRejected):
            self.sell(self.a, self.c, head)
        self.assertEqual(current_owner(self.parcel), self.b)
        self.assertEqual(self.parcel.entries.count(), 2)

    def test_wrong_seller_blocked(self):
        with self.assertRaises(TransferRejected):
            self.sell(self.b, self.c, current_head(self.parcel))

    def test_unknown_buyer_and_self_sale_blocked(self):
        head = current_head(self.parcel)
        with self.assertRaises(TransferRejected):
            transfer_ownership(actor=self.officer, parcel_id=self.parcel.id,
                               seller_id=self.a.id,
                               buyer_id="00000000-0000-0000-0000-000000000000",
                               expected_head=head, kind="sale", ref="",
                               effective_date=date(2024, 5, 1))
        with self.assertRaises(TransferRejected):
            self.sell(self.a, self.a, head)

    def test_invalid_kind_rejected(self):
        with self.assertRaises(ValueError):
            transfer_ownership(actor=self.officer, parcel_id=self.parcel.id,
                               seller_id=self.a.id, buyer_id=self.b.id,
                               expected_head=current_head(self.parcel), kind="initial",
                               ref="", effective_date=date(2024, 5, 1))

    def test_only_land_officer_may_change_records(self):
        head = current_head(self.parcel)
        for role in (Role.CITIZEN, Role.SURVEYOR, Role.LAWYER, Role.ADMIN):
            user = User.objects.create_user(f"u_{role}", password=PW, role=role)
            with self.assertRaises(PermissionDenied):
                self.sell(self.a, self.b, head, actor=user)
        with self.assertRaises(PermissionDenied):
            transfer_ownership(actor=None, parcel_id=self.parcel.id, seller_id=self.a.id,
                               buyer_id=self.b.id, expected_head=head, kind="sale",
                               ref="", effective_date=date(2024, 5, 1))
        self.officer.is_active = False
        self.officer.save()
        with self.assertRaises(PermissionDenied):
            self.sell(self.a, self.b, head)
        self.assertEqual(self.parcel.entries.count(), 1)

    def test_entries_are_immutable_in_python(self):
        entry = self.parcel.entries.first()
        entry.hash = "f" * 64
        with self.assertRaises(ImmutableRecordError):
            entry.save()
        with self.assertRaises(ImmutableRecordError):
            entry.delete()
        with self.assertRaises(ImmutableRecordError):
            OwnershipEntry.objects.all().update(seq=9)
        with self.assertRaises(ImmutableRecordError):
            OwnershipEntry.objects.all().delete()
        with self.assertRaises(ImmutableRecordError):
            Checkpoint.objects.all().delete()

    @skipUnless(connection.vendor == "postgresql", "database triggers are PostgreSQL only")
    def test_database_blocks_raw_sql_changes(self):
        statements = [
            "UPDATE records_ownershipentry SET seq = seq + 100",
            "DELETE FROM records_ownershipentry",
            "UPDATE records_checkpoint SET seq = seq + 100",
            "DELETE FROM records_checkpoint",
            "UPDATE audit_auditevent SET seq = seq + 100",
            "DELETE FROM audit_auditevent",
            "TRUNCATE records_ownershipentry CASCADE",
        ]
        for sql in statements:
            with self.subTest(sql=sql):
                with connection.cursor() as cursor:
                    with self.assertRaises(IntegrityError):
                        with transaction.atomic():
                            cursor.execute(sql)

    def test_forged_checkpoint_signature_detected(self):
        Checkpoint.objects.create(
            parcel=self.parcel, seq=1, head_hash="a" * 64, signature="00" * 64,
            key_id="k1")
        self.assertFalse(verify_parcel(self.parcel).ok)

    def test_truncation_detected_by_signed_checkpoint(self):
        # A genuine signed checkpoint for a later state that the chain no longer has.
        head = "b" * 64
        sig = sign_checkpoint(_private_key(), self.parcel.id, 1, head)
        from django.conf import settings
        Checkpoint.objects.create(parcel=self.parcel, seq=1, head_hash=head,
                                  signature=sig, key_id=settings.SIGNING_KEY_ID)
        result = verify_parcel(self.parcel)
        self.assertFalse(result.ok)

    def test_duplicate_parcel_and_zero_area_rejected(self):
        with self.assertRaises(ValidationError):
            create_parcel_with_owner(actor=self.officer, owner=self.a,
                                     effective_date=date(2021, 1, 1), **PARCEL)
        bad = dict(PARCEL, khatian_no="9999", area_decimal=Decimal("0"))
        with self.assertRaises(ValidationError):
            create_parcel_with_owner(actor=self.officer, owner=self.a,
                                     effective_date=date(2021, 1, 1), **bad)

    def test_changes_are_audit_logged_and_chain_verifies(self):
        self.sell(self.a, self.b, current_head(self.parcel))
        actions = list(AuditEvent.objects.order_by("seq")
                       .values_list("payload__action", flat=True))
        self.assertEqual(actions, ["parcel_created", "ownership_transferred"])
        self.assertTrue(verify_audit_log().ok)

    def test_failed_transfer_leaves_no_trace(self):
        before = AuditEvent.objects.count()
        with self.assertRaises(TransferRejected):
            self.sell(self.b, self.c, current_head(self.parcel))
        self.assertEqual(AuditEvent.objects.count(), before)
        self.assertEqual(self.parcel.checkpoints.count(), 1)
