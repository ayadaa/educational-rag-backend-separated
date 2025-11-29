import re
from typing import List, Dict, Any, Optional
import sympy as sp
from sympy import symbols
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)


def _normalize_step_str(s: str) -> str:
    """
    تطبيع بسيط لنص المعادلة:
    - إزالة المسافات الزائدة
    - استبدال ^ بـ **
    """
    s = s.strip()
    s = s.replace("^", "**")
    s = re.sub(r"\s+", " ", s)
    return s


# ✅ تفعيل الضرب الضمني: 2x → 2*x
TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)

# ✅ رموز شائعة في الرياضيات والفيزياء
COMMON_SYMBOLS = symbols("x y z a b c v u t m F P E I V R g s")


def _parse_equation(s: str) -> Optional[sp.Eq]:
    """
    نسخة متقدمة:
    - تدعم 2x → 2*x
    - تدعم رموز فيزيائية
    - تتحمل مسافات غير منتظمة
    """

    s = _normalize_step_str(s)

    if "=" not in s:
        return None

    left, right = s.split("=", 1)

    try:
        lhs = parse_expr(
            left,
            transformations=TRANSFORMATIONS,
            local_dict={str(sym): sym for sym in COMMON_SYMBOLS},
        )
        rhs = parse_expr(
            right,
            transformations=TRANSFORMATIONS,
            local_dict={str(sym): sym for sym in COMMON_SYMBOLS},
        )
        return sp.Eq(lhs, rhs)
    except Exception as e:
        print("Parse Error:", s, "->", e)
        return None


def _detect_main_symbol(steps: List[str]) -> Optional[sp.Symbol]:
    """
    يحدد المتغير الأساسي تلقائيًا من جميع الخطوات
    """

    for s in steps:
        eq = _parse_equation(s)
        if eq is not None and eq.free_symbols:
            # نأخذ أول متغيّر حقيقي
            for sym in eq.free_symbols:
                return sym

    return None


def _solutions_for_eq(eq: sp.Eq, var: sp.Symbol) -> List[sp.Expr]:
    try:
        sols = sp.solve(eq, var)
        # تحويل الأعداد العشرية/الجذور لأبسط شكل للمقارنة
        return [sp.simplify(sol) for sol in sols]
    except Exception:
        return []


class MathStepGrader:
    """
    مصحح رياضي خطوة بخطوة:
    - يأخذ خطوات الطالب
    - يحاول أن يرى أي خطوة تبدأ فيها المعادلات تصبح غير متوافقة مع الحل الصحيح
    """

    def __init__(self):
        pass

    def grade_steps(
        self,
        question: str,
        student_steps: List[str],
        correct_answer: str,
    ) -> Dict[str, Any]:
        """
        :param question: نص السؤال (اختياري للتحليل أو العرض)
        :param student_steps: قائمة بخطوات الطالب كمعادلات، كل سطر خطوة.
        :param correct_answer: مثل 'x = 2' أو 'v = u + a*t'
        """

        # 1) نحاول استخراج المعادلة النهائية الصحيحة من correct_answer
        correct_eq = _parse_equation(correct_answer)
        if correct_eq is None:
            return {
                "success": False,
                "error": "لم أستطع فهم الصيغة الصحيحة (correct_answer) كمعادلة.",
            }

        # 2) نكتشف المتغير الرئيسي
        main_var = _detect_main_symbol(student_steps + [correct_answer])
        if main_var is None:
            return {
                "success": False,
                "error": "لم أستطع تحديد المتغير الرئيسي في المعادلة.",
            }

        # 3) نحسب حلول المعادلة الصحيحة
        correct_solutions = _solutions_for_eq(correct_eq, main_var)

        step_results = []
        first_wrong_index = None

        for idx, step in enumerate(student_steps):
            eq = _parse_equation(step)
            if eq is None:
                step_results.append(
                    {
                        "index": idx,
                        "step": step,
                        "is_valid": False,
                        "reason": "لم أتمكن من فهم هذه الخطوة كمعادلة صالحة.",
                    }
                )
                if first_wrong_index is None:
                    first_wrong_index = idx
                continue

            # نختبر: هل حلول هذه المعادلة تحتوي على الحل الصحيح؟
            if not correct_solutions:
                # لو ما عرفنا نحل المعادلة الصحيحة أصلاً
                is_valid = True
                reason = "تم قبول الخطوة (تعذر حساب الحل الصحيح للمقارنة)."
            else:
                try:
                    step_solutions = _solutions_for_eq(eq, main_var)
                    # لو أي من حلول correct_solutions غير متوافق مع هذه الخطوة → الخطأ هنا
                    consistent = True
                    for sol in correct_solutions:
                        # نعوض هذا الحل في المعادلة الحالية
                        if not sp.simplify(eq.lhs.subs(main_var, sol) - eq.rhs.subs(main_var, sol)) == 0:
                            consistent = False
                            break

                    is_valid = consistent
                    reason = (
                        "خطوة صحيحة ومتوافقة مع الحل الصحيح."
                        if consistent
                        else "هذه الخطوة غير متوافقة مع الحل الصحيح (تمثل معادلة خاطئة)."
                    )
                except Exception:
                    is_valid = False
                    reason = "تعذر التحقق من صحة هذه الخطوة."

            if not is_valid and first_wrong_index is None:
                first_wrong_index = idx

            step_results.append(
                {
                    "index": idx,
                    "step": step,
                    "is_valid": is_valid,
                    "reason": reason,
                }
            )

        # 4) التحقق من الخطوة النهائية: هل تعطي نفس الحل النهائي؟
        final_correct = False
        if student_steps:
            last_eq = _parse_equation(student_steps[-1])
            if last_eq is not None and correct_solutions:
                # نتحقق أن كل حل صحيح يحقق معادلة الطالب الأخيرة
                try:
                    ok_all = True
                    for sol in correct_solutions:
                        if last_eq.lhs.subs(main_var, sol) - last_eq.rhs.subs(main_var, sol) != 0:
                            ok_all = False
                            break
                    final_correct = ok_all
                except Exception:
                    final_correct = False

        # 5) حساب درجة تقريبية:
        # - كل خطوة صحيحة تأخذ نقاط
        # - لو الخطوة النهائية صحيحة، نزيد مكافأة
        if not step_results:
            score = 0
        else:
            valid_count = sum(1 for r in step_results if r["is_valid"])
            base = (valid_count / len(step_results)) * 80  # 80% للخطوات
            bonus = 20 if final_correct else 0            # 20% للحل النهائي
            score = round(base + bonus, 2)

        return {
            "success": True,
            "question": question,
            "correct_answer": correct_answer,
            "variable": str(main_var),
            "steps": step_results,
            "first_wrong_step_index": first_wrong_index,
            "final_correct": final_correct,
            "score": score,
        }
