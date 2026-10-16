import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import role_required
from accounts.views import client_ip
from audit.services import log_event
from core.integrity import TransferRejected
from core.uploads import CONTENT_TYPE, EXTENSION, MAX_BYTES, UploadRejected
from core.workflow import ACTIONS, SURVEY_VERIFIED, SUBMITTED
from records.models import Owner, Parcel

from .models import KIND_CHOICES, MutationApplication, Notification
from .services import (
    ConflictError, advance_application, read_document, submit_application, upload_document,
)

security_log = logging.getLogger("security")


# Rejection reasons are shown to the applicant; surveyor reports stay internal.
PUBLIC_NOTE_ACTIONS = {"reject", "survey_reject"}


class PayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "ফাইল ৫ MB-এর বেশি হতে পারবে না।"
    default_code = "payload_too_large"


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "অনুরোধটি রেকর্ডের বর্তমান অবস্থার সাথে সাংঘর্ষিক।"
    default_code = "conflict"


def run_service(fn, **kwargs):
    """Translate service-layer errors into clean HTTP errors (no stack traces,
    no internal details)."""
    try:
        return fn(**kwargs)
    except UploadRejected as exc:
        raise ValidationError({"detail": [str(exc)]})
    except DjangoValidationError as exc:
        raise ValidationError({"detail": exc.messages})
    except (ConflictError, TransferRejected) as exc:
        raise Conflict(str(exc))
    except (Parcel.DoesNotExist, MutationApplication.DoesNotExist, Owner.DoesNotExist):
        raise NotFound()
    except DjangoPermissionDenied:
        # A refused action is worth a record: repeated refusals can mean someone is probing.
        try:
            log_event(actor=kwargs.get("actor") or kwargs.get("applicant"),
                      action="permission_denied", target_type="mutation",
                      target_id=str(kwargs.get("application_id", "")), ip=kwargs.get("ip"),
                      metadata={"op": fn.__name__})
        except Exception:  # never let a logging problem hide the 403
            security_log.exception("could not write permission_denied audit event")
        raise  # DRF turns this into 403


class SubmitSerializer(serializers.Serializer):
    parcel_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=[k for k, _ in KIND_CHOICES])
    deed_ref = serializers.CharField(max_length=100)
    claimant_name = serializers.CharField(max_length=200)
    claimant_nid = serializers.CharField(max_length=30)
    claimant_address = serializers.CharField(max_length=300, required=False, allow_blank=True)


class ActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=sorted(ACTIONS))
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)


def app_summary(app, officer_view=False, steps=False):
    data = {
        "id": str(app.id), "code": app.code, "status": app.status,
        "status_label": app.get_status_display(), "kind": app.kind,
        "kind_label": app.get_kind_display(), "deed_ref": app.deed_ref,
        "parcel": {"id": str(app.parcel_id), "khatian_no": app.parcel.khatian_no,
                   "dag_no": app.parcel.dag_no, "mouza": app.parcel.mouza},
        "conflict_flag": app.conflict_flag,
        "created_at": app.created_at.isoformat(), "updated_at": app.updated_at.isoformat(),
    }
    if officer_view:
        data["seller"] = {"name": app.seller.full_name, "nid_last4": app.seller.nid_last4}
        data["claimant"] = {"name": app.claimant.full_name, "nid_last4": app.claimant.nid_last4}
        data["note"] = app.note
    if steps:
        data["documents"] = [{"id": d.pk, "kind": d.kind, "name": d.original_name, "size": d.size,
                              "sha256": d.sha256, "created_at": d.created_at.isoformat()}
                             for d in app.documents.all()]
        data["steps"] = [{"action": s.action, "from": s.from_status, "to": s.to_status,
                          "note": s.note if (officer_view or s.action in PUBLIC_NOTE_ACTIONS) else "",
                          "at": s.created_at.isoformat()} for s in app.steps.all()]
    return data


def _base_qs():
    return MutationApplication.objects.select_related("parcel", "seller", "claimant")


class SubmitView(APIView):
    permission_classes = [role_required(Role.CITIZEN)]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mutation"

    def post(self, request):
        data = SubmitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        app = run_service(submit_application, applicant=request.user,
                          ip=client_ip(request), **data.validated_data)
        return Response(app_summary(_base_qs().get(pk=app.pk)), status=status.HTTP_201_CREATED)


class MineView(APIView):
    permission_classes = [role_required(Role.CITIZEN)]

    def get(self, request):
        qs = _base_qs().filter(applicant=request.user)[:100]
        return Response({"results": [app_summary(a) for a in qs]})


class QueueView(APIView):
    """Surveyors see applications waiting for survey; land officers see those
    waiting for approval."""
    permission_classes = [role_required(Role.SURVEYOR, Role.AC_LAND)]

    def get(self, request):
        wanted = SUBMITTED if request.user.role == Role.SURVEYOR else SURVEY_VERIFIED
        qs = _base_qs().filter(status=wanted).order_by("created_at")[:100]
        return Response({"results": [app_summary(a, officer_view=True) for a in qs]})


class DetailView(APIView):
    permission_classes = [role_required(Role.CITIZEN, Role.SURVEYOR, Role.AC_LAND)]

    def get(self, request, pk):
        app = _base_qs().prefetch_related("steps", "documents").filter(pk=pk).first()
        officer = request.user.role in (Role.SURVEYOR, Role.AC_LAND)
        # a citizen asking for someone else's application gets 404, not 403,
        # so the existence of other people's applications is not revealed
        if app is None or (not officer and app.applicant_id != request.user.id):
            raise NotFound()
        return Response(app_summary(app, officer_view=officer, steps=True))


class ActionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mutation"

    def post(self, request, pk):
        data = ActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        app = run_service(advance_application, actor=request.user, application_id=pk,
                          action=data.validated_data["action"],
                          note=data.validated_data.get("note", ""), ip=client_ip(request))
        return Response(app_summary(_base_qs().get(pk=app.pk), officer_view=True))


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user)[:50]
        return Response({"results": [
            {"id": n.id, "message": n.message, "read": n.read,
             "application_id": str(n.application_id) if n.application_id else None,
             "created_at": n.created_at.isoformat()} for n in qs]})


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        updated = Notification.objects.filter(pk=pk, user=request.user).update(read=True)
        if not updated:
            raise NotFound()
        return Response({"id": pk, "read": True})


class DocumentUploadView(APIView):
    permission_classes = [role_required(Role.CITIZEN)]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "upload"

    def post(self, request, pk):
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            declared = 0
        if declared > MAX_BYTES + 100_000:  # refuse before reading the body
            raise PayloadTooLarge()
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"detail": ["ফাইল দিন।"]})
        if upload.size > MAX_BYTES:
            raise PayloadTooLarge()
        doc = run_service(upload_document, actor=request.user, application_id=pk,
                          data=upload.read(), filename=upload.name or "", ip=client_ip(request))
        return Response({"id": doc.pk, "kind": doc.kind, "name": doc.original_name,
                         "size": doc.size, "sha256": doc.sha256}, status=status.HTTP_201_CREATED)


class DocumentDownloadView(APIView):
    permission_classes = [role_required(Role.CITIZEN, Role.SURVEYOR, Role.AC_LAND)]

    def get(self, request, pk, doc_id):
        doc, data = run_service(read_document, actor=request.user, application_id=pk, doc_id=doc_id)
        response = HttpResponse(data, content_type=CONTENT_TYPE[doc.kind])
        # server-chosen name: nothing the uploader typed ever reaches a header
        response["Content-Disposition"] = f'attachment; filename="document-{doc.pk}{EXTENSION[doc.kind]}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response
