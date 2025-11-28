import json
from .groq_client import GroqClient

GRADING_SYSTEM_PROMPT = GRADING_SYSTEM_PROMPT = """
أنت مصحح امتحانات ذكي ودقيق.

مهمتك:
- قارن إجابة الطالب بالإجابة النموذجية.
- قيّمها بدقة من 0 إلى 100.
- إن كانت الإجابة صحيحة تمامًا → درجة كاملة.
- إن كانت جزئية → درجة متوسطة.
- إن كانت خاطئة → درجة منخفضة.

❗ مهم جدًا:
يجب أن تُخرج النتيجة بصيغة JSON فقط وبالمفاتيح الإنجليزية التالية فقط ❗❗❗:

{
  "score": 0-100,
  "is_correct": true | false,
  "feedback": "شرح مختصر",
  "correct_answer": "الإجابة النموذجية الصحيحة"
}

❌ ممنوع استخدام مفاتيح عربية.
❌ ممنوع إضافة أي نص خارج JSON.

إن كانت الإجابة تحتوي على حسابات رياضية:
- تحقق من صحة الناتج.
- تحقق من صحة الخطوات.
"""

class GradingEngine:
    def __init__(self):
        self.llm = GroqClient()

    def _normalize_keys(self, data: dict):
        """
        توحيد المفاتيح إن أعادها النموذج بالعربية
        """
        mapping = {
            "درجة_النهاية": "score",
            "الصحيحة_أو_الخاطئة": "is_correct",
            "شرح_الخطأ_أو_النقص": "feedback",
            "التصحيح_النموذجي": "correct_answer"
        }

        normalized = {}
        for k, v in data.items():
            new_key = mapping.get(k, k)
            normalized[new_key] = v

        if "is_correct" in normalized and isinstance(normalized["is_correct"], str):
            normalized["is_correct"] = normalized["is_correct"] in ["صحيحة", "صحيح", "true", "True"]

        return normalized

    def grade(self, question: str, student_answer: str, model_answer: str):
        user_prompt = f"""
سؤال الامتحان:
{question}

إجابة الطالب:
{student_answer}

الإجابة النموذجية:
{model_answer}
"""

        result_text = self.llm.generate(GRADING_SYSTEM_PROMPT, user_prompt)

        try:
            data = json.loads(result_text)
            data = self._normalize_keys(data)

            # ✅ تصحيح is_correct منطقيًا بناءً على الدرجة
            if "score" in data:
                data["is_correct"] = data["score"] >= 50

            return data

        except json.JSONDecodeError:
            return {
                "score": 0,
                "is_correct": False,
                "feedback": "تعذر تحليل نتيجة التصحيح.",
                "correct_answer": model_answer,
                "raw_output": result_text
            }
