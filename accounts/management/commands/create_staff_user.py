"""python manage.py create_staff_user --username officer_x --role ac_land

Creates an officer/administrator account from the command line (the public
sign-up can only create citizens). The password is read from the STAFF_PASSWORD
environment variable or asked for without echo, never given on the command line."""
import os
from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Role, User


class Command(BaseCommand):
    help = "Create an officer, surveyor, lawyer or admin account."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--role", required=True, choices=[r.value for r in Role if r != Role.CITIZEN])
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        username = options["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError("this username already exists")
        password = os.environ.get("STAFF_PASSWORD") or getpass("Password: ")
        user = User(username=username, email=options["email"], role=options["role"])
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))
        User.objects.create_user(username=username, email=options["email"],
                                 password=password, role=options["role"])
        self.stdout.write(self.style.SUCCESS(f"created {options['role']} account '{username}'"))
