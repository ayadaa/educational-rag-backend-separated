from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rag.rag_pipeline import RAGPipeline
from rag.config import SUBJECTS, GRADES

app = FastAPI(
    title="Educational RAG API",
    version="3.0.0",
    description="RAG تعليمي - API فقط (بدون بناء Chroma تلقائي)"
)

rag = RAGPipeline()

class QuestionRequest(BaseModel):
    question: str
    subject: str
    grade: str

@app.get("/subjects")
def list_subjects():
    return SUBJECTS

@app.get("/grades")
def list_grades():
    return GRADES

@app.post("/ask")
def ask(req: QuestionRequest):
    subject = req.subject.lower().strip()
    grade = req.grade.lower().strip()

    if subject not in SUBJECTS:
        raise HTTPException(400, "Invalid subject")

    if grade not in GRADES:
        raise HTTPException(400, "Invalid grade")

    answer, sources = rag.answer(req.question, subject, grade)

    return {
        "question": req.question,
        "subject": subject,
        "grade": grade,
        "answer": answer,
        "sources": sources
    }
