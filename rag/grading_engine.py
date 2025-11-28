import json
from .groq_client import GroqClient

GRADING_SYSTEM_PROMPT = """
أنت مصحح امتحانات ذكي ودقيق.

مهمتك:
- قارن إجابة الطالب بالإجابة النموذجية.
- قيّمها بدقة من 0 إلى 100.
- إن كانت الإجابة صحيحة تمامًا → درجة كاملة.
- إن كانت جزئية → درجة جزئية.
- إن كانت خاطئة → درجة منخفضة.
- أعطِ:
  1) الدرجة النهائية
  2) هل الإجابة صحيحة أم خاطئة؟
  3) شرح مختصر للخطأ أو النقص
  4) التصحيح النموذجي

إن كانت الإجابة تحتوي على حسابات رياضية:
- تأكد من صحة الناتج.
- تأكد أن الخطوات منطقية.

أخرج النتيجة بصيغة JSON فقط بدون أي شرح إضافي.
"""

class GradingEngine:
    def __init__(self):
        self.llm = GroqClient()

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

        # ✅ تحويل النص إلى JSON فعلي
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            return {
                "score": 0,
                "is_correct": False,
                "feedback": "تعذر تحليل نتيجة التصحيح من النموذج.",
                "correct_answer": model_answer,
                "raw_output": result_text
            }
