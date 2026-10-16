from datetime import date
from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from accounts.models import Role, User
from audit.models import AuditEvent
from audit.services import verify_audit_log
from core.integrity import TransferRejected
from core.signing import sign_checkpoint
from records.models import Checkpoint, LandType, Owner
from records.services import (
    _private_key, create_parcel_with_owner, current_owner, verify_parcel,
)

from .models import MutationApplication, MutationStep, Notification
from .services import ConflictError, advance_application, submit_application
from audit.base import ImmutableRecordError

PW = "Zx9!kLm2#Qw8vB"
PARCEL = dict(district="নমুনা জেলা", upazila="নমুনা উপজেলা", mouza="নমুনা মৌজা",
              khatian_no="1245", dag_no="883", area_decimal=Decimal("33.00"),
              land_type=LandType.AGRICULTURAL)


class Base:
    def make_world(self):
        mk = User.objects.create_user
        self.officer = mk("officer1", password=PW, role=Role.AC_LAND, email="ac@example.com")
        self.surveyor = mk("surveyor1", password=PW, role=Role.SURVEYOR)
        self.citizen = mk("citizen1", password=PW, role=Role.CITIZEN, email="c1@example.com")
        self.citizen2 = mk("citizen2", password=PW, role=Role.CITIZEN)
        self.lawyer = mk("lawyer1", password=PW, role=Role.LAWYER)
        self.seller = Owner.register("কাল্পনিক বিক্রেতা", "1234567890")
        self.parcel = create_parcel_with_owner(
            actor=self.officer, owner=self.seller, effective_date=date(2020, 1, 1), **PARCEL)

    def apply(self, applicant=None, nid="1234567891", name="কাল্পনিক ক্রেতা"):
        return submit_application(
            applicant=applicant or self.citizen, parcel_id=self.parcel.id, kind="sale",
            deed_ref="দলিল-নমুনা-১", claimant_name=name, claimant_nid=nid)

    def act(self, app, actor, action, note=""):
        return advance_application(actor=actor, application_id=app.id, action=action, note=note)


