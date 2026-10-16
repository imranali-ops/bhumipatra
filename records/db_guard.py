"""PostgreSQL triggers that make the ledger tables append-only even against
raw SQL (psql, a buggy script, a stolen app password). Installed after every
`migrate`; safe to run repeatedly."""
from django.db import connections

PROTECTED_TABLES = ("records_ownershipentry", "records_checkpoint", "audit_auditevent",
                    "mutations_mutationstep", "mutations_mutationdocument")

FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION forbid_ledger_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'append-only table ' || TG_TABLE_NAME || ': ' || TG_OP || ' is not allowed',
        ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
"""


def install_guards(sender=None, using="default", **kwargs):
    connection = connections[using]
    if connection.vendor != "postgresql":
        return
    existing = set(connection.introspection.table_names())
    with connection.cursor() as cursor:
        cursor.execute(FUNCTION_SQL)
        for table in PROTECTED_TABLES:
            if table not in existing:
                continue
            cursor.execute(f"DROP TRIGGER IF EXISTS ledger_no_change ON {table}")
            cursor.execute(
                f"CREATE TRIGGER ledger_no_change BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION forbid_ledger_change()")
            cursor.execute(f"DROP TRIGGER IF EXISTS ledger_no_truncate ON {table}")
            cursor.execute(
                f"CREATE TRIGGER ledger_no_truncate BEFORE TRUNCATE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION forbid_ledger_change()")
