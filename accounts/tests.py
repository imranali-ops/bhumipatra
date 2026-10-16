from types import SimpleNamespace

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from audit.models import AuditEvent
from audit.services import verify_audit_log

from .models import Role, User
from .permissions import IsLandOfficer, IsLawyer, role_required

PW = "Zx9!kLm2#Qw8vB"


@override_settings(SECURE_SSL_REDIRECT=False)
class AuthApiTests(APITestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache

    def register(self, **extra):
        data = {"username": "citizen1", "password": PW, "email": "c@example.com"}
        data.update(extra)
        return self.client.post("/api/auth/register/", data, format="json")

    def login(self, username="citizen1", password=PW):
        return self.client.post("/api/auth/login/",
                                {"username": username, "password": password}, format="json")

    def test_register_creates_citizen_only(self):
        r = self.register(role="ac_land", is_superuser=True, is_staff=True)
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(username="citizen1")
        self.assertEqual(user.role, Role.CITIZEN)
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_weak_or_invalid_registration_rejected(self):
        self.assertEqual(self.register(password="12345678").status_code, 400)
        self.assertEqual(self.register(password="short1!").status_code, 400)
        self.assertEqual(self.register(username="a b").status_code, 400)
        self.register()
        self.assertEqual(self.register(username="CITIZEN1").status_code, 400)

    def test_password_is_hashed_with_argon2(self):
        self.register()
        self.assertTrue(User.objects.get(username="citizen1").password.startswith("argon2"))

    def test_login_me_refresh_logout(self):
        self.register()
        r = self.login()
        self.assertEqual(r.status_code, 200)
        access, refresh = r.data["access"], r.data["refresh"]
        me = self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["role"], "citizen")
        new = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(new.status_code, 200)
        # the old refresh token was rotated out and must not work again
        again = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(again.status_code, 401)
        out = self.client.post("/api/auth/logout/", {"refresh": new.data["refresh"]}, format="json")
        self.assertEqual(out.status_code, 200)
        after = self.client.post("/api/auth/refresh/", {"refresh": new.data["refresh"]}, format="json")
        self.assertEqual(after.status_code, 401)

    def test_protected_endpoint_needs_token(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        r = self.client.get("/api/auth/me/", HTTP_AUTHORIZATION="Bearer not-a-token")
        self.assertEqual(r.status_code, 401)

    def test_wrong_password_fails_and_is_logged_without_username(self):
        self.register()
        r = self.login(password="wrong-password-123")
        self.assertEqual(r.status_code, 401)
        event = AuditEvent.objects.filter(payload__action="login_failed").get()
        self.assertIsNone(event.payload["actor_id"])
        self.assertNotIn("citizen1", str(event.payload))

    def test_login_is_rate_limited(self):
        self.register()
        codes = [self.login(password="wrong-password-123").status_code for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)

    def test_inactive_user_cannot_login(self):
        self.register()
        User.objects.filter(username="citizen1").update(is_active=False)
        self.assertEqual(self.login().status_code, 401)

    def test_audit_log_stays_valid_after_auth_activity(self):
        self.register()
        self.login()
        self.login(password="wrong-password-123")
        actions = list(AuditEvent.objects.order_by("seq").values_list("payload__action", flat=True))
        self.assertEqual(actions, ["register", "login_success", "login_failed"])
        self.assertTrue(verify_audit_log().ok)


class RolePermissionTests(SimpleTestCase):
    def check(self, permission, role=None, active=True, authenticated=True):
        user = SimpleNamespace(is_authenticated=authenticated, is_active=active, role=role)
        return permission().has_permission(SimpleNamespace(user=user), None)

    def test_exact_role_only(self):
        self.assertTrue(self.check(IsLandOfficer, Role.AC_LAND))
        for role in (Role.CITIZEN, Role.SURVEYOR, Role.LAWYER, Role.ADMIN):
            self.assertFalse(self.check(IsLandOfficer, role))

    def test_inactive_or_anonymous_denied(self):
        self.assertFalse(self.check(IsLandOfficer, Role.AC_LAND, active=False))
        self.assertFalse(self.check(IsLandOfficer, Role.AC_LAND, authenticated=False))
        self.assertFalse(IsLawyer().has_permission(SimpleNamespace(user=None), None))

    def test_multiple_roles(self):
        perm = role_required(Role.SURVEYOR, Role.AC_LAND)
        self.assertTrue(self.check(perm, Role.SURVEYOR))
        self.assertTrue(self.check(perm, Role.AC_LAND))
        self.assertFalse(self.check(perm, Role.CITIZEN))


from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class CreateStaffUserTests(TestCase):
    def run_cmd(self, password, **kw):
        args = dict(username="officer_new", role="ac_land")
        args.update(kw)
        with mock.patch.dict("os.environ", {"STAFF_PASSWORD": password}):
            call_command("create_staff_user", stdout=StringIO(), **args)

    def test_creates_account_with_role_and_hashed_password(self):
        self.run_cmd("Zx9!kLm2#Qw8vB")
        user = User.objects.get(username="officer_new")
        self.assertEqual(user.role, Role.AC_LAND)
        self.assertTrue(user.password.startswith("argon2"))
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_weak_password_and_duplicates_refused(self):
        with self.assertRaises(CommandError):
            self.run_cmd("12345678")
        self.run_cmd("Zx9!kLm2#Qw8vB")
        with self.assertRaises(CommandError):
            self.run_cmd("Zx9!kLm2#Qw8vB")

    def test_citizen_role_is_not_offered(self):
        with self.assertRaises(CommandError):
            self.run_cmd("Zx9!kLm2#Qw8vB", role="citizen")
