import requests
from .config import GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL_NAME


class GroqClient:
    def generate(self, system_prompt, user_prompt):
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": GROQ_MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3
        }

        res = requests.post(GROQ_API_URL, headers=headers, json=payload)

        # ✅ اطبع الخطأ الحقيقي إن حصل
        if res.status_code != 200:
            print("❌ Groq Error Status:", res.status_code)
            print("❌ Groq Error Body:", res.text)
            return "❌ حدث خطأ من مزود الذكاء الاصطناعي (Groq). تحقق من الإعدادات أو الموديل."

        data = res.json()

        # ✅ حماية من KeyError
        if "choices" not in data:
            print("❌ Unexpected Groq Response:", data)
            return "❌ استجابة غير متوقعة من Groq. تحقق من الموديل أو الصلاحيات."

        return data["choices"][0]["message"]["content"]
