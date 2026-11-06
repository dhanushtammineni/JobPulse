"""Forward-only SQL migrations: python -m jobpulse.database.migrate [upgrade|check]."""
import argparse
from hashlib import sha256
from pathlib import Path

import psycopg2
from .connections import connect_db

MIGRATIONS = Path(__file__).with_name('migrations')
LOCK_ID = 487296103


class MigrationError(RuntimeError):
    pass


def migration_files(directory=MIGRATIONS):
    files = sorted(Path(directory).glob('[0-9][0-9][0-9]_*.sql'))
    if not files or len({p.name[:3] for p in files}) != len(files):
        raise MigrationError('Migration files are missing or have duplicate versions')
    return [(p.name, sha256(p.read_bytes()).hexdigest(), p.read_text()) for p in files]


def _validate_history(cursor, files):
    cursor.execute('SELECT version, checksum FROM public.schema_migrations ORDER BY version')
    applied = cursor.fetchall()
    expected = [(name, checksum) for name, checksum, _ in files]
    if applied != expected[:len(applied)]:
        raise MigrationError('Migration history differs from this release; restore its original migration files')
    return len(applied)


def upgrade(connection=None, directory=MIGRATIONS):
    """Apply pending SQL and history atomically under a database-wide lock.

    Caller-supplied connections are not closed. SQL must not manage transactions.
    """
    files = migration_files(directory)
    owns_connection = connection is None
    connection = connection if connection is not None else connect_db()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '30s'")
                cursor.execute("SET LOCAL statement_timeout = '120s'")
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
                cursor.execute('''CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    version TEXT PRIMARY KEY, checksum CHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
                applied = _validate_history(cursor, files)
                for name, checksum, sql in files[applied:]:
                    cursor.execute(sql)
                    cursor.execute('INSERT INTO public.schema_migrations (version, checksum) VALUES (%s, %s)',
                                   (name, checksum))
        return [name for name, _, _ in files[applied:]]
    finally:
        if owns_connection:
            connection.close()


def assert_current(connection=None, directory=MIGRATIONS):
    """Read-only startup/readiness check; never implicitly bootstrap a database."""
    files = migration_files(directory)
    owns_connection = connection is None
    connection = connection if connection is not None else connect_db()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.schema_migrations')")
                if cursor.fetchone()[0] is None:
                    raise MigrationError('Database is not initialized; run python -m jobpulse.database.migrate upgrade')
                if _validate_history(cursor, files) != len(files):
                    raise MigrationError('Database migrations are pending; run python -m jobpulse.database.migrate upgrade')
                cursor.execute('''SELECT j.id, j.source, j.first_seen_at, j.last_seen_at,
                    j.is_active, j.source_job_id, j.description, j.employment_type, j.salary,
                    a.experience_years, e.embedding, r.id, re.embedding
                    FROM jobs j
                    LEFT JOIN job_ai_enrichment a ON a.job_id = j.id
                    LEFT JOIN job_embeddings e ON e.job_id = j.id
                    CROSS JOIN resume_profiles r
                    LEFT JOIN resume_embeddings re ON re.resume_id = r.id LIMIT 0''')
    finally:
        if owns_connection:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['upgrade', 'check'], nargs='?', default='upgrade')
    args = parser.parse_args()
    try:
        if args.command == 'check':
            assert_current()
            print('Database schema is current')
        else:
            applied = upgrade()
            print('Applied: ' + (', '.join(applied) if applied else 'none (already current)'))
    except (MigrationError, psycopg2.Error, ValueError) as error:
        # DB exceptions can include SQL parameters; do not log their contents.
        message = str(error) if isinstance(error, (MigrationError, ValueError)) else type(error).__name__
        parser.exit(1, 'Migration failed: ' + message + '\n')


if __name__ == '__main__':
    main()
