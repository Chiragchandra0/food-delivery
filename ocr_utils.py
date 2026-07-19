"""
ocr_utils.py
------------
OCR support via pytesseract (a wrapper around the Tesseract engine).
Used to scan the captured images for a 9-digit code, which - if found -
becomes part of the saved filename.

NOTE: Tesseract itself is a separate binary, not a Python package.
Install it first:
  Windows : https://github.com/UB-Mannheim/tesseract/wiki
  macOS   : brew install tesseract
  Linux   : sudo apt install tesseract-ocr

If it's not on your PATH (common on Windows), set the path explicitly:
  pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
"""

import re

import pytesseract
from PIL import Image

# Uncomment and edit if tesseract is not found automatically on Windows:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

NINE_DIGIT_PATTERN = re.compile(r"\b\d{9}\b")


class OCRError(Exception):
    pass


def extract_text(image_path):
    """Run OCR on an image and return the raw extracted text."""
    try:
        with Image.open(image_path) as img:
            return pytesseract.image_to_string(img)
    except pytesseract.TesseractNotFoundError:
        raise OCRError(
            "Tesseract engine not found. Install it and, on Windows, set "
            "pytesseract.pytesseract.tesseract_cmd to its install path."
        )
    except Exception as e:
        raise OCRError(f"OCR failed on '{image_path}': {e}")


def find_nine_digit_code(image_path):
    """Return the first standalone 9-digit number found in the image's text, or None."""
    text = extract_text(image_path)
    match = NINE_DIGIT_PATTERN.search(text)
    return match.group(0) if match else None