class WorkflowServiceTests(Base, TestCase):
    def setUp(self):
        self.make_world()

    def test_full_happy_path_updates_ownership(self):
        app = self.apply()
        self.assertEqual(app.status, "submitted")
        self.act(app, self.surveyor, "survey_verify", "সরেজমিন যাচাই সম্পন্ন")
        self.act(app, self.officer, "approve")
        app.refresh_from_db()
        self.assertEqual(app.status, "approved")
        self.assertEqual(current_owner(self.parcel).full_name, "কাল্পনিক ক্রেতা")
        self.assertTrue(verify_parcel(self.parcel).ok)
        self.assertEqual([s.action for s in app.steps.all()], ["submit", "survey_verify", "approve"])
        self.assertTrue(verify_audit_log().ok)

    def test_each_step_notifies_the_applicant(self):
        app = self.apply()
        self.act(app, self.surveyor, "survey_verify", "যাচাই সম্পন্ন")
        self.act(app, self.officer, "approve")
        self.assertEqual(Notification.objects.filter(user=self.citizen).count(), 3)
        self.assertTrue(Notification.objects.filter(user=self.officer).exists())  # ready for approval

    def test_email_sent_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.apply()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["c1@example.com"])
        self.assertNotIn("কাল্পনিক", mail.outbox[0].body)  # no personal data in messages

    def test_only_citizens_can_apply(self):
        for user in (self.surveyor, self.officer, self.lawyer):
            with self.assertRaises(PermissionDenied):
                self.apply(applicant=user)

    def test_cannot_skip_steps_or_use_wrong_role(self):
        app = self.apply()
        with self.assertRaises(ConflictError):
            self.act(app, self.officer, "approve")          # not surveyed yet
        with self.assertRaises(PermissionDenied):
            self.act(app, self.officer, "survey_verify", "x")  # wrong role
        with self.assertRaises(PermissionDenied):
            self.act(app, self.citizen2, "cancel")           # not the applicant
        self.act(app, self.surveyor, "survey_verify", "ok")
        with self.assertRaises(PermissionDenied):
            self.act(app, self.surveyor, "approve")          # surveyor cannot approve
        with self.assertRaises(ConflictError):
            self.act(app, self.citizen, "cancel")            # too late to cancel

    def test_applicant_cannot_process_own_application(self):
        # an officer who is also the applicant is blocked (separation of duties)
        officer_app = MutationApplication.objects.create(
            applicant=self.surveyor, parcel=self.parcel, kind="sale", deed_ref="x",
            seller=self.seller, claimant=Owner.register("কাল্পনিক গ", "1234567899"),
            base_head="a" * 64)
        with self.assertRaises(PermissionDenied):
            self.act(officer_app, self.surveyor, "survey_verify", "নিজেরটা")

    def test_note_required_for_verify_and_reject(self):
        app = self.apply()
        for action, actor in (("survey_verify", self.surveyor), ("survey_reject", self.surveyor)):
            with self.assertRaises(ValidationError):
                self.act(app, actor, action, "  ")
        self.act(app, self.surveyor, "survey_reject", "কাগজ অসম্পূর্ণ")
        app.refresh_from_db()
        self.assertEqual(app.status, "rejected")
        self.assertEqual(current_owner(self.parcel), self.seller)

    def test_applicant_can_cancel_while_submitted(self):
        app = self.apply()
        self.act(app, self.citizen, "cancel")
        app.refresh_from_db()
        self.assertEqual(app.status, "cancelled")

    def test_claimant_cannot_be_current_owner(self):
        with self.assertRaises(ValidationError):
            self.apply(nid="1234567890")

    def test_bad_input_rejected(self):
        with self.assertRaises(ValidationError):
            submit_application(applicant=self.citizen, parcel_id=self.parcel.id, kind="steal",
                               deed_ref="x", claimant_name="ক", claimant_nid="1234567891")
        with self.assertRaises(ValidationError):
            self.apply(nid="123")

    def test_double_application_is_flagged_and_second_approval_blocked(self):
        first = self.apply(applicant=self.citizen, nid="1234567891", name="কাল্পনিক ক্রেতা ১")
        second = self.apply(applicant=self.citizen2, nid="1234567892", name="কাল্পনিক ক্রেতা ২")
        first.refresh_from_db()
        self.assertTrue(first.conflict_flag and second.conflict_flag)
        self.assertTrue(Notification.objects.filter(user=self.officer, message__contains="সতর্কতা").exists())
        for app in (first, second):
            self.act(app, self.surveyor, "survey_verify", "যাচাই")
        self.act(first, self.officer, "approve")
        with self.assertRaises(TransferRejected):
            self.act(second, self.officer, "approve")
        second.refresh_from_db()
        self.assertEqual(second.status, "survey_verified")  # rolled back, can be rejected
        self.assertEqual(current_owner(self.parcel).full_name, "কাল্পনিক ক্রেতা ১")
        self.act(second, self.officer, "reject", "আগেই অন্য আবেদন অনুমোদিত হয়েছে")

    def test_tampered_record_blocks_new_applications(self):
        head = "b" * 64
        sig = sign_checkpoint(_private_key(), self.parcel.id, 1, head)
        Checkpoint.objects.create(parcel=self.parcel, seq=1, head_hash=head, signature=sig, key_id="k1")
        with self.assertRaises(ConflictError):
            self.apply()

    def test_steps_are_immutable(self):
        self.apply()
        with self.assertRaises(ImmutableRecordError):
            MutationStep.objects.all().update(note="x")
        with self.assertRaises(ImmutableRecordError):
            MutationStep.objects.first().delete()

    def test_actions_are_audit_logged(self):
        app = self.apply()
        self.act(app, self.surveyor, "survey_verify", "ok")
        actions = list(AuditEvent.objects.order_by("seq").values_list("payload__action", flat=True))
        self.assertEqual(actions, ["parcel_created", "mutation_submitted", "mutation_survey_verify"])


