import io
import os
import pdfplumber
from google.cloud import vision

from .math_ocr import image_to_latex  # ✅ من ملف math_ocr.py

# ✅ تهيئة عميل Google Vision مرة واحدة
vision_client = vision.ImageAnnotatorClient()


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


def extract_rich_from_image_google(file_bytes: bytes, enable_math: bool = True):
    """
    يدمج:
    - نص Google Vision
    - معادلة LaTeX من pix2tex (إن وجدت)

    ويُرجع:
    {
      "text": ...  (نص GCV)
      "latex": ... (معادلة إن وُجدت)
      "merged": ... (نص موحّد يُستخدم مع RAG/Grading)
    }
    """
    # نص عام من Google Vision
    text = extract_text_from_image_google(file_bytes)

    latex = None
    if enable_math:
        try:
            latex = image_to_latex(file_bytes)
        except Exception as e:
            # لو فشل pix2tex لا نوقف البايبلاين
            print("pix2tex error:", e)
            latex = None

    merged = text or ""

    # نضيف LaTeX فقط لو يبدو معادلة معقولة
    if latex and len(latex) > 2:
        if merged:
            merged += "\n\n[معادلة LaTeX]: " + latex
        else:
            merged = "[معادلة LaTeX]: " + latex

    return {
        "text": text,
        "latex": latex,
        "merged": merged,
    }
