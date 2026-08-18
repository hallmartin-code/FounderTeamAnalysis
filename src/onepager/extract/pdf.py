"""PDF extraction: pdfplumber for text, PyMuPDF for rasterization."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import pdfplumber

try:  # PyMuPDF renamed its import in 1.24; `fitz` still works but warns.
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz

from ..config import IMAGE_TEXT_THRESHOLD, MAX_VISION_IMAGES, RASTER_DPI, RASTER_MAX_EDGE
from ..util.logging import get_logger
from .types import Deck, ExtractionError, SlideContent

_log = get_logger()


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return None


def extract_pdf_text(path: Path) -> Deck:
    """Text-only pass. Raises ExtractionError for encrypted/corrupt files."""
    deck = Deck(source_path=str(path), source_kind="pdf")
    try:
        with pdfplumber.open(str(path)) as pdf:
            if not pdf.pages:
                raise ExtractionError(f"{path.name} contains zero pages.")
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:  # a single unreadable page should not kill the run
                    _log.warning("page %d text extraction failed (%s); continuing", i, exc)
                    text = ""
                text = text.strip()
                deck.slides.append(
                    SlideContent(index=i, title=_first_line(text), text=text)
                )
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(_diagnose(path, exc)) from exc
    return deck


def _diagnose(path: Path, exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)
    if "password" in msg.lower() or "PDFPasswordIncorrect" in name:
        return f"{path.name} is password-protected or encrypted; supply a decrypted copy."
    if "PDFSyntaxError" in name or "not a PDF" in msg or "startxref" in msg.lower():
        return f"{path.name} is not a readable PDF (file is corrupt or mislabeled)."
    return f"{path.name} could not be opened as a PDF: {name}: {msg}"


def needs_vision(deck: Deck) -> bool:
    return deck.mean_chars < IMAGE_TEXT_THRESHOLD


def rasterize(path: Path, deck: Deck, limit: int = MAX_VISION_IMAGES) -> Deck:
    """Attach base64 PNG page images in place. Only the first `limit` pages."""
    zoom = RASTER_DPI / 72.0
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise ExtractionError(_diagnose(path, exc)) from exc
    try:
        for slide in deck.slides[:limit]:
            page = doc.load_page(slide.index - 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            longest = max(pix.width, pix.height)
            if longest > RASTER_MAX_EDGE:
                shrink = RASTER_MAX_EDGE / longest
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(zoom * shrink, zoom * shrink), alpha=False
                )
            buf = io.BytesIO(pix.tobytes("png"))
            slide.image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    finally:
        doc.close()
    deck.used_vision = True
    if len(deck.slides) > limit:
        deck.notes.append(
            f"rasterized the first {limit} of {len(deck.slides)} pages (vision image cap)"
        )
    return deck


def pdf_to_deck(path: Path, vision: bool | None = None) -> Deck:
    """vision: True=force, False=never, None=auto based on text density."""
    deck = extract_pdf_text(path)
    auto = needs_vision(deck)
    if vision is True or (vision is None and auto):
        if auto:
            deck.notes.append(
                f"mean {deck.mean_chars:.0f} chars/page is below the "
                f"{IMAGE_TEXT_THRESHOLD} threshold; treating as an image-based deck"
            )
        rasterize(path, deck)
    return deck
