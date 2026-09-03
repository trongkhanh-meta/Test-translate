"""OCR for image-only PDF pages (scanned documents with no text layer).

The rest of pdf2zh works on the PDF's existing text objects; when pdfminer
finds none on a page, translation has always been skipped there (see
``pdf2zh.rules.is_scanned_page`` and the "There is no OCR" note in
SKILL.md). This module fills that gap: it rasterizes the page, runs
Tesseract to recover each line of text and its position, translates every
line through the same translator engine used for every other page (so the
medical glossary and cache both apply automatically), then draws the result
back at that exact position -- covering the original pixels with a white
rectangle first, the same trick the existing scanned-page path in
``TranslateConverter`` already uses for pages that had a *hidden* text layer
under an image.

This is a fundamentally different guarantee from the rest of the engine.
The main converter repositions real glyphs it extracted from the PDF itself,
so layout is exact by construction. Here the "layout" is Tesseract's guess
at where a line sat in a rasterized image, and the translated Vietnamese
line is fit into that box by shrinking a font, not by any true relayout --
so it approximates the original position and size rather than reproducing
it exactly, especially where the translation runs noticeably longer than
the source.

Requires the Tesseract OCR engine on PATH (or pointed to via
``pytesseract.pytesseract.tesseract_cmd``, which the packaged desktop app
sets at startup). Tesseract is a native binary; pip can only install the
``pytesseract`` wrapper around it. See README.md for installation notes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 300 DPI is the common floor for reliable OCR on typeset or scanned
# documents; thin serifs and Vietnamese diacritics start dropping below it.
OCR_DPI = 300

# Below this Tesseract word-confidence (0-100), a detection is more often
# noise -- stray marks, table rules, watermarks -- than real text worth
# covering and retranslating.
MIN_WORD_CONFIDENCE = 40

# Never shrink translated text past this size trying to fit a box; a fully
# unfit line is left at floor size rather than shrinking to unreadable.
MIN_FONT_SIZE = 4.0
FONT_SIZE_STEP = 0.5
LINE_HEIGHT_FACTOR = 1.15

# App language codes (as used throughout pdf2zh) -> Tesseract's 3-letter
# trained-data codes. "auto" and anything unlisted fall back to English,
# which covers the large majority of source scans this app sees; extend
# this table as other source languages come up.
_TESSERACT_LANG = {
    "en": "eng", "vi": "vie", "fr": "fra", "de": "deu", "es": "spa",
    "it": "ita", "pt": "por", "nl": "nld", "pl": "pol", "cs": "ces",
    "sv": "swe", "da": "dan", "no": "nor", "fi": "fin", "tr": "tur",
    "ro": "ron", "hu": "hun", "id": "ind",
}


def tesseract_language(lang_in: str) -> str:
    """Best-effort Tesseract language code for the app's ``lang_in`` value."""
    return _TESSERACT_LANG.get((lang_in or "").strip().lower(), "eng")


@dataclass(frozen=True)
class OcrLine:
    """One OCR'd line: its text and page-point rectangle.

    ``rect`` is (x0, y0, x1, y1) in PDF page points with a top-left origin,
    matching both a rasterized image's pixel coordinates and pymupdf's
    Page/Rect convention -- no axis flip is needed between the two.
    """

    text: str
    rect: tuple[float, float, float, float]


def _import_pytesseract():
    try:
        import pytesseract
    except ImportError as error:
        raise RuntimeError(
            "OCR mode needs the 'pytesseract' package: pip install pytesseract. "
            "It also needs the Tesseract OCR engine itself installed separately "
            "and on PATH -- pytesseract only wraps the 'tesseract' binary, it "
            "does not include it."
        ) from error
    return pytesseract


def page_needs_ocr(page: Any) -> bool:
    """True when a page has no extractable text but does have image content."""
    if page.get_text("text").strip():
        return False
    return bool(page.get_images(full=True))


def detect_ocr_pages(doc: Any, pages: list[int] | None) -> set[int]:
    """Which pages (within ``pages``, or all pages if it is None) need OCR."""
    indices = range(doc.page_count) if pages is None else pages
    return {
        pageno
        for pageno in indices
        if 0 <= pageno < doc.page_count and page_needs_ocr(doc[pageno])
    }


