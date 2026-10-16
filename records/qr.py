import io

from django.conf import settings


def verify_url(parcel_id, head_hash: str) -> str:
    """URL printed in the QR code. It carries the first 16 hex chars of the
    record's head hash, so a QR printed before an ownership change is
    reported as 'outdated' when scanned later."""
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/verify/{parcel_id}/{head_hash[:16]}"


def qr_svg(url: str) -> bytes:
    import segno
    buffer = io.BytesIO()
    segno.make(url, error="m").save(buffer, kind="svg", scale=6, border=2, xmldecl=False)
    return buffer.getvalue()
