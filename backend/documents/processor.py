"""Module 3 — Smart Document & Form Preparation Tool: file processing.

Pure functions with no Flask dependency, so they can be unit-tested
directly. Every operation works on bytes in memory: uploaded files are
never written to disk and nothing is kept after the response is sent.
"""

import io
import os
import re
import zipfile
from dataclasses import dataclass, field

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from .presets import PRESETS

try:  # Optional: only needed for PDF -> image conversion.
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover - depends on the environment
    pdfium = None

# Refuse decompression bombs (a tiny file that expands to a huge bitmap).
Image.MAX_IMAGE_PIXELS = 50_000_000

IMAGE_FORMATS = {
    "jpg": {"pil": "JPEG", "mime": "image/jpeg", "ext": "jpg"},
    "png": {"pil": "PNG", "mime": "image/png", "ext": "png"},
    "webp": {"pil": "WEBP", "mime": "image/webp", "ext": "webp"},
}
FORMAT_ALIASES = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}
RESIZE_MODES = ("fill", "pad", "stretch", "max")
A4_PX_150DPI = (1240, 1754)
MAX_PDF_PAGES_TO_RENDER = 30
MIN_READABLE_QUALITY = 40  # below this JPEG text and faces turn blocky


class DocumentError(Exception):
    """A user-facing error with an error code and HTTP status."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class Result:
    data: bytes
    mimetype: str
    filename: str
    meta: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def normalise_format(fmt):
    key = FORMAT_ALIASES.get(str(fmt or "").strip().lower())
    if not key:
        raise DocumentError(
            "invalid_parameter", "Format must be one of: jpg, png, webp."
        )
    return key


def safe_stem(filename, fallback="document"):
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    return stem[:60] or fallback


def kb(n_bytes):
    return round(n_bytes / 1024, 1)


def detect_kind(data):
    """Return "pdf" or "image" from the file content, not its name."""
    if not data:
        raise DocumentError("empty_file", "The uploaded file is empty.")
    if data[:5] == b"%PDF-":
        return "pdf"
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        return "image"
    except Image.DecompressionBombError:
        raise DocumentError(
            "image_too_large", "The image has too many pixels to process.", 413
        )
    except Exception:
        raise DocumentError(
            "unsupported_type",
            "Unsupported file. Upload a JPG, PNG, WEBP, BMP, GIF, TIFF or PDF file.",
            415,
        )


def load_image(data):
    """Open an image, apply the camera's EXIF rotation and drop metadata."""
    if detect_kind(data) != "image":
        raise DocumentError("unsupported_type", "Please upload an image file.", 415)
    try:
        img = Image.open(io.BytesIO(data))
        original_format = img.format
        img = ImageOps.exif_transpose(img)
        img.load()
        img.format = original_format
    except Image.DecompressionBombError:
        raise DocumentError(
            "image_too_large", "The image has too many pixels to process.", 413
        )
    except Exception:
        raise DocumentError("corrupt_file", "The image could not be read.", 422)
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
        img = img.copy()
    return img


def to_rgb(img, background=(255, 255, 255)):
    """Flatten transparency onto white, as forms expect a white background."""
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, background)
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return img.convert("RGB")


def encode_image(img, fmt, quality=85, dpi=None):
    fmt = normalise_format(fmt)
    buf = io.BytesIO()
    params = {}
    if dpi:
        params["dpi"] = (int(dpi), int(dpi))
    if fmt == "jpg":
        img = to_rgb(img)
        img.save(
            buf, "JPEG", quality=int(quality), optimize=True,
            subsampling=0 if quality >= 90 else 2, **params,
        )
    elif fmt == "webp":
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        img.save(buf, "WEBP", quality=int(quality), method=6, **params)
    else:
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
            img = img.convert("RGB")
        img.save(buf, "PNG", optimize=True, **params)
    return buf.getvalue()


def pad_jpeg_to_min(data, min_bytes):
    """Reach a portal's minimum file size by adding JPEG comment segments.

    Some portals reject photos below e.g. 20 KB even when the image is
    already at maximum quality. A COM (comment) segment is part of the
    JPEG standard and does not change a single pixel of the picture.
    """
    if len(data) >= min_bytes or data[:2] != b"\xff\xd8":
        return data
    missing = min_bytes - len(data)
    segments = bytearray()
    while missing > 0:
        payload_len = min(65533, max(1, missing - 4))
        segments += b"\xff\xfe" + (payload_len + 2).to_bytes(2, "big")
        segments += b" " * payload_len
        missing -= payload_len + 4
    return data[:2] + bytes(segments) + data[2:]


