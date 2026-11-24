
"""GovEase - PostgreSQL database access for Supabase."""

import os
import re
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def _translate_sql(sql):
    """Translate the small amount of SQLite syntax used by GovEase."""

    ignore_insert = bool(
        re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO", sql, re.IGNORECASE)
    )

    if ignore_insert:
        sql = re.sub(
            r"INSERT\s+OR\s+IGNORE\s+INTO",
            "INSERT INTO",
            sql,
            count=1,
            flags=re.IGNORECASE,
        )

    # Convert named parameters such as :title to psycopg %(title)s.
    sql = re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql)

    # Convert positional SQLite placeholders to PostgreSQL placeholders.
    sql = sql.replace("?", "%s")

    if ignore_insert:
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    return sql


class DatabaseConnection:
    """Small compatibility layer for the existing SQLite-style code."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=None):
        translated = _translate_sql(sql)

        if params is None:
            return self.connection.execute(translated)

        return self.connection.execute(translated, params)


@contextmanager
def get_conn():
    """Open a PostgreSQL connection and close it after each operation."""

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing. Add your Supabase connection string "
            "to the environment variables."
        )

    connection = psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=10,
        sslmode="require",
    )

    try:
        yield DatabaseConnection(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    """Create the GovEase tables and indexes if they do not exist."""

    statements = [
        """
        CREATE TABLE IF NOT EXISTS news (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            content TEXT,
            category TEXT,
            department TEXT,
            published_date TEXT,
            detected_at TEXT,
            last_checked TEXT,
            source_name TEXT,
            source_url TEXT,
            state_level TEXT,
            importance TEXT,
            tags TEXT,
            deadline TEXT,
            location TEXT,
            image_url TEXT,
            content_hash TEXT UNIQUE,
            data_origin TEXT DEFAULT 'feed'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS meta (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            last_checked TEXT,
            last_cycle_status TEXT,
            last_cycle_new_items INTEGER DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sources (
            name TEXT PRIMARY KEY,
            url TEXT,
            etag TEXT,
            last_modified TEXT,
            last_status TEXT,
            last_checked TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            skip_cycles INTEGER DEFAULT 0
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_news_published
        ON news (published_date DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_news_category
        ON news (category)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_news_origin
        ON news (data_origin)
        """,
    ]

    with get_conn() as conn:
        for statement in statements:
            conn.execute(statement)

        conn.execute(
            "INSERT INTO meta (id, last_checked) VALUES (1, NULL) "
            "ON CONFLICT (id) DO NOTHING"
        )

    return "Supabase PostgreSQL"


def get_meta():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM meta WHERE id = 1"
        ).fetchone()

    return dict(row) if row else {}


def news_count():
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM news"
        ).fetchone()["n"]
