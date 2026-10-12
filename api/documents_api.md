# GovEase Documents API

Contract for the Smart Document & Form Preparation Tool (Member 3).

- **Base URL (development):** `http://localhost:5000/api/documents`
- **Requests:** `multipart/form-data` (file fields `file` or `files`)
- **Responses:** the processed file as a download, or JSON for `health`,
  `presets`, `inspect` and errors
- **Auth:** none (prototype)
- **Storage:** none. Every request is processed in memory and forgotten.

---

## Result headers

Every endpoint that returns a file adds two JSON headers, so the page can show
a summary without a second request:

| Header | Example |
|---|---|
| `X-GovEase-Meta` | `{"original_kb": 1680.2, "result_kb": 48.9, "saved_percent": 97.1, "width": 200, "height": 230, "quality": 88, "checks": [...]}` |
| `X-GovEase-Warnings` | `["Image was reduced to 1024 x 1024 px to meet the size limit."]` |

`checks` (from `/prepare`) is a list of
`{"label": "File size", "ok": true, "actual": "48.9 KB", "expected": "20-50 KB"}`.

---

## Endpoints

| Method | Endpoint | Form fields | Returns |
|---|---|---|---|
| GET | `/health` | — | `{"status": "ok", "max_file_mb": 10, "max_files": 20, "pdf_to_image": true}` |
| GET | `/presets` | — | `{"presets": [{"id", "label", "description", "kind", "width", "height", "min_kb", "max_kb", "format", ...}]}` |
| POST | `/inspect` | `file`, optional `preset` | JSON: `kind`, `format`, `size_kb`, `width`, `height`, `dpi` or `pages`, and `checks` when a preset is given |
| POST | `/prepare` | `file`, `preset` | File meeting the preset, with `checks` in `X-GovEase-Meta` |
| POST | `/image/resize` | `file`, `width` and/or `height` (px), `mode` (`fill`/`pad`/`stretch`/`max`), `format`, `dpi`, `quality` | Image |
| POST | `/image/compress` | `file`, `max_kb`, optional `min_kb`, `format` | Image |
| POST | `/image/convert` | `file`, `format` (`jpg`/`png`/`webp`), `quality` | Image |
| POST | `/pdf/from-images` | `files` (1–20, in page order), `page_size` (`a4`/`auto`) | PDF |
| POST | `/pdf/merge` | `files` (2–20, in order) | PDF |
| POST | `/pdf/compress` | `file`, `max_kb` **or** `level` (`low`/`medium`/`high`) | PDF |
| POST | `/pdf/to-images` | `file`, `format` (`jpg`/`png`), `dpi` (50–300) | Image, or ZIP for several pages |

Example:

```bash
curl -F "file=@photo.jpg" -F "preset=photo_recruitment" -o photo_ready.jpg http://localhost:5000/api/documents/prepare
```

---

## Errors

Same shape as the assistant: `{"error": code, "message": text}`. The message
is written for citizens and can be shown directly.

| Condition | HTTP | Error code |
|---|---|---|
| No file chosen | 400 | `no_file` |
| Empty file | 400 | `empty_file` |
| Bad number or option | 400 | `invalid_parameter` |
| Too many files, or several where one is expected | 400 | `too_many_files` |
| PDF over 30 pages for PDF → images | 400 | `too_many_pages` |
| Unknown preset | 404 | `unknown_preset` |
| File over 10 MB | 413 | `file_too_large` |
| Request over 50 MB | 413 | `request_too_large` |
| Image over 50 megapixels | 413 | `image_too_large` |
| Content is not an image or PDF (checked by content, not extension) | 415 | `unsupported_type` |
| Password-protected PDF | 422 | `pdf_encrypted` |
| Damaged file | 422 | `corrupt_file` |
| pypdfium2 not installed | 503 | `feature_unavailable` |
