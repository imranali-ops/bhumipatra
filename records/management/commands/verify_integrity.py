"""python manage.py verify_integrity  -> exit code 1 if anything was tampered with."""
from django.core.management.base import BaseCommand, CommandError

from audit.services import verify_audit_log
from records.models import Parcel
from records.services import verify_parcel


class Command(BaseCommand):
    help = "Verify the audit log and every parcel's hash chain and signed checkpoints."

    def handle(self, *args, **options):
        problems = 0
        audit = verify_audit_log()
        if audit.ok:
            self.stdout.write(self.style.SUCCESS("audit log: OK"))
        else:
            problems += 1
            self.stderr.write(f"audit log: BROKEN at {audit.broken_at}: {audit.reason}")
        checked = 0
        for parcel in Parcel.objects.iterator():
            checked += 1
            result = verify_parcel(parcel)
            if not result.ok:
                problems += 1
                self.stderr.write(f"parcel {parcel.id}: BROKEN at {result.broken_at}: {result.reason}")
        self.stdout.write(f"parcels checked: {checked}")
        if problems:
            raise CommandError(f"{problems} integrity problem(s) found")
        self.stdout.write(self.style.SUCCESS("all records verified"))