@override_settings(SECURE_SSL_REDIRECT=False)
class MutationApiTests(Base, APITestCase):
    def setUp(self):
        cache.clear()
        self.make_world()

    def submit_payload(self, **extra):
        data = {"parcel_id": str(self.parcel.id), "kind": "sale", "deed_ref": "দলিল-১",
                "claimant_name": "কাল্পনিক ক্রেতা", "claimant_nid": "১২৩৪৫৬৭৮৯১"}
        data.update(extra)
        return data

    def test_requires_login_and_citizen_role(self):
        self.assertEqual(self.client.post("/api/mutations/", self.submit_payload(), format="json").status_code, 401)
        self.client.force_authenticate(self.lawyer)
        self.assertEqual(self.client.post("/api/mutations/", self.submit_payload(), format="json").status_code, 403)

    def test_end_to_end_over_http(self):
        self.client.force_authenticate(self.citizen)
        r = self.client.post("/api/mutations/", self.submit_payload(), format="json")
        self.assertEqual(r.status_code, 201)
        app_id = r.data["id"]
        mine = self.client.get("/api/mutations/mine/")
        self.assertEqual(len(mine.data["results"]), 1)

        self.client.force_authenticate(self.surveyor)
        queue = self.client.get("/api/mutations/queue/")
        self.assertEqual([a["id"] for a in queue.data["results"]], [app_id])
        r = self.client.post(f"/api/mutations/{app_id}/action/",
                             {"action": "survey_verify", "note": "যাচাই সম্পন্ন"}, format="json")
        self.assertEqual(r.status_code, 200)

        self.client.force_authenticate(self.officer)
        self.assertEqual(len(self.client.get("/api/mutations/queue/").data["results"]), 1)
        r = self.client.post(f"/api/mutations/{app_id}/action/", {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "approved")

        self.client.force_authenticate(self.citizen)
        detail = self.client.get(f"/api/mutations/{app_id}/")
        self.assertEqual(detail.data["status"], "approved")
        self.assertEqual(len(detail.data["steps"]), 3)
        self.assertNotIn("claimant", detail.data)  # applicant view hides officer-only fields
        notes = self.client.get("/api/notifications/")
        self.assertEqual(len(notes.data["results"]), 3)
        read = self.client.post(f"/api/notifications/{notes.data['results'][0]['id']}/read/")
        self.assertEqual(read.status_code, 200)

    def test_citizen_cannot_see_others_applications(self):
        self.client.force_authenticate(self.citizen)
        app_id = self.client.post("/api/mutations/", self.submit_payload(), format="json").data["id"]
        self.client.force_authenticate(self.citizen2)
        self.assertEqual(self.client.get(f"/api/mutations/{app_id}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/mutations/{app_id}/action/",
                                          {"action": "cancel"}, format="json").status_code, 403)
        self.assertEqual(self.client.get("/api/mutations/mine/").data["results"], [])

    def test_other_users_cannot_read_my_notifications(self):
        self.client.force_authenticate(self.citizen)
        self.client.post("/api/mutations/", self.submit_payload(), format="json")
        nid = self.client.get("/api/notifications/").data["results"][0]["id"]
        self.client.force_authenticate(self.citizen2)
        self.assertEqual(self.client.post(f"/api/notifications/{nid}/read/").status_code, 404)
        self.assertEqual(self.client.get("/api/notifications/").data["results"], [])

    def test_error_codes(self):
        self.client.force_authenticate(self.citizen)
        self.assertEqual(self.client.post("/api/mutations/", self.submit_payload(kind="x"), format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/mutations/", self.submit_payload(claimant_nid="12"), format="json").status_code, 400)
        missing = self.submit_payload(parcel_id="00000000-0000-0000-0000-000000000000")
        self.assertEqual(self.client.post("/api/mutations/", missing, format="json").status_code, 404)
        app_id = self.client.post("/api/mutations/", self.submit_payload(), format="json").data["id"]
        self.client.force_authenticate(self.officer)
        r = self.client.post(f"/api/mutations/{app_id}/action/", {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 409)  # not surveyed yet
        self.client.force_authenticate(self.surveyor)
        bad = self.client.post(f"/api/mutations/{app_id}/action/", {"action": "nonsense"}, format="json")
        self.assertEqual(bad.status_code, 400)
        no_note = self.client.post(f"/api/mutations/{app_id}/action/", {"action": "survey_verify"}, format="json")
        self.assertEqual(no_note.status_code, 400)

    def test_rejection_reason_is_visible_to_applicant(self):
        self.client.force_authenticate(self.citizen)
        app_id = self.client.post("/api/mutations/", self.submit_payload(), format="json").data["id"]
        self.client.force_authenticate(self.surveyor)
        self.client.post(f"/api/mutations/{app_id}/action/",
                         {"action": "survey_reject", "note": "দলিলের কপি অস্পষ্ট"}, format="json")
        self.client.force_authenticate(self.citizen)
        steps = self.client.get(f"/api/mutations/{app_id}/").data["steps"]
        self.assertEqual(steps[-1]["note"], "দলিলের কপি অস্পষ্ট")


import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import MutationDocument

PDF = b"%PDF-1.4\n" + b"0" * 300
_MEDIA = tempfile.mkdtemp(prefix="bhumi-test-media-")


@override_settings(SECURE_SSL_REDIRECT=False, MEDIA_ROOT=_MEDIA)
class DocumentTests(Base, APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.make_world()
        self.app = self.apply()

    def url(self, doc_id=None, app=None):
        base = f"/api/mutations/{(app or self.app).id}/documents/"
        return base if doc_id is None else f"{base}{doc_id}/"

    def upload(self, user, data=PDF, name="deed.pdf", ctype="application/pdf", app=None):
        self.client.force_authenticate(user)
        file = SimpleUploadedFile(name, data, content_type=ctype)
        return self.client.post(self.url(app=app), {"file": file}, format="multipart")

    def test_applicant_can_upload_and_officers_can_download(self):
        r = self.upload(self.citizen)
        self.assertEqual(r.status_code, 201)
        doc_id = r.data["id"]
        for user in (self.citizen, self.surveyor):
            self.client.force_authenticate(user)
            d = self.client.get(self.url(doc_id))
            self.assertEqual(d.status_code, 200)
            self.assertEqual(d.content, PDF)
            self.assertEqual(d["Content-Type"], "application/pdf")
            self.assertTrue(d["Content-Disposition"].startswith("attachment;"))
            self.assertEqual(d["X-Content-Type-Options"], "nosniff")
        detail = self.client.get(f"/api/mutations/{self.app.id}/")
        self.assertEqual(len(detail.data["documents"]), 1)

    def test_disguised_files_are_rejected_whatever_their_name_or_type(self):
        for data, name, ctype in [(b"MZ" + b"0" * 300, "deed.pdf", "application/pdf"),
                                  (b"<script>alert(1)</script>" + b" " * 100, "deed.pdf", "application/pdf"),
                                  (b"#!/bin/sh\n" + b" " * 100, "photo.png", "image/png"),
                                  (b"x", "tiny.pdf", "application/pdf")]:
            self.assertEqual(self.upload(self.citizen, data, name, ctype).status_code, 400)
        self.assertEqual(MutationDocument.objects.count(), 0)

    def test_oversized_file_rejected(self):
        big = b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10)
        self.assertEqual(self.upload(self.citizen, big).status_code, 413)

    def test_at_most_five_files(self):
        for _ in range(5):
            self.assertEqual(self.upload(self.citizen).status_code, 201)
        self.assertEqual(self.upload(self.citizen).status_code, 400)

    def test_other_citizens_cannot_upload_or_download(self):
        doc_id = self.upload(self.citizen).data["id"]
        self.assertEqual(self.upload(self.citizen2).status_code, 404)
        self.client.force_authenticate(self.citizen2)
        self.assertEqual(self.client.get(self.url(doc_id)).status_code, 404)

    def test_lawyer_and_anonymous_are_refused(self):
        doc_id = self.upload(self.citizen).data["id"]
        self.client.force_authenticate(self.lawyer)
        self.assertEqual(self.client.get(self.url(doc_id)).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url(doc_id)).status_code, 401)

    def test_no_uploads_after_the_survey_step(self):
        self.act(self.app, self.surveyor, "survey_verify", "যাচাই")
        self.assertEqual(self.upload(self.citizen).status_code, 409)

    def test_sender_file_name_never_reaches_disk_or_headers(self):
        r = self.upload(self.citizen, name="evil<b>name.pdf")
        self.assertEqual(r.status_code, 201)
        doc = MutationDocument.objects.get()
        self.assertNotIn("evil", doc.file.name)  # stored under a random name
        self.assertTrue(Path(doc.file.path).resolve().is_relative_to(Path(_MEDIA).resolve()))
        self.assertNotIn("<", doc.original_name)
        self.client.force_authenticate(self.citizen)
        d = self.client.get(self.url(doc.pk))
        self.assertNotIn("evil", d["Content-Disposition"])

    def test_changed_file_on_disk_is_detected(self):
        doc_id = self.upload(self.citizen).data["id"]
        doc = MutationDocument.objects.get(pk=doc_id)
        Path(doc.file.path).write_bytes(PDF + b"tampered")
        self.client.force_authenticate(self.citizen)
        self.assertEqual(self.client.get(self.url(doc_id)).status_code, 409)

    def test_documents_are_immutable_and_logged(self):
        self.upload(self.citizen)
        with self.assertRaises(ImmutableRecordError):
            MutationDocument.objects.all().delete()
        with self.assertRaises(ImmutableRecordError):
            MutationDocument.objects.all().update(kind="png")
        self.assertTrue(AuditEvent.objects.filter(payload__action="document_uploaded").exists())
        self.assertTrue(verify_audit_log().ok)

    def test_refused_actions_leave_an_audit_record(self):
        self.client.force_authenticate(self.citizen2)
        r = self.client.post(f"/api/mutations/{self.app.id}/action/", {"action": "cancel"}, format="json")
        self.assertEqual(r.status_code, 403)
        event = AuditEvent.objects.filter(payload__action="permission_denied").get()
        self.assertEqual(event.payload["actor_id"], self.citizen2.pk)
        self.assertTrue(verify_audit_log().ok)

    def test_injection_text_in_form_fields_is_stored_as_plain_text(self):
        self.client.force_authenticate(self.citizen2)
        r = self.client.post("/api/mutations/", {
            "parcel_id": str(self.parcel.id), "kind": "sale",
            "deed_ref": "'; DROP TABLE mutations_mutationapplication;--",
            "claimant_name": "<script>alert(1)</script>", "claimant_nid": "1234567895"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r["Content-Type"].startswith("application/json"))
        self.assertEqual(MutationApplication.objects.filter(parcel=self.parcel).count(), 2)
