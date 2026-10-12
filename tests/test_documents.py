"""Test cases for Module 3 (Smart Document & Form Tool).

Run from the project root:
    pip install pytest
    python -m pytest tests/test_documents.py -v
IDs D1-D20 match the Module 3 test-case table in the final report.
"""
import io
import json
import zipfile

import pytest
from flask import Flask
from PIL import Image
from pypdf import PdfReader, PdfWriter

from backend.documents import processor
from backend.routes.documents import documents_bp


# ---------------------------------------------------------------- fixtures

@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(documents_bp, url_prefix="/api/documents")
    return app.test_client()


def photo_bytes(size=(1200, 1600), fmt="JPEG", noisy=True, mode="RGB"):
    """A photo-like image; noise makes it hard to compress, like a real photo."""
    if noisy:
        img = Image.effect_noise(size, 60).convert(mode)
    else:
        img = Image.new(mode, size, "white")
    buf = io.BytesIO()
    img.save(buf, fmt, **({"quality": 95} if fmt == "JPEG" else {}))
    return buf.getvalue()


def pdf_bytes(pages=1, with_image=True):
    imgs = [Image.effect_noise((1500, 2000), 50).convert("RGB") for _ in range(pages)]
    buf = io.BytesIO()
    imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:], quality=95)
    return buf.getvalue()


def upload(client, path, files, field="file", **form):
    data = {k: str(v) for k, v in form.items()}
    data[field] = [(io.BytesIO(b), name) for b, name in files]
    return client.post(path, data=data, content_type="multipart/form-data")


def meta(resp):
    return json.loads(resp.headers["X-GovEase-Meta"])


# ---------------------------------------------------------------- API tests

def test_d1_health_and_presets(client):
    assert client.get("/api/documents/health").get_json()["status"] == "ok"
    ids = [p["id"] for p in client.get("/api/documents/presets").get_json()["presets"]]
    assert "photo_recruitment" in ids and "document_pdf_small" in ids


def test_d2_prepare_recruitment_photo_meets_all_checks(client):
    resp = upload(client, "/api/documents/prepare", [(photo_bytes(), "my photo.png")],
                  preset="photo_recruitment")
    assert resp.status_code == 200
    img = Image.open(io.BytesIO(resp.data))
    assert img.format == "JPEG" and img.size == (200, 230)
    assert 20 * 1024 <= len(resp.data) <= 50 * 1024
    assert all(c["ok"] for c in meta(resp)["checks"])


def test_d3_prepare_signature_pads_plain_image_to_minimum(client):
    # A plain white signature compresses to ~1 KB; the 10 KB minimum must still be met.
    resp = upload(client, "/api/documents/prepare",
                  [(photo_bytes((600, 200), "PNG", noisy=False), "sign.png")],
                  preset="signature_recruitment")
    assert resp.status_code == 200
    assert 10 * 1024 <= len(resp.data) <= 20 * 1024
    assert Image.open(io.BytesIO(resp.data)).size == (140, 60)
    assert all(c["ok"] for c in meta(resp)["checks"])


def test_d4_prepare_pdf_preset_from_image(client):
    resp = upload(client, "/api/documents/prepare", [(photo_bytes(), "aadhaar.jpg")],
                  preset="document_pdf_large")
    assert resp.status_code == 200 and resp.data[:5] == b"%PDF-"
    assert len(resp.data) <= 1024 * 1024


def test_d5_resize_exact_pixels(client):
    resp = upload(client, "/api/documents/image/resize", [(photo_bytes(), "a.jpg")],
                  width=413, height=531, mode="fill", dpi=300)
    img = Image.open(io.BytesIO(resp.data))
    assert img.size == (413, 531)
    assert round(img.info["dpi"][0]) == 300


def test_d6_resize_width_only_keeps_ratio(client):
    resp = upload(client, "/api/documents/image/resize", [(photo_bytes((1200, 1600)), "a.jpg")],
                  width=300)
    assert Image.open(io.BytesIO(resp.data)).size == (300, 400)


def test_d7_compress_image_to_target(client):
    original = photo_bytes((2000, 2000))
    resp = upload(client, "/api/documents/image/compress", [(original, "big.jpg")], max_kb=100)
    assert resp.status_code == 200 and len(resp.data) <= 100 * 1024
    assert meta(resp)["saved_percent"] > 50


def test_d8_convert_png_with_transparency_to_jpg(client):
    buf = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(buf, "PNG")
    resp = upload(client, "/api/documents/image/convert", [(buf.getvalue(), "t.png")],
                  format="jpg")
    img = Image.open(io.BytesIO(resp.data))
    assert img.format == "JPEG" and img.getpixel((10, 10)) == (255, 255, 255)
    assert json.loads(resp.headers["X-GovEase-Warnings"])


