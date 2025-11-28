from sentence_transformers import SentenceTransformer
from .config import EMBEDDING_MODEL_NAME

class EmbeddingModel:
    def __init__(self):
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    def embed_texts(self, texts):
        return self.model.encode(texts, convert_to_numpy=True).tolist()

    def embed_query(self, query):
        return self.embed_texts([query])[0]
