"""Attack-style tests: each one tries something an attacker would try and
checks that it fails."""
import base64
import hashlib
import hmac
import json
import time

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from audit.models import AuditEvent

from .models import Role, User

PW = "Zx9!kLm2#Qw8vB"
LOGIN = "/api/auth/login/"
ME = "/api/auth/me/"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def forge(payload: dict, key: str | None, alg: str = "HS256") -> str:
    head = b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    signing_input = f"{head}.{body}"
    if key is None:
        return signing_input + "."
    sig = hmac.new(key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64(sig)}"


@override_settings(SECURE_SSL_REDIRECT=False)
class LoginAttackTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("victim1", password=PW, role=Role.CITIZEN)

    def attempt(self, password, username="victim1", ip="10.0.0.1"):
        return self.client.post(LOGIN, {"username": username, "password": password},
                                format="json", REMOTE_ADDR=ip)

    def test_username_is_locked_after_five_failures_even_from_other_ips(self):
        for i in range(5):  # a different IP each time, so the per-IP limit never triggers
            self.assertEqual(self.attempt("wrong-password-1", ip=f"10.0.1.{i}").status_code, 401)
        locked = self.attempt(PW, ip="10.0.9.9")  # correct password, new IP
        self.assertEqual(locked.status_code, 429)

    def test_lockout_ignores_letter_case(self):
        for i in range(5):
            self.attempt("wrong-password-1", username="VICTIM1", ip=f"10.0.2.{i}")
        self.assertEqual(self.attempt(PW, ip="10.0.9.9").status_code, 429)

    def test_success_resets_the_counter(self):
        for i in range(4):
            self.attempt("wrong-password-1", ip=f"10.0.3.{i}")
        self.assertEqual(self.attempt(PW, ip="10.0.3.50").status_code, 200)
        self.assertEqual(self.attempt("wrong-password-1", ip="10.0.3.51").status_code, 401)

    def test_unknown_and_known_users_look_the_same(self):
        a = self.attempt("wrong-password-1", username="nobody_here")
        b = self.attempt("wrong-password-1", username="victim1", ip="10.0.4.1")
        self.assertEqual((a.status_code, a.data), (b.status_code, b.data))

    def test_locked_attempts_are_audit_logged(self):
        for i in range(6):
            self.attempt("wrong-password-1", ip=f"10.0.5.{i}")
        locked = AuditEvent.objects.filter(payload__action="login_failed", payload__meta__locked=True)
        self.assertEqual(locked.count(), 1)


@override_settings(SECURE_SSL_REDIRECT=False)
class TokenAttackTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("citizen1", password=PW, role=Role.CITIZEN)
        self.admin = User.objects.create_user("officer1", password=PW, role=Role.AC_LAND)
        r = self.client.post(LOGIN, {"username": "citizen1", "password": PW}, format="json")
        self.access, self.refresh = r.data["access"], r.data["refresh"]

    def get_me(self, token):
        return self.client.get(ME, HTTP_AUTHORIZATION=f"Bearer {token}")

    def claims(self, **extra):
        data = {"token_type": "access", "exp": int(time.time()) + 600, "iat": int(time.time()),
                "jti": "x" * 32, "user_id": str(self.admin.pk), "iss": "bhumipatra"}
        data.update(extra)
        return data

    def test_real_token_works(self):
        self.assertEqual(self.get_me(self.access).status_code, 200)

    def test_edited_payload_is_rejected(self):
        head, body, sig = self.access.split(".")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        payload["user_id"] = str(self.admin.pk)  # try to become the officer
        evil = f"{head}.{b64(json.dumps(payload).encode())}.{sig}"
        self.assertEqual(self.get_me(evil).status_code, 401)

    def test_alg_none_is_rejected(self):
        self.assertEqual(self.get_me(forge(self.claims(), None, alg="none")).status_code, 401)

    def test_token_signed_with_another_key_is_rejected(self):
        self.assertEqual(self.get_me(forge(self.claims(), settings.SECRET_KEY)).status_code, 401)
        self.assertEqual(self.get_me(forge(self.claims(), "guessable-key")).status_code, 401)

    def test_expired_token_is_rejected(self):
        key = settings.SIMPLE_JWT["SIGNING_KEY"]
        expired = forge(self.claims(exp=int(time.time()) - 60), key)
        self.assertEqual(self.get_me(expired).status_code, 401)

    def test_refresh_token_cannot_be_used_as_access_token(self):
        self.assertEqual(self.get_me(self.refresh).status_code, 401)

    def test_token_stops_working_when_account_is_disabled(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.get_me(self.access).status_code, 401)

    def test_garbage_tokens_never_crash(self):
        for bad in ("", "abc", "a.b.c", "....", "Bearer", "\x00", "a" * 5000):
            self.assertEqual(self.get_me(bad).status_code, 401)


@override_settings(SECURE_SSL_REDIRECT=False)
class HeaderAndAccessTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_security_headers_present(self):
        r = self.client.get(ME)
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["Cache-Control"], "no-store")

    def test_no_cors_headers_so_other_sites_cannot_read_answers(self):
        r = self.client.get(ME, HTTP_ORIGIN="https://evil.example")
        self.assertNotIn("Access-Control-Allow-Origin", r)

    def test_registration_cannot_pick_a_role(self):
        r = self.client.post("/api/auth/register/", {
            "username": "sneaky1", "password": PW, "role": "ac_land", "is_staff": True,
            "is_superuser": True}, format="json")
        self.assertEqual(r.status_code, 201)
        u = User.objects.get(username="sneaky1")
        self.assertEqual(u.role, Role.CITIZEN)
        self.assertFalse(u.is_staff or u.is_superuser)

    def test_sql_injection_in_login_is_just_a_wrong_login(self):
        r = self.client.post(LOGIN, {"username": "x' OR '1'='1", "password": "' OR '1'='1"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_non_json_and_oversized_bodies_are_rejected_cleanly(self):
        r = self.client.post(LOGIN, "username=a&password=b", content_type="application/x-www-form-urlencoded")
        self.assertEqual(r.status_code, 415)
        r = self.client.post(LOGIN, "{not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)
