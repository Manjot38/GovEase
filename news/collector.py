"""GovEase - government source collector.

Design contract (spec section 25):

    GET /api/news
       -> refresh_if_stale()      ONE global check, O(1), reads meta.last_checked
            |
            +-- fresh  -> return at once, zero network work
            +-- stale  -> try non-blocking lock
                           +-- busy     -> return at once
                           +-- acquired -> spawn daemon thread, return at once
       -> SELECT from SQLite -> respond        ALWAYS immediate

Nothing in this module ever blocks a web request. refresh_if_stale() does one
timestamp comparison and, at most, starts a thread. There is deliberately no
blocking mode and no switch to add one.

This is not a crawler. It reads a handful of official RSS feeds, politely,
only when the data has gone stale and only when somebody is actually looking.
"""

import argparse
import io
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from html import unescape

import feedparser
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.db import get_conn, init_db  # noqa: E402
from backend.models.news import (  # noqa: E402
    DEFAULT_IMPORTANCE,
    categorize,
    make_content_hash,
)
from news.sources import get_sources  # noqa: E402

# --- Tunables ---------------------------------------------------------------

FRESHNESS_MINUTES = int(os.environ.get("GOVEASE_FRESHNESS_MINUTES", 5))
BACKGROUND_INTERVAL_MINUTES = int(os.environ.get("GOVEASE_BACKGROUND_INTERVAL", 10))
MAX_ITEMS_PER_SOURCE = int(os.environ.get("GOVEASE_MAX_ITEMS", 15))
RETENTION_DAYS = int(os.environ.get("GOVEASE_RETENTION_DAYS", 120))
CYCLE_BUDGET_SECONDS = int(os.environ.get("GOVEASE_CYCLE_BUDGET", 25))

CONNECT_TIMEOUT = 3
READ_TIMEOUT = 5
DELAY_BETWEEN_SOURCES = 0.5

# After this many consecutive failures a source is rested for SKIP_CYCLES
# cycles. A counter, not a timer - the freshness check stays global.
FAILURE_THRESHOLD = 3
SKIP_CYCLES = 5

USER_AGENT = "GovEase/0.1 (student academic project; reads public government RSS feeds)"

SEED_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "seed_news.json"
)

_refresh_lock = threading.Lock()
_background_thread = None


def log(message):
    print("[collector] " + str(message), flush=True)


# --- Text cleaning ----------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw, max_chars=320):
    """Feed summaries arrive as HTML tables and Drupal markup. Flatten them.

    Returns plain text truncated at a word boundary - roughly the 2-3 lines
    the spec asks for.
    """
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" .,;:") + "..."


# --- Date parsing -----------------------------------------------------------

