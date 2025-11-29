import re


def normalize_math_expression(expr: str) -> str:
    if not expr:
        return expr

    expr = expr.strip()

    # توحيد رموز الضرب
    expr = expr.replace("×", "*").replace("·", "*")

    # إزالة bold من LaTeX
    expr = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", expr)

    # إزالة scriptstyle
    expr = expr.replace("\\scriptstyle", "")

    # توحيد المسافات
    expr = re.sub(r"\s+", " ", expr)

    # إزالة الأقواس غير الضرورية
    expr = expr.replace("{", "").replace("}", "")

    return expr.strip()
