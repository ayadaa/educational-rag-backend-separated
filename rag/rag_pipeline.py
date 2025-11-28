from .chroma_db import ChromaKnowledgeBase
from .groq_client import GroqClient

SYSTEM_PROMPT = "أنت مدرس افتراضي ذكي تعتمد فقط على السياق."

class RAGPipeline:
    def __init__(self):
        self.db = ChromaKnowledgeBase()
        self.llm = GroqClient()

    def answer(self, question, subject, grade):
        contexts = self.db.query(question, subject, grade)
        context = "\n".join([doc for doc, _ in contexts])
        prompt = f"سؤال: {question}\n\nسياق:\n{context}"
        answer = self.llm.generate(SYSTEM_PROMPT, prompt)
        return answer, [{"text": doc, "metadata": meta} for doc, meta in contexts]
