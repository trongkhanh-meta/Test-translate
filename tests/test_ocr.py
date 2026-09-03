from __future__ import annotations

import io
import unittest
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageDraw, ImageFont

from pdf2zh.ocr import (
    apply_ocr_translation,
    detect_ocr_pages,
    fit_font_size,
    page_needs_ocr,
    tesseract_language,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BODY_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
VI_FONT = str(REPO_ROOT / "app" / "fonts" / "BeVietnamPro-Regular.ttf")

TESSERACT_AVAILABLE = True
try:
    pytesseract.get_tesseract_version()
except Exception:  # noqa: BLE001
    TESSERACT_AVAILABLE = False


def _scanned_pdf_bytes(lines: list[str]) -> bytes:
    """Build a one-page PDF whose only content is a rendered image (no text layer),
    the same shape as a raw scan: a photographed or scanned page with nothing
    pdfminer can extract.
    """
    width, height = 1000, 400
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(BODY_FONT, 32)
    y = 40
    for line in lines:
        draw.text((60, y), line, fill="black", font=font)
        y += 60

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(pymupdf.Rect(0, 0, width, height), stream=buffer.getvalue())
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


class FakeTranslator:
    """Deterministic stand-in for GoogleTranslator: no network in tests."""

    lang_in = "en"

    def __init__(self, table: dict[str, str]):
        self.table = table
        self.calls: list[str] = []

    def translate(self, text: str) -> str:
        self.calls.append(text)
        return self.table.get(text, text)


@unittest.skipUnless(TESSERACT_AVAILABLE, "tesseract binary not installed")
class OcrPipelineTests(unittest.TestCase):
    def test_page_needs_ocr_true_for_image_only_page(self):
        pdf_bytes = _scanned_pdf_bytes(["Range of motion exercises"])
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        self.assertTrue(page_needs_ocr(doc[0]))
        self.assertEqual(detect_ocr_pages(doc, None), {0})
        doc.close()

    def test_page_needs_ocr_false_for_a_normal_text_page(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "This page already has a real text layer.")
        self.assertFalse(page_needs_ocr(page))
        self.assertEqual(detect_ocr_pages(doc, None), set())
        doc.close()

    def test_extracts_and_translates_ocr_text_in_place(self):
        pdf_bytes = _scanned_pdf_bytes(
            ["Increase range of motion", "twice a day for two weeks"]
        )
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        translator = FakeTranslator(
            {
                "Increase range of motion": "Tăng tầm vận động",
                "twice a day for two weeks": "hai lần một ngày trong hai tuần",
            }
        )

        failures = apply_ocr_translation(doc, {0}, translator, VI_FONT)

        self.assertEqual(failures, [])
        rendered = doc[0].get_text("text")
        self.assertIn("Tăng tầm vận động", rendered)
        self.assertIn("hai lần một ngày trong hai tuần", rendered)
        # The English source words should no longer be visible text on the
        # page: they were covered by a white rectangle before the
        # Vietnamese line was drawn over the same spot.
        self.assertNotIn("Increase", rendered)
        self.assertNotIn("twice a day", rendered)
        doc.close()

    def test_a_line_the_translator_cannot_handle_is_reported_as_a_failure(self):
        pdf_bytes = _scanned_pdf_bytes(["Untranslatable clinical jargon"])
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

        class BrokenTranslator:
            lang_in = "en"

            def translate(self, text: str) -> str:
                raise RuntimeError("network unavailable")

        failures = apply_ocr_translation(doc, {0}, BrokenTranslator(), VI_FONT)
        self.assertEqual(len(failures), 1)
        doc.close()


class TesseractLanguageMappingTests(unittest.TestCase):
    def test_known_language_maps_to_three_letter_code(self):
        self.assertEqual(tesseract_language("en"), "eng")
        self.assertEqual(tesseract_language("EN"), "eng")

    def test_unknown_or_auto_falls_back_to_english(self):
        self.assertEqual(tesseract_language("auto"), "eng")
        self.assertEqual(tesseract_language(""), "eng")
        self.assertEqual(tesseract_language("xx"), "eng")


class FitFontSizeTests(unittest.TestCase):
    def test_short_text_keeps_the_starting_size(self):
        rect = pymupdf.Rect(0, 0, 300, 40)
        size = fit_font_size(rect, "Ngắn gọn", VI_FONT, "vi-test", 14)
        self.assertEqual(size, 14)

    def test_shrinks_to_make_a_long_line_fit_a_short_box(self):
        rect = pymupdf.Rect(0, 0, 300, 30)
        long_text = (
            "Đây là một đoạn văn bản dịch khá dài cần được thu nhỏ cho vừa khung hẹp"
        )
        size = fit_font_size(rect, long_text, VI_FONT, "vi-test", 24)
        self.assertLess(size, 24)
        # The chosen size must actually work when drawn for real.
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=200)
        overflow = page.insert_textbox(
            pymupdf.Rect(10, 10, 310, 40),
            long_text,
            fontsize=size,
            fontname="vi-test",
            fontfile=VI_FONT,
            align=pymupdf.TEXT_ALIGN_LEFT,
        )
        self.assertGreaterEqual(overflow, 0)
        doc.close()

    def test_never_returns_below_the_floor_size(self):
        from pdf2zh.ocr import MIN_FONT_SIZE

        rect = pymupdf.Rect(0, 0, 20, 10)
        size = fit_font_size(rect, "x" * 500, VI_FONT, "vi-test", 14)
        self.assertGreaterEqual(size, MIN_FONT_SIZE)


if __name__ == "__main__":
    unittest.main()
