from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rag.rag_pipeline import RAGPipeline
from rag.grading_engine import GradingEngine
from rag.config import SUBJECTS, GRADES
from rag.exam_engine import ExamEngine

app = FastAPI(
    title="Educational RAG API",
    version="4.0.0",
    description=(
        "نظام تعليمي يعتمد RAG + Groq + ChromaDB، "
        "مع دعم الأسئلة المباشرة، التصحيح النصي، ونظام امتحانات كامل."
    ),
)

# ====== الكيانات الأساسية ======

rag = RAGPipeline()
grading_engine = GradingEngine()
exam_engine = ExamEngine()

class QuestionRequest(BaseModel):
    question: str
    subject: str
    grade: str

# ====== موديلات الامتحان ======

class GeneratedQuestion(BaseModel):
    id: int
    type: Literal["mcq", "open"]
    question: str
    options: Optional[List[str]] = None
    correct_option_index: Optional[int] = None
    model_answer: str


class GeneratedExam(BaseModel):
    subject: str
    grade: str
    questions: List[GeneratedQuestion]


class GenerateExamRequest(BaseModel):
    subject: str
    grade: str
    num_questions: int = 5


class StudentAnswer(BaseModel):
    question_id: int
    selected_option_index: Optional[int] = None  # لأسئلة MCQ
    answer_text: Optional[str] = None           # لأسئلة open


class ExamSubmission(BaseModel):
    exam: GeneratedExam
    answers: List[StudentAnswer]

# ====== Endpoints أساسية ======

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

@app.post("/grade")
def grade_answer(req: dict):
    """
    {
      "question": "...",
      "student_answer": "...",
      "subject": "...",
      "grade": "..."
    }
    """

    question = req["question"]
    student_answer = req["student_answer"]
    subject = req["subject"].lower()
    grade = req["grade"].lower()

    # 1️⃣ نحصل على الإجابة النموذجية عبر RAG
    model_answer, _ = rag.answer(question, subject, grade)

    # 2️⃣ نُرسل الإجابتين إلى محرك التصحيح
    grading_result = grading_engine.grade(
        question=question,
        student_answer=student_answer,
        model_answer=model_answer
    )

    return {
        "question": question,
        "student_answer": student_answer,
        "model_answer": model_answer,
        "grading_result": grading_result
    }



# ======  توليد الامتحان ======

@app.post("/generate_exam", response_model=GeneratedExam)
def generate_exam(req: GenerateExamRequest):
    subject = req.subject.lower().strip()
    grade = req.grade.lower().strip()

    if subject not in SUBJECTS:
        raise HTTPException(400, "Invalid subject")

    if grade not in GRADES:
        raise HTTPException(400, "Invalid grade")

    raw_exam = exam_engine.generate_exam(subject, grade, req.num_questions)

    if "error" in raw_exam:
        # إرجاع الخطأ الخام لو حصلت مشكلة في JSON
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Exam generation failed",
                "error": raw_exam.get("error"),
                "raw_output": raw_exam.get("raw_output"),
            },
        )

    questions = []
    for q in raw_exam["questions"]:
        try:
            questions.append(
                GeneratedQuestion(
                    id=int(q.get("id")),
                    type=q.get("type"),
                    question=q.get("question"),
                    options=q.get("options"),
                    correct_option_index=q.get("correct_option_index"),
                    model_answer=q.get("model_answer"),
                )
            )
        except Exception as e:
            print("Question parse error:", e, q)
            continue

    if not questions:
        raise HTTPException(500, "No valid questions generated")

    return GeneratedExam(subject=subject, grade=grade, questions=questions)


# ======  تصحيح امتحان كامل ======

@app.post("/submit_exam")
def submit_exam(submission: ExamSubmission):
    exam = submission.exam
    answers = submission.answers

    # نبني قاموس من id -> سؤال
    question_map = {q.id: q for q in exam.questions}

    per_question_results = []
    total_score = 0.0
    question_count = 0

    for ans in answers:
        q = question_map.get(ans.question_id)
        if not q:
            # تجاهل سؤال غير معروف
            continue

        question_count += 1

        if q.type == "mcq":
            # تصحيح اختيار من متعدد
            if ans.selected_option_index is None:
                score = 0
                is_correct = False
                feedback = "لم يتم اختيار أي خيار."
            else:
                is_correct = ans.selected_option_index == q.correct_option_index
                score = 100 if is_correct else 0
                feedback = "إجابة صحيحة." if is_correct else "إجابة خاطئة."

            student_repr = None
            if ans.selected_option_index is not None and q.options:
                idx = ans.selected_option_index
                if 0 <= idx < len(q.options):
                    student_repr = q.options[idx]
                else:
                    student_repr = f"خيار رقم {idx}"

            per_question_results.append(
                {
                    "question_id": q.id,
                    "type": q.type,
                    "question": q.question,
                    "student_answer": student_repr,
                    "model_answer": q.model_answer,
                    "score": score,
                    "is_correct": is_correct,
                    "feedback": feedback,
                }
            )
            total_score += score

        elif q.type == "open":
            # تصحيح سؤال مفتوح باستخدام GradingEngine
            if not ans.answer_text:
                grading_result = {
                    "score": 0,
                    "is_correct": False,
                    "feedback": "لا توجد إجابة من الطالب.",
                    "correct_answer": q.model_answer,
                }
            else:
                grading_result = grading_engine.grade(
                    question=q.question,
                    student_answer=ans.answer_text,
                    model_answer=q.model_answer,
                )

            per_question_results.append(
                {
                    "question_id": q.id,
                    "type": q.type,
                    "question": q.question,
                    "student_answer": ans.answer_text,
                    "model_answer": q.model_answer,
                    "score": grading_result.get("score", 0),
                    "is_correct": grading_result.get("is_correct", False),
                    "feedback": grading_result.get("feedback", ""),
                }
            )
            total_score += grading_result.get("score", 0)

        else:
            # نوع سؤال غير معروف
            per_question_results.append(
                {
                    "question_id": q.id,
                    "type": q.type,
                    "question": q.question,
                    "student_answer": None,
                    "model_answer": q.model_answer,
                    "score": 0,
                    "is_correct": False,
                    "feedback": "نوع سؤال غير مدعوم.",
                }
            )

    if question_count == 0:
        raise HTTPException(400, "No valid answers/questions to grade")

    exam_score = total_score / question_count

    return {
        "subject": exam.subject,
        "grade": exam.grade,
        "num_questions": question_count,
        "total_score": exam_score,
        "questions": per_question_results,
    }
