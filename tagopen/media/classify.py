"""Classify Slack/local files into image / text / binary document."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
}
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".py",
    ".toml",
    ".ini",
    ".cfg",
    ".log",
    ".rst",
}
# Never blind-UTF8-inline these even if mislabeled
BINARY_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".rar",
    ".mp3",
    ".mp4",
    ".mov",
    ".wav",
    ".ogg",
}


@dataclass(frozen=True)
class ClassifiedKind:
    kind: str  # image | text | binary
    mime: str
    extension: str


def classify_file(
    *,
    filename: str,
    mimetype: str = "",
    magic_prefix: bytes | None = None,
) -> ClassifiedKind:
    name = (filename or "file").strip() or "file"
    ext = Path(name).suffix.lower()
    mime = (mimetype or "").lower().strip()

    if magic_prefix:
        if magic_prefix.startswith(b"%PDF"):
            return ClassifiedKind("binary", mime or "application/pdf", ext or ".pdf")
        if magic_prefix.startswith(b"PK"):
            # zip-based office — treat as binary
            if ext in {".docx", ".xlsx", ".pptx"} or "officedocument" in mime:
                return ClassifiedKind("binary", mime or "application/zip", ext)

    if mime.startswith("image/") or ext in IMAGE_EXTENSIONS:
        return ClassifiedKind("image", mime or f"image/{ext.lstrip('.') or 'png'}", ext)

    if ext in BINARY_EXTENSIONS or "pdf" in mime or "officedocument" in mime or "msword" in mime:
        return ClassifiedKind("binary", mime or "application/octet-stream", ext)

    if mime.startswith("text/") or ext in TEXT_EXTENSIONS or mime in {
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "application/javascript",
    }:
        return ClassifiedKind("text", mime or "text/plain", ext)

    # Unknown: prefer binary path note over risking garbage inline
    return ClassifiedKind("binary", mime or "application/octet-stream", ext)
