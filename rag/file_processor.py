import io
import os
import pdfplumber
from google.cloud import vision


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
