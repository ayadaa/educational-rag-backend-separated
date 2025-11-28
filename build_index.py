from rag.chroma_db import ChromaKnowledgeBase

if __name__ == "__main__":
    print("🚧 Starting Chroma Index Build...")
    db = ChromaKnowledgeBase()
    db.build_index()
    print("✅ Done. You can now run the API.")
