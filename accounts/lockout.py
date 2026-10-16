"""Per-username brute-force protection, in addition to the per-IP rate limit.

After MAX_FAILURES wrong passwords for one username, further logins for that
username are refused for WINDOW seconds, even with the correct password. The
username is stored only as a hash. This uses Django's cache: use a shared cache
(Redis) in production so the counters survive restarts and work across servers.
Trade-off: someone can deliberately lock a known username for a while; the
per-IP limit and the lockout timeout keep that short."""
import hashlib

from django.core.cache import cache

MAX_FAILURES = 5
WINDOW = 15 * 60


def _key(username: str) -> str:
    digest = hashlib.sha256(username.strip().lower().encode("utf-8")).hexdigest()
    return f"loginfail:{digest}"


def is_locked(username: str) -> bool:
    return cache.get(_key(username), 0) >= MAX_FAILURES


def record_failure(username: str) -> int:
    key = _key(username)
    try:
        return cache.incr(key)
    except ValueError:  # first failure in this window
        cache.set(key, 1, WINDOW)
        return 1


def reset(username: str) -> None:
    cache.delete(_key(username))