# --------------------------------------------------------------------------
# Image operations
# --------------------------------------------------------------------------

def resize_image(img, width=None, height=None, mode="fill"):
    """Resize to the requested size.

    fill    - crop to fill the exact size (good for photos)
    pad     - fit inside the size and pad with white (good for signatures)
    stretch - force the exact size, ignoring the aspect ratio
    max     - shrink only, keeping the aspect ratio, to fit inside the box
    With only one of width/height, the other is computed proportionally.
    """
    if mode not in RESIZE_MODES:
        raise DocumentError(
            "invalid_parameter", f"Mode must be one of: {', '.join(RESIZE_MODES)}."
        )
    for value in (width, height):
        if value is not None and not (1 <= value <= 10000):
            raise DocumentError(
                "invalid_parameter", "Width and height must be 1-10000 pixels."
            )
    if not width and not height:
        return img

    w, h = img.size
    if mode == "max":
        box = (width or w, height or h)
        out = img.copy()
        out.thumbnail(box, Image.LANCZOS)
        return out
    if not width:
        width = max(1, round(w * height / h))
    if not height:
        height = max(1, round(h * width / w))
    if mode == "fill":
        # Centre slightly above the middle so faces are not cropped.
        return ImageOps.fit(img, (width, height), Image.LANCZOS, centering=(0.5, 0.4))
    if mode == "pad":
        return ImageOps.pad(to_rgb(img), (width, height), Image.LANCZOS, color="white")
    return img.resize((width, height), Image.LANCZOS)


def compress_image_to_target(img, fmt, max_kb, min_kb=0, dpi=None,
                             allow_downscale=True):
    """Encode `img` as `fmt` in the [min_kb, max_kb] range.

    Binary-searches the highest quality that fits under max_kb. When
    downscaling is allowed, quality never drops below MIN_READABLE_QUALITY:
    the image is shrunk by 20 % steps instead, because a slightly smaller
    picture stays far more legible than a heavily blocky one.
    Returns (bytes, details, warnings).
    """
    fmt = normalise_format(fmt)
    target = int(max_kb * 1024)
    warnings = []
    details = {"quality": None, "scale": 1.0}
    current, scale, data = img, 1.0, None
    attempts = 12

    for attempt_no in range(attempts):
        last_try = (not allow_downscale or attempt_no == attempts - 1
                    or min(current.size) <= 16)
        if fmt == "png":
            data = encode_image(current, "png", dpi=dpi)
            if len(data) > target and current.mode != "P":
                quantised = to_rgb(current).quantize(colors=256, method=Image.MEDIANCUT)
                data = min(data, encode_image(quantised, "png", dpi=dpi), key=len)
            fits = len(data) <= target
        else:
            floor = 5 if last_try else MIN_READABLE_QUALITY
            lo, hi, best = floor, 95, None
            while lo <= hi:
                mid = (lo + hi) // 2
                attempt = encode_image(current, fmt, mid, dpi)
                if len(attempt) <= target:
                    best, lo = (attempt, mid), mid + 1
                else:
                    hi = mid - 1
            fits = best is not None
            data, details["quality"] = best if fits else (encode_image(current, fmt, floor, dpi), floor)
        if fits or last_try:
            break
        scale *= 0.8
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        current = img.resize(size, Image.LANCZOS)

    details["scale"] = round(scale, 3)
    details["width"], details["height"] = current.size
    if len(data) > target:
        warnings.append(
            f"Could not reach {max_kb} KB; the smallest possible file is {kb(len(data))} KB."
        )
    if scale < 1:
        warnings.append(
            f"Image was reduced to {current.width} x {current.height} px to meet the size limit."
        )

    if min_kb and len(data) < min_kb * 1024 and fmt == "jpg":
        best_quality = encode_image(current, "jpg", 100, dpi)
        if len(best_quality) <= target:
            data, details["quality"] = best_quality, 100
        if len(data) < min_kb * 1024:
            data = pad_jpeg_to_min(data, int(min_kb * 1024) + 512)
            details["padded"] = True
            warnings.append(
                f"Image was below the {min_kb} KB minimum, so a blank JPEG comment "
                "was added. The picture itself is unchanged."
            )
    return data, details, warnings


