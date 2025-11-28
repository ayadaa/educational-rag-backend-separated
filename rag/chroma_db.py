import os, glob, uuid
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
                        metas.append({"subject": subject, "grade": grade, "source": os.path.basename(file)})

                if texts:
                    embeddings = self.embedding_model.embed_texts(texts)
                    collection.add(ids=ids, documents=texts, metadatas=metas, embeddings=embeddings)

        print("✅ Index built successfully.")

    def query(self, question, subject, grade, k=4):
        collection = self._get_collection(subject, grade)
        emb = self.embedding_model.embed_query(question)
        result = collection.query(query_embeddings=[emb], n_results=k)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        return list(zip(docs, metas))
