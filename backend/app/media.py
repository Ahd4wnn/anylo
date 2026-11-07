"""Safe image storage: Pillow decode (rejects non-images), strip metadata, re-encode to WebP."""

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.errors import AppError

MAX_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard


def root() -> Path:
    return Path(get_settings().media_root).resolve()


def save_image(data: bytes, rel_path: str, max_side: int) -> str:
    if len(data) > MAX_BYTES:
        raise AppError("media.too_large", "Image must be 5 MB or smaller.", 413)
    try:
        Image.open(io.BytesIO(data)).verify()
        src = Image.open(io.BytesIO(data))
        if src.format not in {"JPEG", "PNG", "WEBP"}:
            raise AppError("media.bad_type", "Upload a JPG, PNG or WebP image.", 415)
        img = src.convert("RGBA" if src.mode in ("RGBA", "LA", "P") else "RGB")
        img.thumbnail((max_side, max_side))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise AppError("media.bad_type", "Upload a JPG, PNG or WebP image.", 415) from None
    target = (root() / rel_path).resolve()
    if root() not in target.parents:  # path traversal guard
        raise AppError("media.bad_path", "Invalid file path.", 400)
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target, "WEBP", quality=88, method=6)
    return rel_path


def delete(rel_path: str | None) -> None:
    if rel_path:
        target = (root() / rel_path).resolve()
        if root() in target.parents:
            target.unlink(missing_ok=True)


def url(rel_path: str | None) -> str | None:
    return f"{get_settings().public_api_url}/media/{rel_path}" if rel_path else None
