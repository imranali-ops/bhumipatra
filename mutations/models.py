import uuid

from django.conf import settings
from django.db import models

from audit.base import AppendOnlyModel
from core.workflow import APPROVED, CANCELLED, REJECTED, SUBMITTED, SURVEY_VERIFIED


class Status(models.TextChoices):
    SUBMITTED = SUBMITTED, "আবেদন জমা হয়েছে"
    SURVEY_VERIFIED = SURVEY_VERIFIED, "সার্ভেয়ার যাচাই সম্পন্ন"
    APPROVED = APPROVED, "অনুমোদিত"
    REJECTED = REJECTED, "বাতিল"
    CANCELLED = CANCELLED, "আবেদনকারী প্রত্যাহার করেছেন"


KIND_CHOICES = [
    ("sale", "বিক্রয়"),
    ("inheritance", "ওয়ারিশ"),
    ("gift", "হেবা / দান"),
    ("court_order", "আদালতের আদেশ"),
]


class MutationApplication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                  related_name="mutation_applications")
    parcel = models.ForeignKey("records.Parcel", on_delete=models.PROTECT,
                               related_name="mutation_applications")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    deed_ref = models.CharField("দলিল / সূত্র নম্বর", max_length=100)
    seller = models.ForeignKey("records.Owner", on_delete=models.PROTECT, related_name="+")
    claimant = models.ForeignKey("records.Owner", on_delete=models.PROTECT, related_name="+")
    # Head hash of the parcel's chain when the application was filed. Approval
    # only succeeds if the parcel is still exactly in that state.
    base_head = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    conflict_flag = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(seller=models.F("claimant")),
                                   name="mutation_seller_not_claimant"),
        ]
        indexes = [models.Index(fields=["status"]),
                   models.Index(fields=["parcel", "status"])]

    @property
    def code(self) -> str:
        return str(self.id)[:8].upper()

    def __str__(self):
        return f"{self.code} [{self.status}]"


class MutationStep(AppendOnlyModel):
    """One row per status change; never edited or deleted."""
    application = models.ForeignKey(MutationApplication, on_delete=models.PROTECT,
                                    related_name="steps")
    action = models.CharField(max_length=20)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class MutationDocument(AppendOnlyModel):
    """A scanned deed/khatian attached to an application. Never edited or
    deleted (it is evidence). The stored name is random; the sender's file name
    is kept only for display. The SHA-256 is re-checked on every download."""
    KIND_CHOICES = [("pdf", "PDF"), ("jpeg", "JPEG"), ("png", "PNG")]
    application = models.ForeignKey(MutationApplication, on_delete=models.PROTECT,
                                    related_name="documents")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name="+")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    original_name = models.CharField(max_length=120)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    file = models.FileField(upload_to="mutation_docs/", max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(sha256__regex=r"^[0-9a-f]{64}$"),
                                   name="document_sha256_is_hex64"),
        ]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="notifications")
    message = models.CharField(max_length=300)
    application = models.ForeignKey(MutationApplication, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read"])]