def image_resize(data, filename, width=None, height=None, mode="fill",
                 fmt=None, quality=90, dpi=None):
    img = load_image(data)
    fmt = normalise_format(fmt or _guess_format(img))
    out = resize_image(img, width, height, mode)
    encoded = encode_image(out, fmt, quality, dpi)
    return Result(
        encoded, IMAGE_FORMATS[fmt]["mime"],
        f"{safe_stem(filename)}_{out.width}x{out.height}.{IMAGE_FORMATS[fmt]['ext']}",
        meta=_image_meta(out, encoded, len(data)),
    )


def image_compress(data, filename, max_kb, fmt=None, min_kb=0):
    if not (1 <= max_kb <= 20480):
        raise DocumentError("invalid_parameter", "Target size must be 1-20480 KB.")
    if min_kb < 0 or min_kb >= max_kb:
        raise DocumentError(
            "invalid_parameter", "Minimum size must be smaller than the target size."
        )
    img = load_image(data)
    fmt = normalise_format(fmt or _guess_format(img))
    encoded, details, warnings = compress_image_to_target(img, fmt, max_kb, min_kb)
    return Result(
        encoded, IMAGE_FORMATS[fmt]["mime"],
        f"{safe_stem(filename)}_{int(max_kb)}kb.{IMAGE_FORMATS[fmt]['ext']}",
        meta={**_image_meta_from_size(details["width"], details["height"], encoded, len(data)),
              "quality": details["quality"]},
        warnings=warnings,
    )


def image_convert(data, filename, fmt, quality=90):
    img = load_image(data)
    fmt = normalise_format(fmt)
    encoded = encode_image(img, fmt, quality)
    warnings = []
    if fmt == "jpg" and ("A" in img.getbands() or "transparency" in img.info):
        warnings.append("JPG has no transparency; transparent areas were filled with white.")
    return Result(
        encoded, IMAGE_FORMATS[fmt]["mime"],
        f"{safe_stem(filename)}.{IMAGE_FORMATS[fmt]['ext']}",
        meta=_image_meta(img, encoded, len(data)), warnings=warnings,
    )


# --------------------------------------------------------------------------
# PDF operations
# --------------------------------------------------------------------------

def open_pdf(data):
    if detect_kind(data) != "pdf":
        raise DocumentError("unsupported_type", "Please upload a PDF file.", 415)
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError(
                "pdf_encrypted",
                "This PDF is password-protected. Remove the password and try again.",
                422,
            )
        _ = len(reader.pages)
        return reader
    except DocumentError:
        raise
    except (PdfReadError, Exception):
        raise DocumentError("corrupt_file", "The PDF could not be read.", 422)


