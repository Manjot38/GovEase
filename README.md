# GovEase — Government News & Updates 

A government information portal that collects updates from official RSS feeds,
cleans and categorises them, stores them in SQLite, serves them over a small
Flask API, and displays them in a newspaper-style interface that always links
back to the issuing department.

    Official source → Collect → Clean → Categorise → Deduplicate → Store → API → Frontend

This repository contains **Member 2's** Government Updates module and a
functional Groq-powered chatbot for the Member 1 AI Assistant integration.
Member 3's Smart Document & Form tool (`documents.html`, `/api/documents`)
resizes, compresses, converts and merges files for online applications — see
[Documents & Forms](#documents--forms-member-3).

---

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python -m news.collector --seed
```

```bash
python -m news.collector --refresh
```

```bash
python -m backend.app
```

Then open <http://localhost:5000>.

The first command loads the bundled cached snapshot so the app has content even
with no network, the second collects live updates from the official feeds, and
the third serves both the API and the frontend from one process.

The Groq API key is read by the backend from the project-root `.env` file.
Copy the supplied `api/grok_api.env` to `.env` before starting the app. The
backend accepts its existing `GROK_API_KEY` variable name and the standard
`GROQ_API_KEY` name (recommended for new setups). Both files are excluded from
Git.

The floating GovEase Assistant sends questions to `POST /api/chat`; the Flask
backend calls Groq using the `openai/gpt-oss-20b` model. The assistant does not
query the live news database, so verify important government details with the
relevant official source.

---

## Project structure

```
F:\Major Project\
├── frontend/
│   ├── index.html          Home, updates strip, Member 1/3 mount points
│   ├── news.html           Government Updates: featured + cards + compact list
│   ├── news-detail.html    Single update (?id=...)
│   ├── styles.css          All styling. No framework, no icon pack, no web fonts.
│   ├── documents.html      Documents & Forms: five file tools
│   ├── script.js           GovEase namespace: news API client + renderers
│   ├── documents.js        GovEase.docs: document tool UI + homepage quick links
│   ├── documents.css       Document tool styles (built on styles.css tokens)
│   └── chatbot.js          Floating Groq chatbot UI
├── backend/
│   ├── app.py              Flask app, CORS, static serving, background bootstrap
│   ├── routes/news.py      Government Updates API
│   ├── routes/chat.py      POST /api/chat
│   ├── routes/documents.py Document tool API (/api/documents)
│   ├── documents/processor.py  Image/PDF processing (in memory, no Flask)
│   ├── documents/presets.py    Application presets  ← add form requirements here
│   ├── models/news.py      Categories, hashing, serialization, government-host check
│   └── database/db.py      SQLite schema and connections (govease.db is generated)
├── news/
│   ├── sources.py          Registry of verified official feeds  ← add sources here
│   ├── collector.py        Fetch → clean → categorise → dedup → store; freshness gate
│   └── data/seed_news.json Cached snapshot of real records (offline fallback)
├── api/news_api.md         API contract for Members 1 and 3
├── api/documents_api.md    Document tool API contract
├── tests/test_documents.py Document tool test cases (pytest)
├── requirements.txt        Flask, flask-cors, requests, feedparser, python-dotenv,
│                           Pillow, pypdf, pypdfium2
└── GovEase_Member_2_News_Module.md   The specification
```

`backend/database/govease.db` is generated at runtime. Exclude it from version
control (add `*.db`, `*.db-wal`, `*.db-shm` to `.gitignore` when the repo is
initialised).

---

## How updates stay fresh

There is **no 24/7 crawler**. Freshness is demand-driven, with one global check:

```
GET /api/news
   → is the stored data older than FRESHNESS_MINUTES?
        no  → serve SQLite immediately, zero network work
        yes → start a background refresh, serve SQLite immediately anyway
```

Key properties:

- **The page never waits on a government server.** `/api/news` returns in
  milliseconds even when a refresh is running. New items appear on a later load.
- **One global freshness check**, stored in the `meta` table — not a timer per
  source and not a check per request.
- **No stampede.** A non-blocking lock means ten simultaneous requests trigger
  at most one refresh.
- **Polite collection.** Stored `ETag` / `Last-Modified` headers are replayed, so
  an unchanged feed costs a single `304` with no body. Each source gets a short
  timeout (3s connect, 5s read), the whole cycle is capped at 25 seconds, and a
  source that fails three times in a row is rested for five cycles.
- **Bounded storage.** At most 15 items per source per cycle, and items older
  than 120 days are pruned. This is a feed, not an archive.

### Optional background scheduler

Off by default. Enable only for a continuously running deployment:

```bash
GOVEASE_BACKGROUND_REFRESH=1 python -m backend.app
```

It re-runs the same check every 10 minutes.

### What "Last checked" means

The interface says **"Last checked N minutes ago"** and nothing stronger.

A 5-minute interval is a *check interval, not a guarantee*. Whether an
announcement appears depends on the department publishing it to its feed, the
feed being reachable, and someone loading the page. The UI never claims
otherwise.

### Tuning

All via environment variables:

| Variable | Default | Effect |
|---|---|---|
| `GOVEASE_FRESHNESS_MINUTES` | 5 | Staleness threshold. |
| `GOVEASE_BACKGROUND_REFRESH` | unset | `1` enables the background scheduler. |
| `GOVEASE_BACKGROUND_INTERVAL` | 10 | Minutes between background checks. |
| `GOVEASE_MAX_ITEMS` | 15 | Items kept per source per cycle. |
| `GOVEASE_RETENTION_DAYS` | 120 | Age at which feed items are pruned. |
| `GOVEASE_CYCLE_BUDGET` | 25 | Seconds before a cycle stops starting fetches. |
| `GOVEASE_DB` | `backend/database/govease.db` | Database location. |
| `PORT` | 5000 | Server port. |

---

## Data sources

Five official feeds, each **fetched and confirmed to parse** before being added:

| Source | Body |
|---|---|
| Reserve Bank of India | Press releases |
| MyGov | Citizen engagement |
| SEBI | Press releases and orders |
| TRAI | Telecom regulator |
| NITI Aayog | Policy think tank |

**Never add a feed URL you have not verified.** An invented or stale endpoint
either fails silently or, worse, produces an official-looking link that goes
nowhere. `news/sources.py` documents every candidate that was tested and
rejected, with the reason — including the Press Information Bureau, whose only
working RSS endpoint serves Hindi regardless of its `Lang` parameter.

To add a source, append one dict to `SOURCES` in `news/sources.py`. The
collector needs no changes.

### The cached snapshot

`news/data/seed_news.json` holds 20 **real** records previously collected from
the five feeds — four per source, each with its original government URL intact.
It exists so a fresh clone, or one with no network, still has genuine content to
serve.

Nothing in this project is invented. There is no fabricated or placeholder
government content anywhere in the data.

Snapshot rows load with `data_origin: "cached"` rather than `"feed"`, because the
copy may be out of date. The interface says so: a "Cached snapshot" banner names
the newest item's date, and each badge reads "Verified Government Source
(cached)". The moment a live refresh re-confirms one of those items, the row is
promoted to `"feed"` and the cached wording disappears on its own.

Regenerate the snapshot from a populated database at any time:

```bash
python -m news.collector --export-snapshot
```

It takes the newest items per source, round-robin so every source is
represented, and keeps only records whose URL is on a confirmed government
host.

### The verified badge

`✓ Verified Government Source` appears **only** when the item's URL is on a
confirmed government host — `*.gov.in`, `*.nic.in`, plus a short hand-checked
allowlist for `rbi.org.in` and `mygov.in`. Everything else shows a plain source
label with no badge. A lookalike domain such as `notgov.in` or
`mygov.in.example.com` does not qualify.

Cached rows get the same badge with "(cached)" appended, since the source is
genuinely official and only the copy's age is in question. The check is
implemented twice on purpose — `is_official_source()` in
`backend/models/news.py` for API responses, and `GovEase.util.isOfficialHost()`
in `script.js` for offline mode, where the page reads the snapshot file directly
and has no API to ask.

---

## Collector commands

```bash
python -m news.collector --seed
```

```bash
python -m news.collector --refresh
```

```bash
python -m news.collector --refresh --force
```

```bash
python -m news.collector --status
```

```bash
python -m news.collector --export-snapshot
```

`--seed` loads the cached snapshot. `--refresh` respects the freshness gate and
does nothing if the data is recent; `--force` overrides it. `--status` prints the
global timestamp and per-source health. `--export-snapshot` regenerates the
committed snapshot from rows already in the database.

---

## Working offline

The frontend falls back to the cached snapshot in `news/data/seed_news.json`
whenever the API is unreachable, filtering and searching client-side, and shows
an offline banner alongside the cached-snapshot notice. To see it:

```bash
python -m http.server 8000
```

Open <http://localhost:8000/frontend/news.html> with Flask stopped.

Serve it over `http://` rather than opening the file directly — a `file://`
origin blocks the fallback `fetch()` on CORS.

---

## Design notes

- **No CSS or JavaScript dependencies.** No CSS framework, no icon
  pack, no charting or animation library, no web fonts.
- **No polling.** The frontend fetches on page load and on user action only.
- **Feed content is never trusted as HTML** — everything is escaped before it
  reaches the DOM, and only `http(s)` URLs are rendered as links.
- **SQL is always parameterized.**
- Images are lazy-loaded with explicit dimensions so they cannot shift layout.
- Filter state is mirrored into the URL, so filtered views are shareable and the
  back button works.

---

## Documents & Forms (Member 3)

Open <http://localhost:5000/documents.html>, or use the quick links on the
homepage module card.

| Tool | What it does |
|---|---|
| Ready for application | Pick what the form asks for (recruitment photo 200×230 px 20–50 KB, signature 140×60 px 10–20 KB, thumb impression, passport photo 3.5×4.5 cm, scholarship photo, scanned certificate, PDF ≤ 200 KB / 1 MB). The file is cropped or padded, converted and compressed to fit, then checked for type, dimensions and size. The original is checked as well, so the citizen sees what was wrong. |
| Resize | Pixels, cm or mm (converted with the DPI); crop to fill, fit with a white border, or stretch. The DPI is written into the file. |
| Compress | Images: binary search for the highest JPEG/WEBP quality under the target KB; below quality 40 the image is shrunk instead. PDFs: embedded images and content streams are recompressed. |
| Convert | JPG ↔ PNG ↔ WEBP; images → one PDF (A4 or original size); PDF → images (ZIP for several pages). |
| Merge PDFs | Combine 2–20 PDFs in an order the citizen chooses. |

Design rules:

- **Nothing is stored.** Files are processed in memory and returned as a
  download; nothing is written to disk.
- **Type from content, not name.** A renamed `.exe` is rejected as `unsupported_type`.
- **Limits:** 10 MB per file, 20 files, 50 MB per request; decompression-bomb guard.
- **Privacy:** EXIF metadata (including phone GPS) is removed after the photo's
  rotation is applied.
- **Presets are indicative.** Every notification sets its own limits, so the
  page tells citizens to confirm them. Add a preset in `backend/documents/presets.py`.
- **Minimum size.** If a plain image (often a signature) is below a form's
  minimum even at maximum quality, a blank JPEG comment segment is added. No
  pixel changes, and the result shows a warning.

Run the test cases:

```bash
pip install pytest
```

```bash
python -m pytest tests -v
```

The API contract is in [`api/documents_api.md`](api/documents_api.md).

---

## Disclaimer

GovEase is an academic project, not an official government website. Updates are
collected from public government sources and may be incomplete or delayed.
Always confirm information against the original notification on the issuing
department's own website.
