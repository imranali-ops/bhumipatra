"""Business rules for e-mutation. All writes happen here, each inside one
database transaction (status change + step + audit log + notification, and
for approval also the ownership change itself)."""
from __future__ import annotations

import datetime
import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import transaction

from accounts.models import Role, User
from audit.services import log_event
from core.integrity import TransferRejected
from core.uploads import EXTENSION, safe_display_name, sha256_hex, validate_upload
from core.workflow import (
    ACTIVE_STATUSES, ACTIONS, NOTE_REQUIRED, SUBMITTED, InvalidTransition, RoleNotAllowed,
    next_status,
)
from records.models import Owner, Parcel
from records.services import (
    TRANSFER_KINDS, current_head, current_owner, transfer_ownership, verify_parcel,
)

from .models import MutationApplication, MutationDocument, MutationStep, Notification

MAX_NOTE = 2000
MAX_DOCUMENTS = 5


class ConflictError(Exception):
    """The request clashes with the current state of the record."""


def _active(user) -> bool:
    return user is not None and getattr(user, "is_active", False)


def notify(user, message: str, application: MutationApplication | None = None) -> None:
    """In-app notification now; e-mail only after the transaction commits
    (nothing is sent for work that was rolled back). Messages never contain
    names, NIDs or other personal data. An SMS gateway plugs in here later."""
    Notification.objects.create(user=user, message=message[:300], application=application)
    if user.email:
        email, text = user.email, message
        transaction.on_commit(lambda: send_mail(
            "ভূমিপত্র: আবেদনের হালনাগাদ", text, settings.DEFAULT_FROM_EMAIL,
            [email], fail_silently=True))


def _notify_role(role: str, message: str, application) -> None:
    for officer in User.objects.filter(role=role, is_active=True):
        notify(officer, message, application)


@transaction.atomic
def submit_application(*, applicant, parcel_id, kind: str, deed_ref: str,
                       claimant_name: str, claimant_nid: str,
                       claimant_address: str = "", ip: str | None = None) -> MutationApplication:
    if not _active(applicant) or applicant.role != Role.CITIZEN:
        raise PermissionDenied("only citizens can file a mutation application")
    if kind not in TRANSFER_KINDS:
        raise ValidationError("অবৈধ ধরন।")
    deed_ref, claimant_name = deed_ref.strip(), claimant_name.strip()
    if not deed_ref or len(deed_ref) > 100:
        raise ValidationError("দলিল / সূত্র নম্বর দিন (সর্বোচ্চ ১০০ অক্ষর)।")
    if not claimant_name or len(claimant_name) > 200:
        raise ValidationError("নতুন মালিকের নাম দিন।")

    parcel = Parcel.objects.select_for_update().get(pk=parcel_id)
    check = verify_parcel(parcel)
    if not check.ok:
        raise ConflictError("এই জমির রেকর্ডের অখণ্ডতা যাচাই ব্যর্থ হয়েছে, আবেদন নেওয়া যাচ্ছে না।")
    seller = current_owner(parcel)
    claimant = Owner.get_or_register(claimant_name, claimant_nid, claimant_address)
    if claimant.pk == seller.pk:
        raise ValidationError("নতুন মালিক ও বর্তমান মালিক একই ব্যক্তি হতে পারেন না।")

    others = MutationApplication.objects.filter(parcel=parcel, status__in=ACTIVE_STATUSES)
    conflict = others.exists()
    app = MutationApplication.objects.create(
        applicant=applicant, parcel=parcel, kind=kind, deed_ref=deed_ref,
        seller=seller, claimant=claimant, base_head=current_head(parcel),
        conflict_flag=conflict)
    if conflict:
        others.update(conflict_flag=True)  # warn about the earlier ones too
    MutationStep.objects.create(application=app, action="submit", from_status="",
                                to_status=app.status, actor=applicant)
    log_event(actor=applicant, action="mutation_submitted", target_type="mutation",
              target_id=app.id, ip=ip, metadata={"parcel_id": str(parcel.id), "conflict": conflict})
    notify(applicant, f"আবেদন {app.code} জমা হয়েছে।", app)
    if conflict:
        _notify_role(Role.AC_LAND,
                     f"সতর্কতা: একই জমির জন্য একাধিক আবেদন চলমান (আবেদন {app.code})।", app)
    return app


_MESSAGES = {
    "survey_verify": "আপনার আবেদন {code} সার্ভেয়ার যাচাই করেছেন, এখন সহকারী কমিশনারের (ভূমি) অনুমোদনের অপেক্ষায়।",
    "survey_reject": "আপনার আবেদন {code} সার্ভেয়ার বাতিল করেছেন।",
    "approve": "আপনার আবেদন {code} অনুমোদিত হয়েছে, রেকর্ড হালনাগাদ করা হয়েছে।",
    "reject": "আপনার আবেদন {code} বাতিল করা হয়েছে।",
    "cancel": "আপনার আবেদন {code} প্রত্যাহার করা হয়েছে।",
}


