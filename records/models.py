import hashlib
import hmac
import unicodedata
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction

from audit.base import AppendOnlyModel, ImmutableRecordError  # noqa: F401

HEX64_REGEX = r"^[0-9a-f]{64}$"
VALID_NID_LENGTHS = {10, 13, 17}


class LandType(models.TextChoices):
    AGRICULTURAL = "agri", "আবাদি"
    HOMESTEAD = "homestead", "বাস্তু"
    COMMERCIAL = "commercial", "বাণিজ্যিক"
    POND = "pond", "পুকুর"
    OTHER = "other", "অন্যান্য"


class Owner(models.Model):
    """Personal data lives here (editable/erasable), never in the hash chain.
    The NID is NOT stored: only a keyed HMAC (for lookup/duplicate checks) and
    the last 4 digits (for display)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=200)
    nid_hmac = models.CharField(max_length=64, unique=True, editable=False)
    nid_last4 = models.CharField(max_length=4, editable=False)
    address = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(nid_hmac__regex=HEX64_REGEX),
                name="owner_nid_hmac_is_hex64",
            ),
        ]

    def __str__(self):
        return f"{self.full_name} (NID ****{self.nid_last4})"

    @staticmethod
    def normalize_nid(nid: str) -> str:
        """Accept Bengali or English digits, spaces; return ASCII digits."""
        digits = []
        for ch in str(nid).strip():
            if ch.isspace():
                continue
            if not ch.isdecimal():
                raise ValidationError("NID must contain digits only")
            digits.append(str(unicodedata.decimal(ch)))
        result = "".join(digits)
        if len(result) not in VALID_NID_LENGTHS:
            raise ValidationError("NID must be 10, 13 or 17 digits")
        return result

    @classmethod
    def hash_nid(cls, nid: str) -> str:
        normalized = cls.normalize_nid(nid)
        key = settings.NID_HMAC_KEY.encode("utf-8")
        return hmac.new(key, normalized.encode("ascii"), hashlib.sha256).hexdigest()

    @classmethod
    def register(cls, full_name: str, nid: str, address: str = "") -> "Owner":
        normalized = cls.normalize_nid(nid)
        return cls.objects.create(
            full_name=full_name.strip(),
            nid_hmac=cls.hash_nid(normalized),
            nid_last4=normalized[-4:],
            address=address.strip(),
        )

    @classmethod
    def get_or_register(cls, full_name: str, nid: str, address: str = "") -> "Owner":
        """Return the owner with this NID, creating one if needed. An existing
        owner's stored name is never overwritten by a new application."""
        key = cls.hash_nid(nid)
        existing = cls.objects.filter(nid_hmac=key).first()
        if existing:
            return existing
        try:
            with transaction.atomic():
                return cls.register(full_name, nid, address)
        except IntegrityError:  # someone registered the same NID at the same moment
            return cls.objects.get(nid_hmac=key)


class Parcel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    district = models.CharField(max_length=100)
    upazila = models.CharField(max_length=100)
    mouza = models.CharField(max_length=100)
    khatian_no = models.CharField(max_length=30)
    dag_no = models.CharField(max_length=30)
    area_decimal = models.DecimalField(
        "জমির পরিমাণ (শতাংশ)", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    land_type = models.CharField(max_length=20, choices=LandType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["district", "upazila", "mouza", "khatian_no", "dag_no"],
                name="parcel_unique_location",
            ),
        ]
        indexes = [
            models.Index(fields=["khatian_no"]),
            models.Index(fields=["dag_no"]),
        ]

    def __str__(self):
        return f"খতিয়ান {self.khatian_no} / দাগ {self.dag_no}, {self.mouza}"


class OwnershipEntry(AppendOnlyModel):
    """One link in a parcel's hash chain. Payload holds only IDs and dates
    (no personal data) because it can never be edited or erased."""
    parcel = models.ForeignKey(Parcel, on_delete=models.PROTECT, related_name="entries")
    seq = models.PositiveIntegerField()
    prev_hash = models.CharField(max_length=64, editable=False)
    hash = models.CharField(max_length=64, editable=False)
    payload = models.JSONField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["parcel_id", "seq"]
        constraints = [
            models.UniqueConstraint(fields=["parcel", "seq"], name="entry_unique_seq_per_parcel"),
            models.UniqueConstraint(fields=["hash"], name="entry_unique_hash"),
            models.CheckConstraint(condition=models.Q(hash__regex=HEX64_REGEX),
                                   name="entry_hash_is_hex64"),
            models.CheckConstraint(condition=models.Q(prev_hash__regex=HEX64_REGEX),
                                   name="entry_prev_hash_is_hex64"),
        ]

    def __str__(self):
        return f"{self.parcel_id} #{self.seq}"


class Checkpoint(AppendOnlyModel):
    """Server-signed statement: 'parcel P had head hash H at sequence N'."""
    parcel = models.ForeignKey(Parcel, on_delete=models.PROTECT, related_name="checkpoints")
    seq = models.PositiveIntegerField()
    head_hash = models.CharField(max_length=64, editable=False)
    signature = models.CharField(max_length=128, editable=False)
    key_id = models.CharField(max_length=32, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["parcel_id", "seq"]
        constraints = [
            models.UniqueConstraint(fields=["parcel", "seq"], name="checkpoint_unique_seq_per_parcel"),
            models.CheckConstraint(condition=models.Q(head_hash__regex=HEX64_REGEX),
                                   name="checkpoint_head_is_hex64"),
        ]

    def __str__(self):
        return f"checkpoint {self.parcel_id} #{self.seq}"
