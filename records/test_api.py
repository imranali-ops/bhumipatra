from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.signing import sign_checkpoint

from .models import LandType, Owner
from .services import _private_key, create_parcel_with_owner, current_head, transfer_ownership

PW = "Zx9!kLm2#Qw8vB"
PARCEL = dict(district="নমুনা জেলা", upazila="নমুনা উপজেলা", mouza="নমুনা মৌজা",
              khatian_no="1245", dag_no="883", area_decimal=Decimal("33.00"),
              land_type=LandType.AGRICULTURAL)


@override_settings(SECURE_SSL_REDIRECT=False)
class ParcelApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.officer = User.objects.create_user("officer1", password=PW, role=Role.AC_LAND)
        self.citizen = User.objects.create_user("citizen1", password=PW, role=Role.CITIZEN)
        self.lawyer = User.objects.create_user("lawyer1", password=PW, role=Role.LAWYER)
        self.a = Owner.register("কাল্পনিক ক", "1234567890")
        self.b = Owner.register("কাল্পনিক খ", "1234567891")
        self.parcel = create_parcel_with_owner(
            actor=self.officer, owner=self.a, effective_date=date(2020, 1, 1), **PARCEL)

    def test_search_requires_login(self):
        self.assertEqual(self.client.get("/api/parcels/search/?khatian_no=1245").status_code, 401)

    def test_search_finds_by_khatian_with_bengali_digits(self):
        self.client.force_authenticate(self.lawyer)
        r = self.client.get("/api/parcels/search/", {"khatian_no": "১২৪৫"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["current_owner"]["nid_last4"], "7890")

    def test_search_by_dag_and_filters(self):
        self.client.force_authenticate(self.citizen)
        ok = self.client.get("/api/parcels/search/", {"dag_no": "883", "mouza": "নমুনা মৌজা"})
        self.assertEqual(ok.data["count"], 1)
        none = self.client.get("/api/parcels/search/", {"dag_no": "883", "mouza": "অন্য মৌজা"})
        self.assertEqual(none.data["count"], 0)

    def test_search_needs_a_number_and_rejects_bad_input(self):
        self.client.force_authenticate(self.citizen)
        self.assertEqual(self.client.get("/api/parcels/search/").status_code, 400)
        self.assertEqual(self.client.get("/api/parcels/search/", {"mouza": "নমুনা মৌজা"}).status_code, 400)
        bad = self.client.get("/api/parcels/search/", {"khatian_no": "1245' OR '1'='1"})
        self.assertEqual(bad.status_code, 400)

    def test_detail_shows_history_and_integrity(self):
        transfer_ownership(actor=self.officer, parcel_id=self.parcel.id, seller_id=self.a.id,
                           buyer_id=self.b.id, expected_head=current_head(self.parcel),
                           kind="sale", ref="দলিল-১", effective_date=date(2024, 5, 1))
        self.client.force_authenticate(self.lawyer)
        r = self.client.get(f"/api/parcels/{self.parcel.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["integrity"]["ok"])
        self.assertEqual([h["owner"]["name"] for h in r.data["history"]],
                         ["কাল্পনিক ক", "কাল্পনিক খ"])
        self.assertEqual(r.data["current_owner"]["name"], "কাল্পনিক খ")
        self.assertIn(f"/verify/{self.parcel.id}/", r.data["verify_url"])

    def test_detail_requires_login_and_unknown_is_404(self):
        self.assertEqual(self.client.get(f"/api/parcels/{self.parcel.id}/").status_code, 401)
        self.client.force_authenticate(self.lawyer)
        self.assertEqual(
            self.client.get("/api/parcels/00000000-0000-0000-0000-000000000000/").status_code, 404)

    def test_qr_is_svg(self):
        self.client.force_authenticate(self.officer)
        r = self.client.get(f"/api/parcels/{self.parcel.id}/qr.svg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/svg+xml")
        self.assertTrue(r.content.lstrip().startswith(b"<svg"))

    def test_public_verify_current_then_outdated_without_personal_data(self):
        prefix = current_head(self.parcel)[:16]
        url = f"/api/verify/{self.parcel.id}/{prefix}/"
        r = self.client.get(url)  # no login at all
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "valid_current")
        self.assertNotIn("কাল্পনিক", r.content.decode())
        self.assertNotIn("owner", r.content.decode())
        transfer_ownership(actor=self.officer, parcel_id=self.parcel.id, seller_id=self.a.id,
                           buyer_id=self.b.id, expected_head=current_head(self.parcel),
                           kind="sale", ref="দলিল-১", effective_date=date(2024, 5, 1))
        self.assertEqual(self.client.get(url).data["status"], "valid_outdated")

    def test_public_verify_bad_inputs(self):
        self.assertEqual(self.client.get(f"/api/verify/{self.parcel.id}/nothex/").status_code, 404)
        self.assertEqual(
            self.client.get("/api/verify/00000000-0000-0000-0000-000000000000/" + "a" * 16 + "/").status_code, 404)

    def test_public_verify_reports_tampered_record(self):
        from .models import Checkpoint
        head = "b" * 64
        sig = sign_checkpoint(_private_key(), self.parcel.id, 1, head)
        Checkpoint.objects.create(parcel=self.parcel, seq=1, head_hash=head, signature=sig,
                                  key_id="k1")
        r = self.client.get(f"/api/verify/{self.parcel.id}/{'a' * 16}/")
        self.assertEqual(r.data["status"], "invalid")

    def test_public_verify_is_rate_limited(self):
        url = f"/api/verify/{self.parcel.id}/{'a' * 16}/"
        codes = [self.client.get(url).status_code for _ in range(31)]
        self.assertEqual(codes[-1], 429)
