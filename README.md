ممتاز 👌
هذا قرار **احترافي جدًا (Production-Ready)** ✅
وسنحوّل مشروعك إلى **نظام بمرحلتين منفصلتين تمامًا**:

---

# ✅ الهدف النهائي

نفصل:

| المرحلة          | ماذا تفعل                      | متى تُشغَّل      |
| ---------------- | ------------------------------ | ---------------- |
| **1️⃣ Indexing** | توليد بيانات Chroma من الملفات | مرة واحدة يدويًا |
| **2️⃣ API**      | فقط استعلام + توليد إجابة      | دائمًا           |

✅ بهذا:

* لا تُعاد عملية الـ embedding عند كل تشغيل
* تشغيل الـ API يصبح سريع جدًا
* يمكن تحديث البيانات بدون إيقاف السيرفر
* مناسب للإنتاج التجاري

---

# ✅ البنية الجديدة للمشروع

```bash
educational-rag-backend/
├─ main.py                # API فقط ✅
├─ build_index.py         # توليد Chroma فقط ✅✅
├─ requirements.txt
├─ .env
│
├─ rag/
│  ├─ config.py
│  ├─ embeddings.py
│  ├─ chroma_db.py        # بدون build داخل init
│  ├─ groq_client.py
│  ├─ rag_pipeline.py    # لا يبني Index
│
└─ data/
   ├─ physics/grade6/ch1.txt
   └─ ...
```

---

# ✅ 1️⃣ تعديل `rag/chroma_db.py` (حذف البناء التلقائي)

❌ نحذف أي `build_index()` من `__init__`
✅ ونبقيه كدالة مستقلة فقط.

استبدل ملف:

```
rag/chroma_db.py
```

بهذا:

```python
import os
import glob
import uuid
import chromadb
from tqdm import tqdm

from .config import DATA_DIR, CHROMA_DIR, SUBJECTS, GRADES
from .embeddings import EmbeddingModel


class ChromaKnowledgeBase:
    def __init__(self):
        os.makedirs(CHROMA_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.embedding_model = EmbeddingModel()

    def _get_collection(self, subject, grade):
        return self.client.get_or_create_collection(f"{subject}_{grade}")

    def build_index(self):
        """
        تُستدعى فقط من build_index.py
        """
        for subject in SUBJECTS:
            for grade in GRADES:
                folder = os.path.join(DATA_DIR, subject, grade)
                if not os.path.isdir(folder):
                    continue

                files = glob.glob(os.path.join(folder, "*.txt"))
                if not files:
                    continue

                collection = self._get_collection(subject, grade)
                print(f"📚 Building: {collection.name}")

                texts, ids, metas = [], [], []

                for file in tqdm(files):
                    with open(file, encoding="utf-8") as f:
                        content = f.read()

                    chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
                    for chunk in chunks:
                        texts.append(chunk)
                        ids.append(str(uuid.uuid4()))
                        metas.append({
                            "subject": subject,
                            "grade": grade,
                            "source": os.path.basename(file)
                        })

                if texts:
                    embeddings = self.embedding_model.embed_texts(texts)
                    collection.add(
                        ids=ids,
                        documents=texts,
                        metadatas=metas,
                        embeddings=embeddings
                    )

        print("✅ Index built successfully.")

    def query(self, question, subject, grade, k=4):
        collection = self._get_collection(subject, grade)
        embedding = self.embedding_model.embed_query(question)

        result = collection.query(
            query_embeddings=[embedding],
            n_results=k
        )

        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]

        return list(zip(docs, metas))
```

---

# ✅ 2️⃣ ملف جديد خاص بالبناء فقط

أنشئ ملف جديد في الجذر:

```
build_index.py
```

وضع فيه:

```python
from rag.chroma_db import ChromaKnowledgeBase

if __name__ == "__main__":
    print("🚧 Starting Chroma Index Build...")
    db = ChromaKnowledgeBase()
    db.build_index()
    print("✅ Done. You can now run the API.")
```

✅ هذا الملف هو **المسؤول الوحيد عن توليد ChromaDB**.

---

# ✅ 3️⃣ تعديل `rag/rag_pipeline.py` (إلغاء البناء التلقائي)

استبدله بهذا:

```python
from .chroma_db import ChromaKnowledgeBase
from .groq_client import GroqClient

SYSTEM_PROMPT = """
أنت مدرس افتراضي ذكي.
- اشرح حسب مستوى الطالب.
- اعتمد فقط على المقاطع المسترجعة.
"""

class RAGPipeline:
    def __init__(self):
        self.db = ChromaKnowledgeBase()
        self.llm = GroqClient()

    def answer(self, question, subject, grade):
        contexts = self.db.query(question, subject, grade)

        context_text = "\n".join([doc for doc, _ in contexts])

        prompt = f"""
المادة: {subject}
الصف: {grade}
السؤال: {question}

السياق:
{context_text}
"""

        answer = self.llm.generate(SYSTEM_PROMPT, prompt)

        sources = [{"text": doc, "metadata": meta} for doc, meta in contexts]
        return answer, sources
```

✅ الآن الـ API لا يبني أي شيء.

---

# ✅ 4️⃣ سير العمل الجديد الصحيح

### ✅ أول مرة فقط (أو عند تحديث البيانات):

```bash
python build_index.py
```

سيبني كل:

```
physics_grade6
math_grade5
chemistry_grade6
...
```

داخل:

```
chroma_store/
```

---

### ✅ كل مرة تشغّل الـ API:

```bash
uvicorn main:app --reload
```

✅ بدون أي Embedding
✅ بسرعة عالية جدًا
✅ جاهز للإنتاج

---

# ✅ ماذا كسبت بهذا الفصل؟

| فائدة   | النتيجة          |
| ------- | ---------------- |
| الأداء  | ⚡ أسرع جدًا      |
| التحكم  | ✅ كامل           |
| التطوير | ✅ أسهل           |
| التحديث | ✅ بدون تعطيل API |
| الإنتاج | ✅ احترافي        |

---

# ✅ الخطوة التالية (جاهز لنقلة قوية)

اختر ما نضيف الآن:

1️⃣ نظام **رفع ملفات المدرسين + إعادة بناء تلقائي للـ Chroma**
2️⃣ نظام **امتحانات + تصحيح تلقائي مرتبط بالـ RAG**
3️⃣ نظام **طلاب + جلسات تدريس + تتبع تقدم**
4️⃣ واجهة **Web كاملة React Dashboard**
5️⃣ تحويله إلى **منتج SaaS كامل**

👉 اكتب الرقم فقط وسأنفّذه لك مباشرة 🔥
