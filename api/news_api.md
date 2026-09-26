# GovEase News API

Contract for the Government News & Updates module (Member 2).
Members 1 and 3 can code against this without reading the implementation.

- **Base URL (development):** `http://localhost:5000/api`
- **Format:** JSON, UTF-8
- **Auth:** none (prototype)
- **CORS:** open in development, so a frontend served from another port can call it

---

## Freshness behaviour (read this first)

`GET /api/news` **always returns immediately** from SQLite. It never waits on a
government source.

When the stored data is older than the freshness threshold (default 5 minutes),
the request starts a **background** refresh and still returns the current data
straight away. Newly collected items therefore appear on a **later** request,
not the one that triggered the refresh.

> The 5-minute interval is a **check interval, not a guarantee**. Whether an
> announcement appears depends on the department publishing it to its feed, the
> feed being reachable, and someone loading the page. Do not build anything that
> assumes an item will arrive within a fixed time.

`last_checked` in a response is the timestamp of the last completed
**source-check cycle** — not a claim about any individual item.

---

## Endpoints

### `GET /api/news`

List updates, newest first.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `category` | string | all | One of the categories below. `All` means no filter. |
| `search` | string | — | Substring match across `title`, `summary`, `tags`. |
| `department` | string | — | Substring match on department. |
| `state` | string | all | `Central` or `State`. |
| `importance` | string | — | `high`, `normal` or `low`. |
| `limit` | int | 20 | Clamped to 1–100. |
| `offset` | int | 0 | For paging. |
| `sort` | string | `balanced` | `balanced`, `latest`, or `importance`. |

**Sort modes**

- `balanced` (default) — round-robin across sources, so one prolific department
  cannot fill the whole page. Within each source, newest first.
- `latest` — strict reverse-chronological across all sources.
- `importance` — `high` first, then newest.

**Example**

```
GET /api/news?category=Schemes&state=Central&limit=2
```

```json
{
  "count": 2,
  "total": 4,
  "limit": 2,
  "offset": 0,
  "sort": "balanced",
  "last_checked": "2026-09-13T16:02:39+05:30",
  "refresh_state": "fresh",
  "results": [
    {
      "id": 216,
      "title": "Money Market Operations as on September 12, 2026",
      "summary": "(Amount in Rs crore, Rate in Per cent) MONEY MARKETS...",
      "content": "(Amount in Rs crore, Rate in Per cent) MONEY MARKETS...",
      "category": "Notifications",
      "department": "Reserve Bank of India",
      "published_date": "2026-09-15",
      "detected_at": "2026-09-15T12:01:45+05:30",
      "last_checked": "2026-09-15T12:18:37+05:30",
      "source_name": "Reserve Bank of India",
      "source_url": "https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=63591",
      "state_level": "Central",
      "importance": "normal",
      "tags": [],
      "deadline": null,
      "location": null,
      "image_url": null,
      "content_hash": "8f14e45fceea167a...",
      "data_origin": "feed",
      "is_official_source": true
    }
  ]
}
```

`refresh_state` is diagnostic only: `fresh`, `refresh started`,
`already refreshing`, or `no sources configured`.

---

### `GET /api/news/<id>`

One update. Returns the bare object (same fields as a `results` entry).

**404 response**

```json
{ "error": "not_found", "message": "No update with id 99999" }
```

---

### `GET /api/meta`

Everything needed to build filters without hardcoding them.

```json
{
  "last_checked": "2026-09-13T16:02:39+05:30",
  "last_cycle_new_items": 10,
  "freshness_minutes": 5,
  "freshness_note": "A check interval, not a guarantee that every government announcement appears within this window.",
  "categories": [{ "category": "Policies", "count": 24 }],
  "departments": [{ "department": "Securities and Exchange Board of India", "count": 15 }],
  "all_categories": ["Schemes", "Announcements", "..."],
  "state_levels": ["Central", "State"],
  "counts": { "feed": 92 },
  "has_cached_data": false,
  "has_feed_data": true,
  "sources": [
    {
      "name": "SEBI",
      "last_status": "200",
      "last_checked": "2026-09-13T16:02:39+05:30",
      "consecutive_failures": 0
    }
  ],
  "configured_sources": 5
}
```

