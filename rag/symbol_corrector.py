import re


# ✅ خريطة أخطاء شائعة بين OCR و pix2tex
SYMBOL_MAP = {
    "r": "F",
    "×": "x",
    "Δ": "a",
    "l": "1",
    "O": "0",
    "ν": "v",
    "+": "t"
}


def extract_main_equation(text: str) -> str:
    """
    يحاول استخراج معادلة صريحة من نص Google Vision مثل F=ma أو 2x+3=7
    """
    if not text:
        return ""

    # نبحث عن أي شيء فيه =
    matches = re.findall(r"[A-Za-z0-9+\-*/^(). ]+=+[A-Za-z0-9+\-*/^(). ]+", text)

    return matches[0].replace(" ", "") if matches else ""


def correct_latex_with_vision(latex: str, vision_text: str) -> str:
    """
    يصحح رموز LaTeX بالاعتماد على المعادلة المستخرجة من Google Vision
    """
    if not latex or not vision_text:
        return latex

    vision_eq = extract_main_equation(vision_text)
    latex_compact = latex.replace(" ", "").replace("\\", "")

    # ✅ لو GCV أعطى معادلة أوضح نرجّحها مباشرة
    if len(vision_eq) >= 4 and "=" in vision_eq:
        return vision_eq.replace("*", " ")

    # ✅ وإلا نطبّق خريطة التصحيح الرمزي
    corrected = latex

    for wrong, right in SYMBOL_MAP.items():
        corrected = corrected.replace(wrong, right)

    return corrected
