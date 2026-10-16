import re
import uuid

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import CanVerifyRecords
from core.textnorm import clean_identifier

from .models import LandType, Owner, Parcel
from .qr import qr_svg, verify_url
from .services import current_head, current_owner, verify_parcel, _chain

HEAD_PREFIX = re.compile(r"\A[0-9a-f]{16}\Z")
MAX_RESULTS = 20


def _parcel_fields(parcel):
    return {
        "id": str(parcel.id),
        "district": parcel.district, "upazila": parcel.upazila, "mouza": parcel.mouza,
        "khatian_no": parcel.khatian_no, "dag_no": parcel.dag_no,
        "area_decimal": str(parcel.area_decimal),
        "land_type": parcel.get_land_type_display(),
    }


class ParcelSearchView(APIView):
    """Look up parcels by khatian and/or dag number. At least one is required,
    results are capped, and the endpoint is rate limited, so the register
    cannot be downloaded in bulk."""
    permission_classes = [CanVerifyRecords]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

    def get(self, request):
        params = request.query_params
        try:
            khatian = clean_identifier(params.get("khatian_no"))
            dag = clean_identifier(params.get("dag_no"))
        except ValueError:
            raise ValidationError({"detail": "নম্বরে শুধু অঙ্ক, অক্ষর, / - . ব্যবহার করুন।"})
        if not khatian and not dag:
            raise ValidationError({"detail": "খতিয়ান নম্বর অথবা দাগ নম্বর দিন।"})
        qs = Parcel.objects.all()
        if khatian:
            qs = qs.filter(khatian_no=khatian)
        if dag:
            qs = qs.filter(dag_no=dag)
        for field in ("district", "upazila", "mouza"):
            value = (params.get(field) or "").strip()[:100]
            if value:
                qs = qs.filter(**{field: value})
        results = []
        for parcel in qs.order_by("district", "upazila", "mouza", "khatian_no", "dag_no")[:MAX_RESULTS]:
            owner = current_owner(parcel)
            item = _parcel_fields(parcel)
            item["current_owner"] = {"name": owner.full_name, "nid_last4": owner.nid_last4}
            results.append(item)
        return Response({"count": len(results), "results": results})


class ParcelDetailView(APIView):
    permission_classes = [CanVerifyRecords]

    def get(self, request, pk):
        parcel = get_object_or_404(Parcel, pk=pk)
        chain = _chain(parcel)
        check = verify_parcel(parcel)
        owner_ids = {uuid.UUID(e["payload"]["owner_id"]) for e in chain}
        owners = Owner.objects.in_bulk(owner_ids)
        history = []
        for e in chain:
            owner = owners.get(uuid.UUID(e["payload"]["owner_id"]))
            history.append({
                "seq": e["seq"],
                "kind": e["payload"]["kind"],
                "effective_date": e["payload"]["effective_date"],
                "ref": e["payload"]["ref"],
                "owner": {"name": owner.full_name, "nid_last4": owner.nid_last4} if owner else None,
                "hash": e["hash"],
            })
        data = _parcel_fields(parcel)
        data["integrity"] = {"ok": check.ok, "reason": check.reason}
        data["history"] = history
        if chain:
            data["current_owner"] = history[-1]["owner"]
            data["verify_url"] = verify_url(parcel.id, chain[-1]["hash"])
        return Response(data)


class ParcelQrView(APIView):
    permission_classes = [CanVerifyRecords]

    def get(self, request, pk):
        parcel = get_object_or_404(Parcel, pk=pk)
        svg = qr_svg(verify_url(parcel.id, current_head(parcel)))
        return HttpResponse(svg, content_type="image/svg+xml")


class PublicVerifyView(APIView):
    """What a QR scan opens. Public, so it shows NO personal data: only the
    parcel identifiers and whether the record is intact and up to date."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_verify"

    def get(self, request, pk, head_prefix):
        if not HEAD_PREFIX.match(head_prefix):
            raise NotFound()
        parcel = Parcel.objects.filter(pk=pk).first()
        if parcel is None:
            raise NotFound()
        check = verify_parcel(parcel)
        body = {"checked_at": timezone.now().isoformat(), **{
            k: v for k, v in _parcel_fields(parcel).items() if k != "id"}}
        if not check.ok:
            body["status"] = "invalid"
            return Response(body)
        chain = _chain(parcel)
        body["last_effective_date"] = chain[-1]["payload"]["effective_date"]
        body["status"] = "valid_current" if chain[-1]["hash"].startswith(head_prefix) else "valid_outdated"
        return Response(body)