@transaction.atomic
def advance_application(*, actor, application_id, action: str, note: str = "",
                        ip: str | None = None) -> MutationApplication:
    if not _active(actor):
        raise PermissionDenied("inactive account")
    if action not in ACTIONS:
        raise ValidationError("অবৈধ কাজ।")
    note = (note or "").strip()
    if len(note) > MAX_NOTE:
        raise ValidationError("মন্তব্য খুব বড়।")
    if action in NOTE_REQUIRED and not note:
        raise ValidationError("এই কাজের জন্য মন্তব্য / প্রতিবেদন লিখতে হবে।")

    # Lock order is always parcel first, then application (same as submit), so
    # two requests can never wait on each other in a circle (deadlock).
    parcel_id = MutationApplication.objects.values_list("parcel_id", flat=True).get(pk=application_id)
    Parcel.objects.select_for_update().get(pk=parcel_id)
    app = MutationApplication.objects.select_for_update().get(pk=application_id)
    is_applicant = app.applicant_id == actor.pk
    # separation of duties: you may not process your own application,
    # and only the applicant may cancel it
    if action == "cancel" and not is_applicant:
        raise PermissionDenied("only the applicant can cancel")
    if action != "cancel" and is_applicant:
        raise PermissionDenied("you cannot process your own application")
    try:
        new_status = next_status(app.status, action, actor.role)
    except RoleNotAllowed as exc:
        raise PermissionDenied(str(exc))
    except InvalidTransition as exc:
        raise ConflictError(str(exc))

    old_status = app.status
    if action == "approve":
        # Applies the ownership change (hash chain + signed checkpoint + audit).
        # If the parcel changed since filing, this raises TransferRejected and
        # the whole transaction, including this status change, is rolled back.
        transfer_ownership(
            actor=actor, parcel_id=app.parcel_id, seller_id=app.seller_id,
            buyer_id=app.claimant_id, expected_head=app.base_head, kind=app.kind,
            ref=app.deed_ref, effective_date=datetime.date.today(), ip=ip)
    app.status = new_status
    if note:
        app.note = note
    app.save(update_fields=["status", "note", "updated_at"])
    MutationStep.objects.create(application=app, action=action, from_status=old_status,
                                to_status=new_status, actor=actor, note=note)
    log_event(actor=actor, action=f"mutation_{action}", target_type="mutation",
              target_id=app.id, ip=ip, metadata={"from": old_status, "to": new_status})
    notify(app.applicant, _MESSAGES[action].format(code=app.code), app)
    if action == "survey_verify":
        _notify_role(Role.AC_LAND, f"আবেদন {app.code} অনুমোদনের জন্য প্রস্তুত।", app)
    return app


@transaction.atomic
def upload_document(*, actor, application_id, data: bytes, filename: str,
                    ip: str | None = None) -> MutationDocument:
    """Attach a scan to your own application while it is still 'submitted'."""
    if not _active(actor):
        raise PermissionDenied("inactive account")
    kind = validate_upload(data)  # looks at the bytes, not the name or Content-Type
    app = MutationApplication.objects.select_for_update().get(pk=application_id)
    if app.applicant_id != actor.pk:
        raise MutationApplication.DoesNotExist  # someone else's application: pretend it does not exist
    if app.status != SUBMITTED:
        raise ConflictError("এই অবস্থায় আর নতুন কাগজ যোগ করা যাবে না।")
    if app.documents.count() >= MAX_DOCUMENTS:
        raise ValidationError(f"একটি আবেদনে সর্বোচ্চ {MAX_DOCUMENTS}টি ফাইল দেওয়া যায়।")
    doc = MutationDocument(application=app, uploaded_by=actor, kind=kind,
                           original_name=safe_display_name(filename),
                           size=len(data), sha256=sha256_hex(data))
    doc.file.save(f"{uuid.uuid4().hex}{EXTENSION[kind]}", ContentFile(data), save=False)
    doc.save()
    log_event(actor=actor, action="document_uploaded", target_type="mutation",
              target_id=app.id, ip=ip, metadata={"doc_id": doc.pk, "kind": kind, "sha256": doc.sha256})
    return doc


def read_document(*, actor, application_id, doc_id):
    """Return (document, bytes) for the applicant or an officer, after
    re-checking the stored SHA-256."""
    if not _active(actor):
        raise PermissionDenied("inactive account")
    app = MutationApplication.objects.get(pk=application_id)
    if not (app.applicant_id == actor.pk or actor.role in (Role.SURVEYOR, Role.AC_LAND)):
        raise MutationApplication.DoesNotExist
    doc = app.documents.get(pk=doc_id)
    with doc.file.open("rb") as handle:
        data = handle.read()
    if sha256_hex(data) != doc.sha256:
        raise ConflictError("ফাইলটির অখণ্ডতা যাচাই ব্যর্থ হয়েছে (ফাইল বদলানো হয়েছে)।")
    return doc, data
