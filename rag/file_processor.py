import io
import os
import pdfplumber
from google.cloud import vision
import re

from .math_ocr import image_to_latex  # ✅ من ملف math_ocr.py
from .math_normalizer import normalize_math_expression
from .semantic_corrector import semantic_correct
from .symbol_corrector import correct_latex_with_vision

# ✅ تهيئة عميل Google Vision مرة واحدة
vision_client = vision.ImageAnnotatorClient()


MATH_PATTERNS = [
    r"[=+\-*/^]",
    r"\b\d+[a-zA-Z]\b",     # مثل 2x
    r"[a-zA-Z]\d+",         # مثل x2
    r"\b(sin|cos|tan|log|ln)\b",
    r"√",
]


def has_math_expression(text: str) -> bool:
    if not text:
        return False

    for pattern in MATH_PATTERNS:
        if re.search(pattern, text):
            return True

    return False


def extract_text_from_image_google(file_bytes: bytes) -> str:
    image = vision.Image(content=file_bytes)

    response = vision_client.text_detection(image=image)
    if response.error.message:
        raise RuntimeError(response.error.message)

    texts = response.text_annotations
    if not texts:
        return ""

    # ✅ أول عنصر يحتوي النص الكامل
    return texts[0].description.strip()


def extract_text_from_pdf_google(file_bytes: bytes) -> str:
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def extract_rich_from_image_google(file_bytes: bytes):
    """
    يقرر تلقائيًا:
    - هل يوجد معادلة؟
    - هل نحتاج pix2tex أو لا؟

    ويُرجع:
    {
      "text": ...       (نص Google Vision)
      "latex": ...      (معادلة إن وُجدت)
      "merged": ...     (نص موحد)
      "detected_type": "text" | "math" | "mixed"
      "used_pix2tex": True | False
    }
    """

    # ✅ المرحلة 1: نستخرج النص عادي من Google Vision
    text = extract_text_from_image_google(file_bytes)

    # ✅ المرحلة 2: نقرر هل يوجد مؤشرات رياضية
    contains_math = has_math_expression(text)

    latex = None
    used_pix2tex = False

    # ✅ المرحلة 3: نستدعي pix2tex فقط إذا فعلاً يوجد مؤشر رياضي
    if contains_math:
        try:
            raw_latex = image_to_latex(file_bytes)

            latex_step_1 = normalize_math_expression(raw_latex)
            latex_step_2 = semantic_correct(latex_step_1, text)
            latex_step_3 = correct_latex_with_vision(latex_step_2, text)

            latex = latex_step_3

            used_pix2tex = True
        except Exception as e:
            print("pix2tex error:", e)
            latex = None

    # ✅ المرحلة 4: تحديد نوع المحتوى
    if text and latex:
        detected_type = "mixed"
    elif latex:
        detected_type = "math"
    else:
        detected_type = "text"

    # ✅ المرحلة 5: الدمج النهائي
    merged = text.strip() if text else ""

    if latex and len(latex) > 2:
        if merged:
            merged += "\n\n[معادلة LaTeX]: " + latex
        else:
            merged = "[معادلة LaTeX]: " + latex

    return {
        "text": text,
        "latex": latex,
        "merged": merged,
        "detected_type": detected_type,
        "used_pix2tex": used_pix2tex,
    }
