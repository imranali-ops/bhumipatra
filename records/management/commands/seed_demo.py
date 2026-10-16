"""python manage.py seed_demo  -> demo accounts + FICTIONAL parcels for testing.
Refuses to run unless DJANGO_DEBUG=true. Passwords are random and printed once."""
import datetime
import secrets
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role, User
from mutations.services import submit_application
from records.models import LandType, Owner
from records.services import create_parcel_with_owner, current_head, transfer_ownership

ACCOUNTS = [
    ("demo_officer", Role.AC_LAND),
    ("demo_surveyor", Role.SURVEYOR),
    ("demo_citizen", Role.CITIZEN),
    ("demo_lawyer", Role.LAWYER),
]


class Command(BaseCommand):
    help = "Create demo users and fictional sample land records (development only)."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo runs only when DJANGO_DEBUG=true")
        if User.objects.filter(username="demo_officer").exists():
            raise CommandError("demo data already exists")

        users, passwords = {}, {}
        for username, role in ACCOUNTS:
            passwords[username] = secrets.token_urlsafe(12)
            users[username] = User.objects.create_user(
                username, email=f"{username}@example.com",
                password=passwords[username], role=role)

        officer = users["demo_officer"]
        rahim = Owner.register("কাল্পনিক রহিম", "1234567890", "নমুনা ঠিকানা")
        sumi = Owner.register("কাল্পনিক সুমি", "1234567893", "নমুনা ঠিকানা")
        common = dict(district="নমুনা জেলা", upazila="নমুনা উপজেলা", mouza="নমুনা মৌজা",
                      land_type=LandType.AGRICULTURAL)
        parcel1 = create_parcel_with_owner(
            actor=officer, owner=rahim, effective_date=datetime.date(2018, 3, 1),
            khatian_no="1245", dag_no="883", area_decimal=Decimal("33.00"), **common)
        parcel2 = create_parcel_with_owner(
            actor=officer, owner=sumi, effective_date=datetime.date(2019, 7, 15),
            khatian_no="1246", dag_no="884", area_decimal=Decimal("20.50"), **common)
        jamal = Owner.register("কাল্পনিক জামাল", "1234567894", "নমুনা ঠিকানা")
        transfer_ownership(
            actor=officer, parcel_id=parcel2.id, seller_id=sumi.id, buyer_id=jamal.id,
            expected_head=current_head(parcel2), kind="sale", ref="দলিল-নমুনা-০৭",
            effective_date=datetime.date(2023, 5, 10))
        app = submit_application(
            applicant=users["demo_citizen"], parcel_id=parcel1.id, kind="sale",
            deed_ref="দলিল-নমুনা-১", claimant_name="কাল্পনিক করিম", claimant_nid="1234567892")

        out = self.stdout.write
        out("\nডেমো অ্যাকাউন্ট (পাসওয়ার্ড শুধু এখন একবার দেখানো হচ্ছে, কোথাও সেভ করে রাখুন):")
        for username, _ in ACCOUNTS:
            out(f"  {username:15} {passwords[username]}")
        out(f"\nনমুনা জমি ১: খতিয়ান 1245, দাগ 883  (id: {parcel1.id})")
        out(f"নমুনা জমি ২: খতিয়ান 1246, দাগ 884  (id: {parcel2.id}), ইতিহাসে ২টি ধাপ")
        out(f"সার্ভেয়ারের অপেক্ষায় একটি নামজারি আবেদন: {app.code}")
