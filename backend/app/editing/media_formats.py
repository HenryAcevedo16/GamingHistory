"""Standalone media formats accepted by the browser uploader."""

FORMATS = {
    ".mp4": "mov", ".mov": "mov", ".m4v": "mov", ".m4a": "mov",
    ".mkv": "matroska", ".webm": "matroska", ".avi": "avi",
    ".mp3": "mp3", ".wav": "wav", ".flac": "flac", ".ogg": "ogg", ".opus": "ogg",
    ".png": "png_pipe", ".jpg": "jpeg_pipe", ".jpeg": "jpeg_pipe",
    ".webp": "webp_pipe", ".bmp": "bmp_pipe",
}

IMAGE_EXTENSIONS = frozenset(ext for ext, demuxer in FORMATS.items() if demuxer.endswith("_pipe"))
