"""read_attachment tool — inspect cached inbound files under data/media/."""

from __future__ import annotations

from pathlib import Path

from tagopen.config import settings
from tagopen.media.cache import is_under_media_cache
from tagopen.media.classify import classify_file


def read_attachment(path_str: str, *, max_chars: int = 80_000) -> str:
    """Read or extract text from a cached attachment path (media cache only)."""
    path = Path(path_str).expanduser()
    if not path.is_file():
        return f"File not found: {path_str}"
    if not is_under_media_cache(path):
        return (
            "Path rejected: read_attachment only allows files under "
            f"`{settings.data_dir / 'media'}` (Slack download cache)."
        )

    data = path.read_bytes()
    kind = classify_file(filename=path.name, magic_prefix=data[:16])

    if kind.kind == "image":
        return (
            f"Image file `{path.name}` ({len(data)} bytes) at `{path}`.\n"
            "Pixels were injected on the user turn when the model supports vision; "
            "otherwise a vision_analyze description was added. "
            "Do not call read_attachment for OCR unless needed."
        )

    if kind.kind == "text" or path.suffix.lower() in {".csv", ".tsv", ".json", ".md", ".txt"}:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + f"\n\n…(truncated, {len(text)} chars total)"
        return text

    # PDF / Office — best-effort extractors; no hard dependency
    if path.suffix.lower() == ".pdf" or data[:4] == b"%PDF":
        extracted = _try_pdf_text(path, max_chars=max_chars)
        if extracted:
            return extracted
        return (
            f"PDF at `{path}` ({len(data)} bytes). Text extract unavailable "
            "(install pymupdf or pypdf in the venv). Summarize from filename/context "
            "or ask the user for a text export."
        )

    if path.suffix.lower() in {".xlsx", ".xls", ".csv"}:
        if path.suffix.lower() == ".csv":
            try:
                return data.decode("utf-8")[:max_chars]
            except UnicodeDecodeError:
                pass
        return (
            f"Spreadsheet at `{path}` ({len(data)} bytes). "
            "Use a text/CSV export from the user, or process offline — "
            "in-process Excel parsing is not bundled."
        )

    return (
        f"Binary document `{path.name}` at `{path}` ({len(data)} bytes, "
        f"mime≈{kind.mime}). Cannot inline; ask for a text export or describe "
        "what you need from it."
    )


def _try_pdf_text(path: Path, *, max_chars: int) -> str | None:
    try:
        import fitz  # pymupdf

        doc = fitz.open(path)
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text() or "")
            if sum(len(p) for p in parts) >= max_chars:
                break
        text = "\n".join(parts).strip()
        if not text:
            return None
        if len(text) > max_chars:
            return text[:max_chars] + "\n\n…(truncated)"
        return text
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) >= max_chars:
                break
        text = "\n".join(parts).strip()
        if not text:
            return None
        if len(text) > max_chars:
            return text[:max_chars] + "\n\n…(truncated)"
        return text
    except Exception:
        return None
