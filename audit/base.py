from django.db import models


class ImmutableRecordError(Exception):
    """Raised on any attempt to change or delete an append-only record."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableRecordError("append-only records cannot be updated")

    def bulk_update(self, *args, **kwargs):
        raise ImmutableRecordError("append-only records cannot be updated")

    def delete(self):
        raise ImmutableRecordError("append-only records cannot be deleted")


class AppendOnlyModel(models.Model):
    """Application-level guard. The PostgreSQL trigger installed by
    records/db_guard.py enforces the same rule against raw SQL."""
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableRecordError("append-only records cannot be modified")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError("append-only records cannot be deleted")