---

### `POST /api/refresh`

Force a refresh cycle now. Still asynchronous — it returns immediately.
Rate-limited to once per minute.

```json
{ "status": "refresh started" }
```

**429 response**

```json
{ "status": "rate_limited", "retry_after_seconds": 42 }
```

---

### `GET /api/health`

```json
{ "status": "ok", "count": 83, "last_checked": "...", "configured_sources": 5 }
```

---

## Field reference

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Primary key. |
| `title` | string | Headline, HTML stripped. |
| `summary` | string | 2–3 line plain-text summary. Falls back to the title when the feed supplies none. |
| `content` | string | Longer plain-text body where the feed provides one. |
| `category` | string | One of the categories below. |
| `department` | string | Issuing ministry / body. |
| `published_date` | string | `YYYY-MM-DD`. The publish date. |
| `detected_at` | ISO 8601 | When GovEase **first saw** this item. |
| `last_checked` | ISO 8601 | When this item's source was **last polled**. |
| `source_name` | string | Short source label. |
| `source_url` | string \| null | Original notification URL. Present on every record currently served. |
| `state_level` | string | `Central` or `State`. |
| `importance` | string | `high`, `normal`, `low`. |
| `tags` | string[] | Always an array in JSON. |
| `deadline` | string \| null | `YYYY-MM-DD` where known. |
| `location` | string \| null | Optional. |
| `image_url` | string \| null | Optional; the frontend lazy-loads it. |
| `content_hash` | string | SHA-256 of title + URL. Deduplication key. |
| `data_origin` | string | `feed` (collected live) or `cached` (from the committed snapshot). Both are real government records. |
| `is_official_source` | bool | True only when `source_url` is on a confirmed government host. |

### `data_origin` and `is_official_source` — please respect these

**Every record is a real government item.** Nothing in this API is invented.
`data_origin` says only how fresh the copy is:

| Value | Meaning |
|---|---|
| `feed` | Collected live from an official feed during a refresh cycle. |
| `cached` | Loaded from the committed snapshot in `news/data/seed_news.json` — real records collected earlier, so possibly out of date. A cached row is promoted to `feed` automatically the next time a live cycle re-confirms it. |

`is_official_source` is independent of that, and drives the verified badge:

| Condition | How to present it |
|---|---|
| `is_official_source = true` | URL is on a confirmed government host (`*.gov.in`, `*.nic.in`, plus hand-checked `rbi.org.in` / `mygov.in`). Safe to show as verified; add "(cached)" when `data_origin` is `cached`. |
| `is_official_source = false` | Show the source name without a verified badge. Do not imply official standing. |

### Categories

`Schemes`, `Announcements`, `Policies`, `Notifications`, `Citizen Services`,
`Eligibility Updates`, `Deadlines`, `Education`, `Employment`, `Agriculture`,
`Health`, `Other`

---

## Adding your own module (Members 1 and 3)

The API is blueprint-per-module. Nothing in the news code needs to change.

1. Create `backend/routes/assistant.py` (Member 1) or
   `backend/routes/documents.py` (Member 3), following the shape of
   `backend/routes/news.py`.
2. Register it in `backend/app.py`:

```python
from backend.routes.assistant import assistant_bp
app.register_blueprint(assistant_bp, url_prefix="/api")
```

3. Keep your endpoints under your own path — `/api/assistant/...`,
   `/api/documents/...` — so the three modules never collide.

On the frontend, `window.GovEase` reserves `GovEase.assistant` and
`GovEase.docs` for you, and `index.html` has two mount points,
`#assistant-mount` and `#documents-mount`. Keep your own `fetch()` calls in your
own namespace rather than adding to `GovEase.api`, so the news module and yours
fail independently.
