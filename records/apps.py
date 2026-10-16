from django.apps import AppConfig
from django.db.models.signals import post_migrate


class RecordsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "records"

    def ready(self):
        from .db_guard import install_guards
        post_migrate.connect(install_guards, sender=self,
                             dispatch_uid="records.install_ledger_guards")