def _extract_lines(page: Any, lang_in: str) -> list[OcrLine]:
    pytesseract = _import_pytesseract()
    from PIL import Image

    pix = page.get_pixmap(dpi=OCR_DPI)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    try:
        data = pytesseract.image_to_data(
            image,
            lang=tesseract_language(lang_in),
            output_type=pytesseract.Output.DICT,
        )
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError(
            "Tesseract OCR engine not found on PATH. Install it separately from "
            "pytesseract and make sure the 'tesseract' command is reachable "
            "(see README.md for platform-specific instructions)."
        ) from error

    scale = 72.0 / OCR_DPI  # pixels at OCR_DPI -> PDF points
    grouped: dict[tuple[int, int, int], list[tuple[int, int, int, int, str]]] = {}
    count = len(data.get("text", []))
    for i in range(count):
        text = data["text"][i].strip()
        try:
            confidence = float(data["conf"][i])
        except (TypeError, ValueError):
            confidence = -1.0
        if not text or confidence < MIN_WORD_CONFIDENCE:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        left, top = data["left"][i], data["top"][i]
        width, height = data["width"][i], data["height"][i]
        grouped.setdefault(key, []).append((left, top, left + width, top + height, text))

    lines: list[OcrLine] = []
    for words in grouped.values():
        words.sort(key=lambda word: word[0])
        x0 = min(word[0] for word in words) * scale
        y0 = min(word[1] for word in words) * scale
        x1 = max(word[2] for word in words) * scale
        y1 = max(word[3] for word in words) * scale
        text = " ".join(word[4] for word in words)
        lines.append(OcrLine(text=text, rect=(x0, y0, x1, y1)))
    return lines


def fit_font_size(
    rect: Any, text: str, font_path: str, fontname: str, start_size: float
) -> float:
    """Largest size (down to ``MIN_FONT_SIZE``) at which ``text`` fits ``rect`` whole.

    pymupdf's ``insert_textbox`` draws the *entire* passed text or nothing at
    all -- if even the first line does not fit, it silently draws nothing
    rather than truncating -- so there is no way to know from font metrics
    alone whether a given size will fit; its own line-height and internal
    margins are not reproducible from ``pymupdf.Font`` measurements. This
    checks the real thing on a small throwaway page/document per candidate
    size, which is discarded immediately after reading back the fit result;
    the caller's real page is never touched by this search.
    """
    import pymupdf

    probe_rect = pymupdf.Rect(0, 0, max(rect.width, 1.0), max(rect.height, 1.0))
    size = max(start_size, MIN_FONT_SIZE)
    while size > MIN_FONT_SIZE:
        scratch_doc = pymupdf.open()
        try:
            scratch_page = scratch_doc.new_page(
                width=probe_rect.width, height=probe_rect.height
            )
            overflow = scratch_page.insert_textbox(
                probe_rect,
                text,
                fontsize=size,
                fontname=fontname,
                fontfile=font_path,
                align=pymupdf.TEXT_ALIGN_LEFT,
            )
        finally:
            scratch_doc.close()
        if overflow >= 0:
            return size
        size -= FONT_SIZE_STEP
    return MIN_FONT_SIZE


def apply_ocr_translation(
    doc: Any,
    pages: set[int],
    translator: Any,
    font_path: str,
) -> list[str]:
    """Translate every OCR-needed page of ``doc`` in place (mutates pages).

    Returns the OCR'd line texts that could not be translated, so the caller
    can fold them into the same "left in source language" accounting the
    rest of the pipeline already reports.
    """
    import pymupdf

    lang_in = getattr(translator, "lang_in", "")
    fontname = "pdf2zh-ocr-vi"
    failures: list[str] = []

    for pageno in sorted(pages):
        page = doc[pageno]
        try:
            lines = _extract_lines(page, lang_in)
        except RuntimeError:
            raise  # missing tesseract/pytesseract is a setup problem, not a per-page one
        except Exception as error:  # noqa: BLE001 - one bad page must not abort the run
            logger.warning("OCR failed on page %d: %s", pageno, error)
            continue

        for line in lines:
            rect = pymupdf.Rect(line.rect)
            try:
                translated = translator.translate(line.text)
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "Could not translate OCR text on page %d: %s", pageno, error
                )
                failures.append(line.text)
                continue
            if not translated or translated == line.text:
                continue

            pad = 1.5
            cover = pymupdf.Rect(
                rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad
            )
            page.draw_rect(cover, color=None, fill=(1, 1, 1), fill_opacity=1)

            starting_size = max(6.0, (rect.y1 - rect.y0) * 0.8)
            size = fit_font_size(rect, translated, font_path, fontname, starting_size)
            overflow = page.insert_textbox(
                rect,
                translated,
                fontsize=size,
                fontname=fontname,
                fontfile=font_path,
                align=pymupdf.TEXT_ALIGN_LEFT,
            )
            if overflow < 0:
                # Even MIN_FONT_SIZE does not fit the OCR'd line's original
                # box -- the translation ran much longer than the source, a
                # common EN->VI gap. Grow the box downward instead of
                # silently losing the line; some overlap with content below
                # is preferable to a translation that vanishes outright.
                grown = pymupdf.Rect(
                    rect.x0, rect.y0, rect.x1, rect.y1 + 4 * max(rect.height, 1.0)
                )
                page.insert_textbox(
                    grown,
                    translated,
                    fontsize=size,
                    fontname=fontname,
                    fontfile=font_path,
                    align=pymupdf.TEXT_ALIGN_LEFT,
                )

    return failures