def images_to_pdf(files, page_size="a4", quality=85):
    """Combine images (list of (bytes, filename)) into one PDF."""
    if page_size not in ("a4", "auto"):
        raise DocumentError("invalid_parameter", "Page size must be 'a4' or 'auto'.")
    pages = []
    for data, _name in files:
        img = to_rgb(load_image(data))
        if page_size == "a4":
            canvas = Image.new("RGB", A4_PX_150DPI, "white")
            margin = 60
            img.thumbnail(
                (A4_PX_150DPI[0] - 2 * margin, A4_PX_150DPI[1] - 2 * margin), Image.LANCZOS
            )
            canvas.paste(
                img, ((canvas.width - img.width) // 2, (canvas.height - img.height) // 2)
            )
            img = canvas
        else:
            img.thumbnail((2000, 2000), Image.LANCZOS)
        pages.append(img)
    buf = io.BytesIO()
    pages[0].save(
        buf, "PDF", save_all=True, append_images=pages[1:],
        resolution=150, quality=int(quality),
    )
    out = buf.getvalue()
    original = sum(len(d) for d, _ in files)
    name = safe_stem(files[0][1]) if len(files) == 1 else "combined_documents"
    return Result(out, "application/pdf", f"{name}.pdf",
                  meta=_size_meta(out, original, pages=len(pages)))


def pdf_merge(files):
    if len(files) < 2:
        raise DocumentError("invalid_parameter", "Select at least two PDF files to merge.")
    writer = PdfWriter()
    for data, _name in files:
        writer.append(open_pdf(data))
    buf = io.BytesIO()
    writer.write(buf)
    out = buf.getvalue()
    return Result(out, "application/pdf", "merged_documents.pdf",
                  meta=_size_meta(out, sum(len(d) for d, _ in files),
                                  pages=len(writer.pages)))


def _rewrite_pdf(data, quality, max_px):
    writer = PdfWriter(clone_from=open_pdf(data))
    for page in writer.pages:
        for image in page.images:
            try:
                pil = image.image
                if max(pil.size) > max_px:
                    pil = pil.copy()
                    pil.thumbnail((max_px, max_px), Image.LANCZOS)
                if pil.mode not in ("RGB", "L"):
                    pil = to_rgb(pil)
                image.replace(pil, quality=quality)
            except Exception:
                continue  # Inline or unusual images are left untouched.
        page.compress_content_streams()
    if hasattr(writer, "compress_identical_objects"):
        writer.compress_identical_objects()  # merge duplicates, drop orphans
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def pdf_compress(data, filename, max_kb=None, level="medium"):
    """Shrink a PDF by recompressing its images and content streams."""
    ladders = {
        "low": [(80, 2000)],
        "medium": [(65, 1600)],
        "high": [(40, 1200)],
    }
    if max_kb is not None:
        if not (10 <= max_kb <= 51200):
            raise DocumentError("invalid_parameter", "Target size must be 10-51200 KB.")
        steps = [(85, 2200), (70, 1800), (55, 1500), (40, 1200), (30, 1000), (20, 800)]
    elif level in ladders:
        steps = ladders[level]
    else:
        raise DocumentError("invalid_parameter", "Level must be low, medium or high.")

    best = None
    for quality, max_px in steps:
        out = _rewrite_pdf(data, quality, max_px)
        if best is None or len(out) < len(best):
            best = out
        if max_kb is not None and len(out) <= max_kb * 1024:
            best = out
            break

    warnings = []
    if len(best) >= len(data):
        best = data
        warnings.append("This PDF is already well optimised; the original is returned.")
    if max_kb is not None and len(best) > max_kb * 1024:
        warnings.append(
            f"Could not reach {max_kb} KB; the smallest result is {kb(len(best))} KB. "
            "Text-heavy PDFs cannot shrink much — try scanning at a lower resolution."
        )
    pages = len(PdfReader(io.BytesIO(best)).pages)
    return Result(best, "application/pdf", f"{safe_stem(filename)}_compressed.pdf",
                  meta=_size_meta(best, len(data), pages=pages), warnings=warnings)


def pdf_to_images(data, filename, fmt="jpg", dpi=150):
    if pdfium is None:
        raise DocumentError(
            "feature_unavailable",
            "PDF to image needs the pypdfium2 package on the server.", 503,
        )
    if not (50 <= dpi <= 300):
        raise DocumentError("invalid_parameter", "DPI must be between 50 and 300.")
    fmt = normalise_format(fmt)
    open_pdf(data)  # validates type and encryption with friendly errors
    doc = pdfium.PdfDocument(data)
    try:
        count = len(doc)
        if count > MAX_PDF_PAGES_TO_RENDER:
            raise DocumentError(
                "too_many_pages",
                f"PDFs with more than {MAX_PDF_PAGES_TO_RENDER} pages cannot be converted.",
            )
        stem = safe_stem(filename)
        ext = IMAGE_FORMATS[fmt]["ext"]
        rendered = []
        for i in range(count):
            pil = doc[i].render(scale=dpi / 72).to_pil()
            rendered.append(encode_image(pil, fmt, 90, dpi))
    finally:
        doc.close()

    if count == 1:
        return Result(rendered[0], IMAGE_FORMATS[fmt]["mime"], f"{stem}.{ext}",
                      meta=_size_meta(rendered[0], len(data), pages=1))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, page_bytes in enumerate(rendered, start=1):
            zf.writestr(f"{stem}_page{i}.{ext}", page_bytes)
    out = buf.getvalue()
    return Result(out, "application/zip", f"{stem}_pages.zip",
                  meta=_size_meta(out, len(data), pages=count))


# --------------------------------------------------------------------------
# Inspect and prepare-for-application
# --------------------------------------------------------------------------

def inspect_file(data, filename):
    kind = detect_kind(data)
    info = {"filename": filename, "kind": kind, "size_bytes": len(data),
            "size_kb": kb(len(data))}
    if kind == "image":
        with Image.open(io.BytesIO(data)) as raw:
            fmt = (raw.format or "").lower()
            dpi = raw.info.get("dpi")
        img = load_image(data)
        info.update({
            "format": "jpg" if fmt == "jpeg" else fmt,
            "width": img.width, "height": img.height, "color_mode": img.mode,
            "dpi": round(float(dpi[0])) if dpi else None,
        })
    else:
        reader = open_pdf(data)
        info.update({"format": "pdf", "pages": len(reader.pages)})
    return info


def check_against_preset(info, preset_id):
    """Compare an inspected file with a preset; return a list of checks."""
    preset = _get_preset(preset_id)
    checks = []
    expected_format = "pdf" if preset["kind"] == "pdf" else preset["format"]
    checks.append(_check("File type", info["format"] == expected_format,
                         info["format"].upper(), f"{expected_format.upper()} required"))
    if preset["kind"] == "image" and info["kind"] == "image":
        if preset.get("height"):
            ok = (info["width"], info["height"]) == (preset["width"], preset["height"])
            want = f"{preset['width']} x {preset['height']} px"
        else:
            ok = info["width"] <= preset["width"]
            want = f"max {preset['width']} px wide"
        checks.append(_check("Dimensions", ok,
                             f"{info['width']} x {info['height']} px", want))
    size_ok = preset["min_kb"] * 1024 <= info["size_bytes"] <= preset["max_kb"] * 1024
    want = (f"{preset['min_kb']}-{preset['max_kb']} KB" if preset["min_kb"]
            else f"up to {preset['max_kb']} KB")
    checks.append(_check("File size", size_ok, f"{info['size_kb']} KB", want))
    return checks


def prepare_for_preset(data, filename, preset_id):
    """Turn any upload into a file that meets the chosen preset."""
    preset = _get_preset(preset_id)
    kind = detect_kind(data)

    if preset["kind"] == "pdf":
        if kind == "image":
            data = images_to_pdf([(data, filename)], "a4").data
        result = pdf_compress(data, filename, max_kb=preset["max_kb"])
        result.filename = f"{safe_stem(filename)}_{preset_id}.pdf"
    else:
        if kind != "image":
            raise DocumentError(
                "unsupported_type",
                "This preset needs a photo or scanned image (JPG, PNG). "
                "Use 'PDF to image' first if you only have a PDF.", 415,
            )
        img = resize_image(load_image(data), preset["width"], preset.get("height"),
                           preset["mode"])
        encoded, details, warnings = compress_image_to_target(
            img, preset["format"], preset["max_kb"], preset["min_kb"],
            dpi=preset.get("dpi"), allow_downscale=preset["mode"] == "max",
        )
        result = Result(
            encoded, IMAGE_FORMATS[preset["format"]]["mime"],
            f"{safe_stem(filename)}_{preset_id}.{IMAGE_FORMATS[preset['format']]['ext']}",
            meta={**_image_meta_from_size(details["width"], details["height"],
                                          encoded, len(data)),
                  "quality": details["quality"]},
            warnings=warnings,
        )

    result.meta["preset"] = preset_id
    result.meta["checks"] = check_against_preset(
        inspect_file(result.data, result.filename), preset_id
    )
    return result


# --------------------------------------------------------------------------
# Internal
# --------------------------------------------------------------------------

def _get_preset(preset_id):
    preset = PRESETS.get(preset_id)
    if not preset:
        raise DocumentError("unknown_preset", f"Unknown preset '{preset_id}'.", 404)
    return preset


def _check(label, ok, actual, expected):
    return {"label": label, "ok": bool(ok), "actual": actual, "expected": expected}


def _guess_format(img):
    fmt = (img.format or "").lower()
    if fmt in ("jpeg", "jpg"):
        return "jpg"
    if fmt in ("png", "webp"):
        return fmt
    return "png" if "A" in img.getbands() else "jpg"


def _size_meta(out_bytes, original_size, **extra):
    return {"original_kb": kb(original_size), "result_kb": kb(len(out_bytes)),
            "saved_percent": round(100 * (1 - len(out_bytes) / original_size), 1)
            if original_size else 0, **extra}


def _image_meta(img, out_bytes, original_size):
    return _image_meta_from_size(img.width, img.height, out_bytes, original_size)


def _image_meta_from_size(width, height, out_bytes, original_size):
    return {**_size_meta(out_bytes, original_size), "width": width, "height": height}
