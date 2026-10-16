"""Checks for uploaded deed/khatian scans. Pure Python, no Django.

The file's own bytes decide what it is, never its name or the browser's
Content-Type header (both are fully controlled by the sender)."""
from __future__ import annotations

import hashlib
import unicodedata

MAX_BYTES = 5 * 1024 * 1024
MIN_BYTES = 64

SIGNATURES = (
    ("pdf", b"%PDF-"),
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("jpeg", b"\xff\xd8\xff"),
)
EXTENSION = {"pdf": ".pdf", "png": ".png", "jpeg": ".jpg"}
CONTENT_TYPE = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg"}


class UploadRejected(ValueError):
    """The file is not acceptable. The message is safe to show to the user."""


def detect_kind(head: bytes):
    for kind, magic in SIGNATURES:
        if head.startswith(magic):
            return kind
    return None


def validate_upload(data: bytes) -> str:
    if len(data) < MIN_BYTES:
        raise UploadRejected("ফাইলটি খুব ছোট বা খালি।")
    if len(data) > MAX_BYTES:
        raise UploadRejected("ফাইল ৫ MB-এর বেশি হতে পারবে না।")
    kind = detect_kind(data[:16])
    if kind is None:
        raise UploadRejected("শুধু PDF, JPG বা PNG ফাইল গ্রহণযোগ্য।")
    return kind


def safe_display_name(name: str, max_len: int = 120) -> str:
    """A name that is only ever shown on screen (never used as a file path)."""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if not unicodedata.category(ch).startswith("C"))
    name = "".join(ch for ch in name if ch not in '<>:"|?*')
    name = " ".join(name.split()).lstrip(".")
    return name[:max_len] or "document"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
