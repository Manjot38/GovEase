"""Smart Document & Form Preparation Tool endpoints (Member 3, Module 3).

Registered in backend/app.py under /api/documents. Every endpoint is stateless: the file
arrives as multipart/form-data, is processed in memory and is returned
as a download. Nothing is stored on the server.

Processed files are returned with X-GovEase-* headers that describe the
result (sizes, dimensions, warnings) so the page can show a summary
without a second request. Errors are JSON objects of the form
{"error": code, "message": text}, as in the AI Assistant module.
"""

import io
import json

from flask import Blueprint, jsonify, request, send_file

from backend.documents import processor
from backend.documents.presets import public_presets
from backend.documents.processor import DocumentError

documents_bp = Blueprint("documents", __name__)

MAX_FILE_MB = 10
MAX_FILES = 20
MAX_REQUEST_MB = 50


# --------------------------------------------------------------------------
# Request helpers
# --------------------------------------------------------------------------

@documents_bp.before_request
def _limit_request_size():
    length = request.content_length
    if length and length > MAX_REQUEST_MB * 1024 * 1024:
        return _error(DocumentError(
            "request_too_large", f"Upload at most {MAX_REQUEST_MB} MB at once.", 413
        ))
    return None


@documents_bp.errorhandler(DocumentError)
def _handle_document_error(err):
    return _error(err)


def _error(err):
    return jsonify({"error": err.code, "message": err.message}), err.status


def _read_files(field="file", multiple=False):
    uploads = request.files.getlist(field)
    uploads = [u for u in uploads if u and u.filename]
    if not uploads:
        raise DocumentError("no_file", "Please choose a file to upload.")
    if not multiple and len(uploads) > 1:
        raise DocumentError("too_many_files", "Upload one file for this tool.")
    if len(uploads) > MAX_FILES:
        raise DocumentError("too_many_files", f"Upload at most {MAX_FILES} files.")
    files = []
    for upload in uploads:
        data = upload.read(MAX_FILE_MB * 1024 * 1024 + 1)
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            raise DocumentError(
                "file_too_large", f"'{upload.filename}' is larger than {MAX_FILE_MB} MB.", 413
            )
        if not data:
            raise DocumentError("empty_file", f"'{upload.filename}' is empty.")
        files.append((data, upload.filename))
    return files


def _int(name, default=None, minimum=None, maximum=None):
    raw = request.form.get(name, "").strip()
    if raw == "":
        return default
    try:
        value = int(float(raw))
    except ValueError:
        raise DocumentError("invalid_parameter", f"'{name}' must be a number.")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise DocumentError(
            "invalid_parameter", f"'{name}' must be between {minimum} and {maximum}."
        )
    return value


def _float(name, default=None):
    raw = request.form.get(name, "").strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise DocumentError("invalid_parameter", f"'{name}' must be a number.")


def _send(result):
    response = send_file(
        io.BytesIO(result.data), mimetype=result.mimetype,
        as_attachment=True, download_name=result.filename,
    )
    response.headers["X-GovEase-Meta"] = json.dumps(result.meta, ensure_ascii=True)
    response.headers["X-GovEase-Warnings"] = json.dumps(result.warnings, ensure_ascii=True)
    response.headers["Access-Control-Expose-Headers"] = (
        "X-GovEase-Meta, X-GovEase-Warnings, Content-Disposition"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@documents_bp.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "max_file_mb": MAX_FILE_MB,
        "max_files": MAX_FILES,
        "pdf_to_image": processor.pdfium is not None,
    })


@documents_bp.get("/presets")
def presets():
    return jsonify({"presets": public_presets()})


@documents_bp.post("/inspect")
def inspect():
    (data, filename), = _read_files()
    info = processor.inspect_file(data, filename)
    preset_id = request.form.get("preset", "").strip()
    if preset_id:
        info["checks"] = processor.check_against_preset(info, preset_id)
    return jsonify(info)


@documents_bp.post("/prepare")
def prepare():
    (data, filename), = _read_files()
    preset_id = request.form.get("preset", "").strip()
    if not preset_id:
        raise DocumentError("invalid_parameter", "Choose a document type (preset).")
    return _send(processor.prepare_for_preset(data, filename, preset_id))


@documents_bp.post("/image/resize")
def image_resize():
    (data, filename), = _read_files()
    width = _int("width", minimum=1, maximum=10000)
    height = _int("height", minimum=1, maximum=10000)
    if not width and not height:
        raise DocumentError("invalid_parameter", "Enter a width, a height, or both.")
    return _send(processor.image_resize(
        data, filename, width, height,
        mode=request.form.get("mode", "fill"),
        fmt=request.form.get("format") or None,
        quality=_int("quality", 90, 10, 100),
        dpi=_int("dpi", None, 72, 1200),
    ))


@documents_bp.post("/image/compress")
def image_compress():
    (data, filename), = _read_files()
    max_kb = _float("max_kb")
    if max_kb is None:
        raise DocumentError("invalid_parameter", "Enter the maximum size in KB.")
    return _send(processor.image_compress(
        data, filename, max_kb,
        fmt=request.form.get("format") or None,
        min_kb=_float("min_kb", 0),
    ))


@documents_bp.post("/image/convert")
def image_convert():
    (data, filename), = _read_files()
    return _send(processor.image_convert(
        data, filename, request.form.get("format", "jpg"),
        quality=_int("quality", 90, 10, 100),
    ))


@documents_bp.post("/pdf/from-images")
def pdf_from_images():
    files = _read_files("files", multiple=True)
    return _send(processor.images_to_pdf(
        files, page_size=request.form.get("page_size", "a4"),
        quality=_int("quality", 85, 10, 100),
    ))


@documents_bp.post("/pdf/merge")
def pdf_merge():
    return _send(processor.pdf_merge(_read_files("files", multiple=True)))


@documents_bp.post("/pdf/compress")
def pdf_compress():
    (data, filename), = _read_files()
    return _send(processor.pdf_compress(
        data, filename, max_kb=_float("max_kb"),
        level=request.form.get("level", "medium"),
    ))


@documents_bp.post("/pdf/to-images")
def pdf_to_images():
    (data, filename), = _read_files()
    return _send(processor.pdf_to_images(
        data, filename, fmt=request.form.get("format", "jpg"),
        dpi=_int("dpi", 150, 50, 300),
    ))
