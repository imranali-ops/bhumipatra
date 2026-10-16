import re
import unicodedata

_ALLOWED = re.compile(r"\A[0-9A-Za-z/\-. ]+\Z")


def to_ascii_digits(text: str) -> str:
    """Turn Bengali (০-৯) and other Unicode decimal digits into 0-9."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in text)


def clean_identifier(text, max_len: int = 30) -> str:
    """Normalise a khatian/dag number typed by a person. Empty input gives ''.
    Anything other than digits, letters, / - . and spaces is rejected."""
    if text is None:
        return ""
    value = " ".join(to_ascii_digits(str(text)).split())
    if not value:
        return ""
    if len(value) > max_len or not _ALLOWED.match(value):
        raise ValueError("invalid identifier")
    return value
