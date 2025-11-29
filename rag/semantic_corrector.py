import re


COMMON_SEMANTIC_FIXES = [
    (r"\\Delta", "a"),          # دلتا بدل التسارع
    (r"\bDelta\b", "a"),
    (r"\bO\b", "0"),
    (r"\bl\b", "1"),
    (r"\b×\b", "x"),
    (r"\^2", "²"),
    (r"sqrt", "√"),
]


def semantic_correct(latex: str, vision_text: str) -> str:
    if not latex:
        return latex

    fixed = latex

    for pattern, replacement in COMMON_SEMANTIC_FIXES:
        fixed = re.sub(pattern, replacement, fixed)

    # ✅ لو النص من GCV فيه صيغة أوضح، نرجحه
    vt = vision_text.replace(" ", "")
    fx = fixed.replace(" ", "")

    if len(vt) > 3 and len(fx) > 3 and vt in fx:
        return vt

    return fixed
