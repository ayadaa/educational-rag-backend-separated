import requests
from .config import GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL_NAME

class GroqClient:
    def generate(self, system_prompt, user_prompt):
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": GROQ_MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3
        }
        res = requests.post(GROQ_API_URL, headers=headers, json=payload)
        return res.json()["choices"][0]["message"]["content"]
