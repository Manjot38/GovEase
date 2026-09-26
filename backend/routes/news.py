"""GovEase - news API blueprint.

Every endpoint here reads SQLite and returns immediately. The only contact
with the refresh machinery is one call to refresh_if_stale(), which never
blocks: it either does nothing or starts a background thread.

Members 1 and 3: copy this file's shape for your own blueprint
(routes/assistant.py, routes/documents.py) and register it in app.py. You do
not need to modify anything in here.
"""

import time

from flask import Blueprint, jsonify, request

from backend.database.db import get_conn, get_meta
from backend.models.news import CATEGORIES, IMPORTANCE_LEVELS, row_to_dict
from news.collector import FRESHNESS_MINUTES, refresh_if_stale
from news.sources import get_sources

news_bp = Blueprint("news", __name__)

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

# Cap for the balanced sort's working set. Bounds memory while being far
# larger than any page the prototype serves.
BALANCE_POOL = 300

# POST /api/refresh is a demo convenience, so it gets a simple floor to stop
# it being used to hammer the sources.
MANUAL_REFRESH_MIN_SECONDS = 60
_last_manual_refresh = 0.0


def _build_query(args):
    """Turn query params into a parameterized WHERE clause.

    Values only ever reach SQLite as bound parameters.
    """
    clauses = []
    params = []

    category = (args.get("category") or "").strip()
    if category and category.lower() != "all":
        clauses.append("category = ?")
        params.append(category)

    department = (args.get("department") or "").strip()
    if department:
        clauses.append("department LIKE ?")
        params.append("%" + department + "%")

    state = (args.get("state") or "").strip()
    if state and state.lower() != "all":
        clauses.append("state_level = ?")
        params.append(state)

    importance = (args.get("importance") or "").strip()
    if importance in IMPORTANCE_LEVELS:
        clauses.append("importance = ?")
        params.append(importance)

    search = (args.get("search") or "").strip()
    if search:
        clauses.append("(title LIKE ? OR summary LIKE ? OR tags LIKE ?)")
        term = "%" + search + "%"
        params.extend([term, term, term])

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _balance_by_source(rows):
    """Round-robin across sources, keeping each source's own date order.

    Without this, one prolific source swamps the page: SEBI alone publishes
    dozens of enforcement notices on a single day, which would push every
    other department off the front page. No row is dropped or reordered
    within its source - only the interleaving changes.
    """
    buckets = {}
    order = []
    for row in rows:
        key = row["source_name"] or ""
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(row)

    balanced = []
    index = 0
    while len(balanced) < len(rows):
        added = False
        for key in order:
            bucket = buckets[key]
            if index < len(bucket):
                balanced.append(bucket[index])
                added = True
        if not added:
            break
        index += 1
    return balanced


def _parse_int(raw, default, minimum, maximum):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


@news_bp.route("/news", methods=["GET"])
def list_news():
    # Non-blocking: returns "fresh", "already refreshing" or "refresh started".
    refresh_state = refresh_if_stale()

    where, params = _build_query(request.args)
    limit = _parse_int(request.args.get("limit"), DEFAULT_LIMIT, 1, MAX_LIMIT)
    offset = _parse_int(request.args.get("offset"), 0, 0, 1000000)

    # balanced (default) | latest | importance
    sort = (request.args.get("sort") or "balanced").lower()
    if sort == "importance":
        # Deterministic ordering: high first, then newest.
        order = (
            "ORDER BY CASE importance WHEN 'high' THEN 0 WHEN 'normal' THEN 1 "
            "ELSE 2 END, published_date DESC, id DESC"
        )
    else:
        order = "ORDER BY published_date DESC, id DESC"

    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM news" + where, params
        ).fetchone()["n"]

        if sort == "balanced":
            pool = conn.execute(
                "SELECT * FROM news" + where + " " + order + " LIMIT ?",
                params + [BALANCE_POOL],
            ).fetchall()
            rows = _balance_by_source(pool)[offset:offset + limit]
        else:
            rows = conn.execute(
                "SELECT * FROM news" + where + " " + order + " LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

    meta = get_meta()
    return jsonify({
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "last_checked": meta.get("last_checked"),
        "sort": sort,
        "refresh_state": refresh_state,
        "results": [row_to_dict(row) for row in rows],
    })


@news_bp.route("/news/<int:news_id>", methods=["GET"])
def get_news(news_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if row is None:
        return jsonify({"error": "not_found",
                        "message": "No update with id " + str(news_id)}), 404
    return jsonify(row_to_dict(row))


@news_bp.route("/meta", methods=["GET"])
def meta():
    """Everything the frontend needs to build filters without hardcoding them."""
    with get_conn() as conn:
        categories = conn.execute(
            "SELECT category, COUNT(*) AS count FROM news "
            "GROUP BY category ORDER BY count DESC"
        ).fetchall()
        departments = conn.execute(
            "SELECT department, COUNT(*) AS count FROM news "
            "GROUP BY department ORDER BY count DESC LIMIT 40"
        ).fetchall()
        origins = conn.execute(
            "SELECT data_origin, COUNT(*) AS count FROM news GROUP BY data_origin"
        ).fetchall()
        source_rows = conn.execute(
            "SELECT name, last_status, last_checked, consecutive_failures "
            "FROM sources ORDER BY name"
        ).fetchall()

    origin_counts = {row["data_origin"]: row["count"] for row in origins}
    meta_row = get_meta()

    return jsonify({
        "last_checked": meta_row.get("last_checked"),
        "last_cycle_new_items": meta_row.get("last_cycle_new_items", 0),
        "freshness_minutes": FRESHNESS_MINUTES,
        # Stated plainly so no caller mistakes the interval for a promise.
        "freshness_note": (
            "A check interval, not a guarantee that every government "
            "announcement appears within this window."
        ),
        "categories": [dict(row) for row in categories],
        "departments": [dict(row) for row in departments],
        "all_categories": CATEGORIES,
        "state_levels": ["Central", "State"],
        "counts": origin_counts,
        "has_cached_data": origin_counts.get("cached", 0) > 0,
        "has_feed_data": origin_counts.get("feed", 0) > 0,
        "sources": [dict(row) for row in source_rows],
        "configured_sources": len(get_sources()),
    })


@news_bp.route("/refresh", methods=["POST"])
def manual_refresh():
    """Force a refresh, for demos. Still asynchronous, still rate-limited."""
    global _last_manual_refresh
    elapsed = time.monotonic() - _last_manual_refresh
    if elapsed < MANUAL_REFRESH_MIN_SECONDS:
        return jsonify({
            "status": "rate_limited",
            "retry_after_seconds": int(MANUAL_REFRESH_MIN_SECONDS - elapsed),
        }), 429
    _last_manual_refresh = time.monotonic()
    return jsonify({"status": refresh_if_stale(force=True)})


@news_bp.route("/health", methods=["GET"])
def health():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM news").fetchone()["n"]
    return jsonify({
        "status": "ok",
        "count": count,
        "last_checked": get_meta().get("last_checked"),
        "configured_sources": len(get_sources()),
    })