def test_d9_images_to_a4_pdf_keeps_page_order(client):
    resp = upload(client, "/api/documents/pdf/from-images",
                  [(photo_bytes((400, 600)), "1.jpg"), (photo_bytes((600, 400)), "2.jpg")],
                  field="files", page_size="a4")
    reader = PdfReader(io.BytesIO(resp.data))
    assert len(reader.pages) == 2


def test_d10_merge_pdfs(client):
    resp = upload(client, "/api/documents/pdf/merge",
                  [(pdf_bytes(2), "a.pdf"), (pdf_bytes(1), "b.pdf")], field="files")
    assert resp.status_code == 200
    assert len(PdfReader(io.BytesIO(resp.data)).pages) == 3


def test_d11_compress_scanned_pdf(client):
    original = pdf_bytes(2)
    resp = upload(client, "/api/documents/pdf/compress", [(original, "scan.pdf")], max_kb=300)
    assert resp.status_code == 200
    assert len(resp.data) < len(original)
    assert len(PdfReader(io.BytesIO(resp.data)).pages) == 2


def test_d12_pdf_to_images_zip(client):
    if processor.pdfium is None:
        pytest.skip("pypdfium2 not installed")
    resp = upload(client, "/api/documents/pdf/to-images", [(pdf_bytes(2), "x.pdf")], dpi=72)
    assert resp.mimetype == "application/zip"
    assert len(zipfile.ZipFile(io.BytesIO(resp.data)).namelist()) == 2


def test_d13_inspect_reports_failed_checks(client):
    resp = upload(client, "/api/documents/inspect", [(photo_bytes(), "raw.png")],
                  preset="photo_recruitment")
    body = resp.get_json()
    assert body["width"] == 1200 and body["format"] == "jpg"
    assert any(not c["ok"] for c in body["checks"])


# ---------------------------------------------------------------- negative tests

def test_d14_no_file(client):
    resp = client.post("/api/documents/image/convert", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400 and resp.get_json()["error"] == "no_file"


def test_d15_fake_extension_rejected(client):
    resp = upload(client, "/api/documents/image/convert", [(b"MZ\x90\x00 not an image", "virus.jpg")])
    assert resp.status_code == 415 and resp.get_json()["error"] == "unsupported_type"


def test_d16_file_over_10_mb(client):
    resp = upload(client, "/api/documents/image/convert", [(b"\xff" * (10 * 1024 * 1024 + 5), "big.jpg")])
    assert resp.status_code == 413 and resp.get_json()["error"] == "file_too_large"


def test_d17_password_protected_pdf(client):
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes(1))))
    writer.encrypt("secret")
    buf = io.BytesIO()
    writer.write(buf)
    resp = upload(client, "/api/documents/pdf/compress", [(buf.getvalue(), "locked.pdf")])
    assert resp.status_code == 422 and resp.get_json()["error"] == "pdf_encrypted"


def test_d18_unknown_preset(client):
    resp = upload(client, "/api/documents/prepare", [(photo_bytes(), "a.jpg")], preset="nope")
    assert resp.status_code == 404 and resp.get_json()["error"] == "unknown_preset"


def test_d19_invalid_parameters(client):
    resp = upload(client, "/api/documents/image/resize", [(photo_bytes(), "a.jpg")], width="abc")
    assert resp.status_code == 400 and resp.get_json()["error"] == "invalid_parameter"
    resp = upload(client, "/api/documents/pdf/merge", [(pdf_bytes(1), "only.pdf")], field="files")
    assert resp.status_code == 400


def test_d20_unsafe_filename_is_sanitised(client):
    resp = upload(client, "/api/documents/image/convert", [(photo_bytes((50, 50)), "../../etc/<x>.png")],
                  format="png")
    disposition = resp.headers["Content-Disposition"]
    assert ".." not in disposition and "<" not in disposition and "/" not in disposition


# ---------------------------------------------------------------- unit checks

def test_exif_rotation_is_applied():
    img = Image.new("RGB", (100, 50))
    exif = img.getexif()
    exif[0x0112] = 6  # rotated 90 degrees
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    assert processor.load_image(buf.getvalue()).size == (50, 100)


def test_pad_jpeg_keeps_image_valid():
    data = photo_bytes((40, 40), noisy=False)
    padded = processor.pad_jpeg_to_min(data, 70_000)
    assert len(padded) >= 70_000
    assert Image.open(io.BytesIO(padded)).size == (40, 40)


def test_compression_prefers_downscaling_over_blocky_quality():
    img = Image.effect_noise((1600, 1600), 80).convert("RGB")
    data, details, warnings = processor.compress_image_to_target(img, "jpg", 200)
    assert len(data) <= 200 * 1024
    assert details["quality"] >= processor.MIN_READABLE_QUALITY
    assert details["width"] < 1600 and warnings
