"""Give legacy CatalogSyncRun columns defaults so Django inserts succeed.

Production DB still has older NOT NULL columns (active_lock, checkpoint, …)
that the current model no longer maps. Without defaults, scheduled/manual
«ورود خودکار» fails with IntegrityError / TransactionManagementError.
"""

from django.db import migrations


LEGACY_DEFAULTS = (
    ("active_lock", "FALSE"),
    ("cancel_requested", "FALSE"),
    ("celery_task_id", "''"),
    ("checkpoint", "'{}'::jsonb"),
    ("current_page", "0"),
    ("dry_run", "FALSE"),
    ("last_error", "''"),
    ("max_items", "0"),
    ("retry_count", "0"),
)


def apply_defaults(apps, schema_editor):
    table = "catalog_catalogsyncrun"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            [table],
        )
        existing = {row[0] for row in cursor.fetchall()}
        for column, default_sql in LEGACY_DEFAULTS:
            if column not in existing:
                continue
            cursor.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default_sql}"
            )
            # Backfill any unexpected nulls before enforcing NOT NULL stays valid.
            if default_sql in {"FALSE", "0"}:
                cursor.execute(
                    f"UPDATE {table} SET {column} = {default_sql} WHERE {column} IS NULL"
                )
            elif default_sql == "''":
                cursor.execute(
                    f"UPDATE {table} SET {column} = '' WHERE {column} IS NULL"
                )
            elif "jsonb" in default_sql:
                cursor.execute(
                    f"UPDATE {table} SET {column} = '{{}}'::jsonb WHERE {column} IS NULL"
                )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0019_actor_director_original_name'),
    ]

    operations = [
        migrations.RunPython(apply_defaults, noop_reverse),
    ]
