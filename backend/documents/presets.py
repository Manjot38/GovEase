"""Module 3 — application-ready presets.

Each preset describes a typical requirement printed in Indian online
application forms. Values are indicative only: every recruitment or
scheme notification sets its own limits, so the interface always tells
the citizen to confirm them in the official notification.

Adding a preset needs only one new entry here; the processor and the
API do not change (same idea as news/sources.py in Module 2).
"""

PRESETS = {
    "photo_recruitment": {
        "label": "Recruitment form photograph",
        "description": "Recent colour photo, 200 x 230 px, 20-50 KB, JPG.",
        "kind": "image",
        "width": 200,
        "height": 230,
        "min_kb": 20,
        "max_kb": 50,
        "format": "jpg",
        "dpi": 200,
        "mode": "fill",
    },
    "signature_recruitment": {
        "label": "Recruitment form signature",
        "description": "Signature on white paper, 140 x 60 px, 10-20 KB, JPG.",
        "kind": "image",
        "width": 140,
        "height": 60,
        "min_kb": 10,
        "max_kb": 20,
        "format": "jpg",
        "dpi": 200,
        "mode": "pad",
    },
    "thumb_impression": {
        "label": "Left thumb impression",
        "description": "Thumb impression, 240 x 240 px, 20-50 KB, JPG.",
        "kind": "image",
        "width": 240,
        "height": 240,
        "min_kb": 20,
        "max_kb": 50,
        "format": "jpg",
        "dpi": 200,
        "mode": "pad",
    },
    "passport_photo": {
        "label": "Passport-size photo (3.5 x 4.5 cm)",
        "description": "3.5 x 4.5 cm at 300 DPI (413 x 531 px), up to 100 KB, JPG.",
        "kind": "image",
        "width": 413,
        "height": 531,
        "min_kb": 0,
        "max_kb": 100,
        "format": "jpg",
        "dpi": 300,
        "mode": "fill",
    },
    "scholarship_photo": {
        "label": "Scholarship portal photo",
        "description": "Passport-style photo, 3.5 x 4.5 cm, up to 200 KB, JPG.",
        "kind": "image",
        "width": 350,
        "height": 450,
        "min_kb": 0,
        "max_kb": 200,
        "format": "jpg",
        "dpi": 254,
        "mode": "fill",
    },
    "document_scan_image": {
        "label": "Scanned certificate (image)",
        "description": "A4 scan, max 1240 px wide (150 DPI), up to 300 KB, JPG.",
        "kind": "image",
        "width": 1240,
        "height": None,
        "min_kb": 0,
        "max_kb": 300,
        "format": "jpg",
        "dpi": 150,
        "mode": "max",
    },
    "document_pdf_small": {
        "label": "Supporting document (PDF, 200 KB)",
        "description": "Certificate or ID proof as PDF, up to 200 KB.",
        "kind": "pdf",
        "min_kb": 0,
        "max_kb": 200,
    },
    "document_pdf_large": {
        "label": "Supporting document (PDF, 1 MB)",
        "description": "Multi-page document as PDF, up to 1 MB.",
        "kind": "pdf",
        "min_kb": 0,
        "max_kb": 1024,
    },
}


def public_presets():
    """Presets as a list for GET /api/documents/presets."""
    return [{"id": key, **value} for key, value in PRESETS.items()]
