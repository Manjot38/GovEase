"""GovEase - SQLite access and schema.

Three tables:
  news    - the updates themselves
  meta    - ONE row holding the single global freshness timestamp
  sources - per-source *state* (etag / failure counter), never a timer

The freshness gate reads meta only. Sources hold no schedule of their own,
which is what keeps the check global and O(1) as required by spec section 25.
"""

import os
import sqlite3

DB_PATH = os.environ.get(
    "GOVEASE_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "govease.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    summary         TEXT,
    content         TEXT,
    category        TEXT,
    department      TEXT,
    published_date  TEXT,
    detected_at     TEXT,
    last_checked    TEXT,
    source_name     TEXT,
    source_url      TEXT,
    state_level     TEXT,
    importance      TEXT,
    tags            TEXT,
    deadline        TEXT,
    location        TEXT,
    image_url       TEXT,
    content_hash    TEXT UNIQUE,
    data_origin     TEXT DEFAULT 'feed'
);

CREATE INDEX IF NOT EXISTS idx_news_published ON news (published_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_category  ON news (category);
CREATE INDEX IF NOT EXISTS idx_news_origin    ON news (data_origin);

-- Exactly one row, id = 1. The global freshness record.
CREATE TABLE IF NOT EXISTS meta (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    last_checked         TEXT,
    last_cycle_status    TEXT,
    last_cycle_new_items INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sources (
    name                 TEXT PRIMARY KEY,
    url                  TEXT,
    etag                 TEXT,
    last_modified        TEXT,
    last_status          TEXT,
    last_checked         TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    skip_cycles          INTEGER DEFAULT 0
);
"""


def get_conn():
    """Connection with dict-style rows and sane concurrency settings."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL lets the background refresh thread write while requests read.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    """Create tables if absent and guarantee the single meta row. Idempotent."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta (id, last_checked) VALUES (1, NULL)")
    return DB_PATH


def get_meta():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM meta WHERE id = 1").fetchone()
    return dict(row) if row else {}


def news_count():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM news").fetchone()["n"]
