import io
from PIL import Image

try:
    from pix2tex.cli import LatexOCR
except ImportError:
    LatexOCR = None


_model = None


def get_latex_ocr_model():
    global _model
    if _model is None:
        if LatexOCR is None:
            raise ImportError("pix2tex غير مثبت. ثبّت الحزمة pix2tex أولاً.")
        # سيستخدم CPU افتراضياً (أو GPU إن وُجد)
        _model = LatexOCR()
    return _model


def image_to_latex(file_bytes: bytes) -> str:
    """
    يحول صورة (معادلة) إلى LaTeX باستخدام pix2tex.
    """
    model = get_latex_ocr_model()
    img = Image.open(io.BytesIO(file_bytes)).convert("L")
    latex_str = model(img)
    return latex_str.strip()