# The verified feeds use three different shapes, and two of them do not
# survive feedparser's own parser:
#   MyGov / TRAI / NITI : RFC822 with timezone -> published_parsed works
#   RBI                 : "Fri, 11 Sep 2026 21:40:00"   (no timezone)
#   SEBI                : "11 Sep, 2026 +0530"
_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S",
    "%d %b, %Y %z",
    "%d %b, %Y",
    "%d %B %Y",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def parse_date(entry):
    """Best-effort publish date as YYYY-MM-DD, or None if truly absent."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6]).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
    for key in ("published", "updated", "pubDate"):
        raw = (entry.get(key) or "").strip()
        if not raw:
            continue
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --- Source state -----------------------------------------------------------

def _load_source_state(conn, name):
    row = conn.execute("SELECT * FROM sources WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else {}


def _save_source_state(conn, name, url, **fields):
    conn.execute("INSERT OR IGNORE INTO sources (name, url) VALUES (?, ?)", (name, url))
    if fields:
        assignments = ", ".join(key + " = ?" for key in fields)
        conn.execute(
            "UPDATE sources SET " + assignments + " WHERE name = ?",
            tuple(fields.values()) + (name,),
        )


# --- Fetch one source -------------------------------------------------------

def fetch_source(source, state):
    """Fetch and parse one feed, returning (entries, info).

    Any failure here is local to this source: the caller keeps going.
    """
    headers = {"User-Agent": USER_AGENT}
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]

    response = requests.get(
        source["url"],
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        headers=headers,
    )

    info = {
        "status": str(response.status_code),
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
    }

    if response.status_code == 304:
        info["status"] = "304 not modified"
        return [], info

    if response.status_code != 200:
        raise RuntimeError("HTTP " + str(response.status_code))

    parsed = feedparser.parse(response.content)
    if not parsed.entries:
        raise RuntimeError("no entries in feed")

    return parsed.entries[:MAX_ITEMS_PER_SOURCE], info


def build_record(entry, source, checked_at):
    """Feed entry -> news row. Returns None if the entry is unusable."""
    title = clean_text(entry.get("title", ""), max_chars=300)
    link = (entry.get("link") or "").strip()
    if not title or not link:
        return None

    raw_summary = entry.get("summary") or entry.get("description") or ""
    summary = clean_text(raw_summary)
    # PIB publishes titles with no summary at all - fall back to the title
    # rather than rendering an empty card.
    if not summary:
        summary = title

    return {
        "title": title,
        "summary": summary,
        "content": clean_text(raw_summary, max_chars=4000) or title,
        "category": categorize(title, summary, source.get("default_category")),
        "department": source.get("department", source["name"]),
        "published_date": parse_date(entry) or checked_at[:10],
        "detected_at": checked_at,
        "last_checked": checked_at,
        "source_name": source["name"],
        "source_url": link,
        "state_level": source.get("state_level", "Central"),
        "importance": DEFAULT_IMPORTANCE,
        "tags": "",
        "deadline": None,
        "location": None,
        "image_url": None,
        "content_hash": make_content_hash(title, link),
        "data_origin": "feed",
    }


INSERT_SQL = """
INSERT OR IGNORE INTO news (
    title, summary, content, category, department, published_date,
    detected_at, last_checked, source_name, source_url, state_level,
    importance, tags, deadline, location, image_url, content_hash, data_origin
) VALUES (
    :title, :summary, :content, :category, :department, :published_date,
    :detected_at, :last_checked, :source_name, :source_url, :state_level,
    :importance, :tags, :deadline, :location, :image_url, :content_hash, :data_origin
)
"""


# --- The refresh cycle ------------------------------------------------------

def run_cycle():
    """One pass over every source. Safe to call from the CLI or a thread."""
    init_db()
    started = time.monotonic()
    checked_at = now_iso()
    total_new = 0
    outcomes = []

    for source in get_sources():
        if time.monotonic() - started > CYCLE_BUDGET_SECONDS:
            log("cycle budget reached; skipping " + source["name"] + " and the rest")
            outcomes.append(source["name"] + ": skipped (budget)")
            continue

        with get_conn() as conn:
            state = _load_source_state(conn, source["name"])

        # Resting a repeatedly failing source. Counter, not clock.
        if state.get("skip_cycles", 0) > 0:
            remaining = state["skip_cycles"] - 1
            with get_conn() as conn:
                _save_source_state(
                    conn, source["name"], source["url"], skip_cycles=remaining
                )
            log(source["name"] + ": resting (" + str(remaining) + " cycles left)")
            outcomes.append(source["name"] + ": resting")
            continue

        try:
            entries, info = fetch_source(source, state)
        except Exception as exc:
            failures = state.get("consecutive_failures", 0) + 1
            skip = SKIP_CYCLES if failures >= FAILURE_THRESHOLD else 0
            with get_conn() as conn:
                _save_source_state(
                    conn,
                    source["name"],
                    source["url"],
                    last_status=type(exc).__name__ + ": " + str(exc)[:80],
                    last_checked=checked_at,
                    consecutive_failures=failures,
                    skip_cycles=skip,
                )
            log(source["name"] + ": FAILED (" + type(exc).__name__ + ") - others continue")
            outcomes.append(source["name"] + ": failed")
            time.sleep(DELAY_BETWEEN_SOURCES)
            continue

        new_here = 0
        with get_conn() as conn:
            for entry in entries:
                record = build_record(entry, source, checked_at)
                if record is None:
                    continue
                cursor = conn.execute(INSERT_SQL, record)
                if cursor.rowcount:
                    new_here += 1
                else:
                    # Already known - refresh its last_checked stamp, and
                    # promote a snapshot row now confirmed live.
                    conn.execute(
                        "UPDATE news SET last_checked = ?, data_origin = 'feed' "
                        "WHERE content_hash = ?",
                        (checked_at, record["content_hash"]),
                    )
            _save_source_state(
                conn,
                source["name"],
                source["url"],
                etag=info.get("etag"),
                last_modified=info.get("last_modified"),
                last_status=info["status"],
                last_checked=checked_at,
                consecutive_failures=0,
                skip_cycles=0,
            )

        total_new += new_here
        log(
            source["name"] + ": " + info["status"] + ", "
            + str(len(entries)) + " seen, " + str(new_here) + " new"
        )
        outcomes.append(source["name"] + ": " + str(new_here) + " new")
        time.sleep(DELAY_BETWEEN_SOURCES)

    prune_old()

    with get_conn() as conn:
        conn.execute(
            "UPDATE meta SET last_checked = ?, last_cycle_status = ?, "
            "last_cycle_new_items = ? WHERE id = 1",
            (checked_at, "; ".join(outcomes)[:500], total_new),
        )

    log("cycle done in %.1fs, %d new items" % (time.monotonic() - started, total_new))
    return total_new


def prune_old():
    """Keep the DB a feed, not an archive. Cached snapshot rows are spared."""
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM news WHERE data_origin = 'feed' AND published_date < ?",
            (cutoff,),
        )
        if cursor.rowcount:
            log("pruned " + str(cursor.rowcount) + " items older than "
                + str(RETENTION_DAYS) + " days")


# --- The freshness gate (called on every /api/news request) ------------------

def is_stale():
    """One global check. No per-source logic, no network, one row read."""
    with get_conn() as conn:
        row = conn.execute("SELECT last_checked FROM meta WHERE id = 1").fetchone()
    if not row or not row["last_checked"]:
        return True
    try:
        last = datetime.fromisoformat(row["last_checked"])
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - last.astimezone(timezone.utc)
    return age > timedelta(minutes=FRESHNESS_MINUTES)


def _threaded_cycle():
    try:
        run_cycle()
    except Exception as exc:
        log("background cycle error: " + type(exc).__name__ + ": " + str(exc))
    finally:
        _refresh_lock.release()


def refresh_if_stale(force=False):
    """Non-blocking. Returns what it decided, never the cycle's results.

    This is the only function the request path calls. It must stay cheap.
    """
    if not get_sources():
        return "no sources configured"
    if not force and not is_stale():
        return "fresh"
    if not _refresh_lock.acquire(blocking=False):
        return "already refreshing"
    thread = threading.Thread(
        target=_threaded_cycle, daemon=True, name="govease-refresh"
    )
    thread.start()
    return "refresh started"


# --- Optional background scheduler (OFF unless env var is set) --------------

def start_background_refresh():
    """Enabled only by GOVEASE_BACKGROUND_REFRESH=1. Off by default."""
    global _background_thread
    if os.environ.get("GOVEASE_BACKGROUND_REFRESH") != "1":
        return False
    # Flask's debug reloader imports this module twice; only the child
    # process should own the thread.
    if os.environ.get("FLASK_DEBUG") == "1" and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    if _background_thread is not None and _background_thread.is_alive():
        return False

    def loop():
        log("background refresh on, every "
            + str(BACKGROUND_INTERVAL_MINUTES) + " min")
        while True:
            time.sleep(BACKGROUND_INTERVAL_MINUTES * 60)
            try:
                refresh_if_stale()
            except Exception as exc:
                log("background loop error: " + str(exc))

    _background_thread = threading.Thread(
        target=loop, daemon=True, name="govease-background"
    )
    _background_thread.start()
    return True


# --- Seed fallback ----------------------------------------------------------

def load_seed():
    """Load the committed cached snapshot.

    The snapshot holds REAL records previously collected from the official
    feeds, complete with their original source URLs. It exists so a fresh
    install, or one with no network, still has genuine government updates to
    serve. Rows land with data_origin='cached' so the interface can say the
    data is a snapshot that may be out of date - it never invents content.

    Regenerate it from a populated database with:
        python -m news.collector --export-snapshot
    """
    init_db()
    if not os.path.exists(SEED_PATH):
        log("no seed file at " + SEED_PATH)
        return 0
    with io.open(SEED_PATH, encoding="utf-8") as handle:
        items = json.load(handle)

    stamp = now_iso()
    inserted = 0
    with get_conn() as conn:
        for item in items:
            tags = item.get("tags") or ""
            if isinstance(tags, list):
                tags = ",".join(tags)
            title = item.get("title", "")
            record = {
                "title": title,
                "summary": item.get("summary", ""),
                "content": item.get("content", ""),
                "category": item.get("category", "Other"),
                "department": item.get("department", ""),
                "published_date": item.get("published_date"),
                "detected_at": stamp,
                "last_checked": stamp,
                "source_name": item.get("source_name", "Cached snapshot"),
                "source_url": item.get("source_url"),
                "state_level": item.get("state_level", "Central"),
                "importance": item.get("importance", DEFAULT_IMPORTANCE),
                "tags": tags,
                "deadline": item.get("deadline"),
                "location": item.get("location"),
                "image_url": item.get("image_url"),
                # Same identity rule as a live row, so a snapshot record and
                # the live record it came from deduplicate against each other.
                "content_hash": make_content_hash(title, item.get("source_url") or ""),
                "data_origin": "cached",
            }
            if conn.execute(INSERT_SQL, record).rowcount:
                inserted += 1
    log("snapshot: " + str(inserted) + " cached records inserted ("
        + str(len(items)) + " in file)")
    return inserted


def export_snapshot(per_source=4):
    """Write the committed cached snapshot from real rows already collected.

    Takes the newest items per source, round-robin so every source is
    represented, and keeps only records whose URL is on a confirmed
    government host. Nothing is invented: if the database has no feed rows,
    the snapshot is not touched.
    """
    from backend.models.news import is_official_source

    init_db()
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM news WHERE data_origin IN ('feed','cached') "
            "ORDER BY published_date DESC, id DESC"
        )]

    if not rows:
        log("no collected rows to export; snapshot left unchanged")
        return 0

    buckets = {}
    order = []
    for row in rows:
        key = row["source_name"] or ""
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(row)

    picked = []
    for index in range(per_source):
        for key in order:
            if index < len(buckets[key]):
                picked.append(buckets[key][index])

    out = []
    for row in picked:
        if not is_official_source(row["source_url"]):
            continue
        tags = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
        out.append({
            "title": row["title"],
            "summary": row["summary"],
            "content": row["content"],
            "category": row["category"],
            "department": row["department"],
            "published_date": row["published_date"],
            "source_name": row["source_name"],
            "source_url": row["source_url"],
            "state_level": row["state_level"],
            "importance": row["importance"],
            "tags": tags,
            "deadline": row["deadline"],
            "location": row["location"],
            "image_url": row["image_url"],
        })

    with io.open(SEED_PATH, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, ensure_ascii=False)
        handle.write(chr(10))

    log("snapshot exported: " + str(len(out)) + " real records -> " + SEED_PATH)
    return len(out)


# --- CLI --------------------------------------------------------------------

def print_status():
    init_db()
    with get_conn() as conn:
        meta = conn.execute("SELECT * FROM meta WHERE id = 1").fetchone()
        rows = conn.execute("SELECT * FROM sources ORDER BY name").fetchall()
        counts = conn.execute(
            "SELECT data_origin, COUNT(*) AS n FROM news GROUP BY data_origin"
        ).fetchall()

    print("Global freshness (the only gate):")
    print("  last_checked        : " + str(meta["last_checked"] or "never"))
    print("  last cycle new items: " + str(meta["last_cycle_new_items"]))
    print("  stale right now     : " + str(is_stale()))
    print("")
    print("Rows by origin:")
    for row in counts:
        print("  %-8s %d" % (row["data_origin"], row["n"]))
    print("")
    print("Per-source state (state only - no timers):")
    for row in rows:
        print("  %-28s %-34s fails=%s rest=%s" % (
            row["name"],
            str(row["last_status"])[:34],
            row["consecutive_failures"],
            row["skip_cycles"],
        ))


def main():
    parser = argparse.ArgumentParser(description="GovEase government news collector")
    parser.add_argument("--seed", action="store_true",
                        help="load the committed cached snapshot")
    parser.add_argument("--refresh", action="store_true",
                        help="run one collection cycle now")
    parser.add_argument("--force", action="store_true",
                        help="with --refresh, ignore the freshness gate")
    parser.add_argument("--status", action="store_true",
                        help="show freshness and source health")
    parser.add_argument("--export-snapshot", action="store_true",
                        dest="export_snapshot",
                        help="regenerate the cached snapshot from collected rows")
    args = parser.parse_args()

    if args.export_snapshot:
        export_snapshot()
    elif args.seed:
        load_seed()
    elif args.refresh:
        if not args.force and not is_stale():
            log("data is fresh, skipping (no network calls made)")
        else:
            run_cycle()
    elif args.status:
        print_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    main()
