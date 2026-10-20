import os
import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract

# Windows default install path; on other systems Tesseract is found on PATH
_WIN_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_WIN_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = _WIN_TESSERACT

# If a PDF page has fewer characters than this, we treat it as a scan and use OCR
MIN_TEXT_CHARS = 50


def _remove_table_lines(binary_inv: np.ndarray) -> np.ndarray:
    """binary_inv has white text/lines on black. Subtract long horizontal and vertical
    lines, because table borders make Tesseract skip rows and invent stray characters."""
    h, w = binary_inv.shape
    horiz = cv2.morphologyEx(
        binary_inv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 25), 1))
    )
    vert = cv2.morphologyEx(
        binary_inv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, h // 60)))
    )
    lines = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8))
    return cv2.bitwise_and(binary_inv, cv2.bitwise_not(lines))


def _flatten_lighting(gray: np.ndarray) -> np.ndarray:
    """Removes shadows and uneven lighting: estimate the paper colour (text removed, then blurred)
    and divide the image by it, so the paper becomes evenly white."""
    background = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25)))
    background = cv2.GaussianBlur(background, (0, 0), 25)
    return cv2.divide(gray, background, scale=255)


def _estimate_skew(gray: np.ndarray) -> float:
    """Angle (degrees) that straightens a tilted page. Text lines line up best when the
    rows of the page have the most uneven ink counts, so we try angles and keep the best."""
    h, w = gray.shape
    scale = 700 / w
    small = cv2.resize(gray, (700, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    _, inv = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    sh, sw = inv.shape

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D((sw / 2, sh / 2), angle, 1.0)
        rotated = cv2.warpAffine(inv, m, (sw, sh))
        return float(np.var(rotated.sum(axis=1, dtype=np.float64)))

    best = max(np.arange(-6.0, 6.01, 0.5), key=score)
    return float(max(np.arange(best - 0.5, best + 0.51, 0.1), key=score))


def _deskew(gray: np.ndarray) -> np.ndarray:
    angle = _estimate_skew(gray)
    if abs(angle) < 0.3:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def preprocess_image(img: np.ndarray) -> np.ndarray:
    """Clean an image so Tesseract reads it more accurately."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    height, width = gray.shape
    if width < 2000:  # Tesseract works best on large, clear text
        scale = 2000 / width
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = _flatten_lighting(gray)
    gray = _deskew(gray)
    _, inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return cv2.bitwise_not(_remove_table_lines(inv))


def clean_ocr_text(text: str) -> str:
    """Repair the typical OCR mistakes so the parser can read the rows."""
    text = re.sub(r"[–—−]", "-", text)  # fancy dashes -> hyphen
    text = re.sub(r"-{2,}", "-", text)  # a dash read twice
    # stray marks left over from table borders, sitting between columns
    text = re.sub(r"(?<=\s)[|;:,.'‘’`~_]+(?=\s)", " ", text)
    # the micro sign is often lost: 'PL', '#L', 'million/ L'
    text = re.sub(r"million\s*/\s*[µuU#]?\s*[Ll]\b", "million/µL", text)
    text = re.sub(r"(?<=\s)[PpU#]L\b", "/µL", text)
    # 'pL' written for '/µL' is unambiguous in blood counts; a space inside a number in a range
    text = re.sub(r"(?<=-)(\d) (\d{1,3},\d{3})", r"\1\2", text)
    return text


def ocr_image(img: np.ndarray) -> str:
    raw = pytesseract.image_to_string(preprocess_image(img), config="--psm 6")
    return clean_ocr_text(raw)


def extract_from_pdf(path: str) -> dict:
    import pymupdf  # imported here so the rest of the module works without it

    doc = pymupdf.open(path)
    pages = []
    methods = set()
    for page in doc:
        text = page.get_text().strip()
        if len(text) >= MIN_TEXT_CHARS:
            methods.add("text")
        else:
            # Scanned page: render it as an image and run OCR
            methods.add("ocr")
            pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            text = ocr_image(img)
        pages.append(text)
    doc.close()
    return {"text": "\n\n".join(pages).strip(), "method": "+".join(sorted(methods))}


def extract_from_image(path: str) -> dict:
    # np.fromfile + imdecode works even if the path has special characters
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not read the image file.")
    return {"text": ocr_image(img).strip(), "method": "ocr"}


def extract_text(path: str) -> dict:
    if Path(path).suffix.lower() == ".pdf":
        return extract_from_pdf(path)
    return extract_from_image(path)