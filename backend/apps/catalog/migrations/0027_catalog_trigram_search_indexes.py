from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('catalog', '0026_align_catalog_title_labels'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "SET statement_timeout = 0;",
                "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_movie_title_trgm_idx ON catalog_movie USING gin (upper(title) gin_trgm_ops) WHERE is_published;",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_movie_original_trgm_idx ON catalog_movie USING gin (upper(original_title) gin_trgm_ops) WHERE is_published;",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_movie_slug_trgm_idx ON catalog_movie USING gin (upper(slug) gin_trgm_ops) WHERE is_published;",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_series_title_trgm_idx ON catalog_series USING gin (upper(title) gin_trgm_ops) WHERE is_published;",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_series_original_trgm_idx ON catalog_series USING gin (upper(original_title) gin_trgm_ops) WHERE is_published;",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_series_slug_trgm_idx ON catalog_series USING gin (upper(slug) gin_trgm_ops) WHERE is_published;",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_actor_name_trgm_idx ON catalog_actor USING gin (upper(name) gin_trgm_ops);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_actor_original_trgm_idx ON catalog_actor USING gin (upper(original_name) gin_trgm_ops);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_director_name_trgm_idx ON catalog_director USING gin (upper(name) gin_trgm_ops);",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS catalog_director_original_trgm_idx ON catalog_director USING gin (upper(original_name) gin_trgm_ops);",
                "RESET statement_timeout;",
            ],
            reverse_sql=[
                "SET statement_timeout = 0;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_director_original_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_director_name_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_actor_original_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_actor_name_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_series_slug_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_series_original_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_series_title_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_movie_slug_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_movie_original_trgm_idx;",
                "DROP INDEX CONCURRENTLY IF EXISTS catalog_movie_title_trgm_idx;",
                "RESET statement_timeout;",
            ],
        ),
    ]
