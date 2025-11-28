import json
from typing import Any, Dict

from .groq_client import GroqClient

EXAM_SYSTEM_PROMPT = """
أنت منشئ امتحانات ذكي لمادة دراسية لطلاب المدارس.

المطلوب:
- توليد أسئلة امتحان لمادة معيّنة (مثل فيزياء) وصف معيّن (مثل السادس).
- ادمج بين:
  - أسئلة اختيار من متعدد (mcq)
  - أسئلة مفتوحة (open) لشرح أو حل قصير

صيغة الإخراج (JSON فقط) يجب أن تكون بالشكل التالي:

{
  "questions": [
    {
      "id": 1,
      "type": "mcq",
      "question": "نص السؤال هنا...",
      "options": ["خيار 1", "خيار 2", "خيار 3", "خيار 4"],
      "correct_option_index": 1,
      "model_answer": "النص النموذجي للإجابة (يمكن أن يشرح السبب بإيجاز)"
    },
    {
      "id": 2,
      "type": "open",
      "question": "نص سؤال مفتوح هنا...",
      "model_answer": "الإجابة النموذجية الكاملة للسؤال المفتوح"
    }
  ]
}

ملاحظات مهمة:
- لا تضف أي نص خارج JSON.
- استخدم "mcq" و "open" فقط في حقل type.
- الأسئلة يجب أن تكون مناسبة للمستوى الدراسي المعطى.
"""


class ExamEngine:
    def __init__(self):
        self.llm = GroqClient()

    def generate_exam(self, subject: str, grade: str, num_questions: int = 5) -> Dict[str, Any]:
        """
        توليد امتحان مكوّن من num_questions سؤال (مزيج بين mcq و open)
        """
        user_prompt = f"""
المادة: {subject}
الصف: {grade}
عدد الأسئلة المطلوب تقريباً: {num_questions}

أنشئ أسئلة امتحان مناسبة للمستوى، تتناول أهم المفاهيم في هذه المادة وهذا الصف.
"""

        raw = self.llm.generate(EXAM_SYSTEM_PROMPT, user_prompt)

        try:
            data = json.loads(raw)
            # ضمان وجود questions
            if "questions" not in data or not isinstance(data["questions"], list):
                raise ValueError("Invalid exam JSON: 'questions' missing or not a list")
            return data
        except Exception as e:
            # في حال فشل التحليل، نرجع شكل بسيط مع الخطأ للمساعدة في التصحيح
            return {
                "questions": [],
                "error": str(e),
                "raw_output": raw
            }
