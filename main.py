from typing import List, Optional, Literal, Dict, Any
from datetime import timedelta
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from rag.rag_pipeline import RAGPipeline
from rag.config import SUBJECTS, GRADES
from rag.grading_engine import GradingEngine
from rag.exam_engine import ExamEngine
from rag.student_record import StudentRecordManager
from rag.token_blacklist import TokenBlacklist
from rag.auth import user_manager, create_access_token, decode_token
from rag.google_oauth import (
    get_google_login_url,
    exchange_code_for_token,
    get_google_user_info,
)


app = FastAPI(
    title="Educational RAG API",
    version="5.0.0",
    description=(
        "نظام تعليمي يعتمد RAG + Groq + ChromaDB، "
        "مع دعم الحسابات (JWT)، الامتحانات، التصحيح، وسجل الطالب."
    ),
)

# ============ OAuth2 / JWT ============

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    # ✅ تحقق إن كان التوكن ملغي (logout)
    if token_blacklist.is_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked (logged out)",
        )

    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    username = payload["sub"]
    user = user_manager.get_user(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


def get_current_student(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student access required",
        )
    return user


def get_current_teacher(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher access required",
        )
    return user


# ============ الكيانات الأساسية ============

rag = RAGPipeline()
grading_engine = GradingEngine()
exam_engine = ExamEngine()
student_records = StudentRecordManager()
token_blacklist = TokenBlacklist()


# ============ موديلات عامة ============

class QuestionRequest(BaseModel):
    question: str
    subject: str
    grade: str


# موديلات الامتحان

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
    selected_option_index: Optional[int] = None  # MCQ
    answer_text: Optional[str] = None            # Open


class ExamSubmission(BaseModel):
    exam: GeneratedExam
    answers: List[StudentAnswer]


# موديلات الحسابات

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: Literal["student", "teacher"] = "student"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    username: str
    role: str
    created_at: str


# ============ Endpoints الحسابات ============

@app.post("/register", response_model=UserPublic)
def register(req: RegisterRequest):
    try:
        user = user_manager.create_user(req.username, req.password, req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Username already exists")

    return UserPublic(
        username=user["username"],
        role=user["role"],
        created_at=user["created_at"],
    )


from rag.auth import refresh_token_manager
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = user_manager.verify_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token = create_access_token(
        {"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=15),  # ✅ قصير
    )

    refresh_token = refresh_token_manager.create_refresh_token(user["username"])

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# =========== Google OAuth Endpoints ============

@app.get("/auth/google/login")
def google_login():
    return {
        "login_url": get_google_login_url()
    }


@app.get("/auth/google/callback")
async def google_callback(code: str):
    token_data = await exchange_code_for_token(code)
    access_token = token_data["access_token"]

    user_info = await get_google_user_info(access_token)
    email = user_info.get("email")

    if not email:
        raise HTTPException(400, "Google account has no email")

    user = user_manager.get_or_create_google_user(email)

    jwt_access = create_access_token(
        {"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=15),
    )

    refresh_token = refresh_token_manager.create_refresh_token(user["username"])

    return {
        "access_token": jwt_access,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "role": user["role"],
        }
    }


@app.post("/refresh")
def refresh_token(refresh_token: str):
    username = refresh_token_manager.verify_refresh_token(refresh_token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = user_manager.get_user(username)

    new_access_token = create_access_token(
        {"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=15),
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }


@app.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    token_blacklist.revoke(token)
    
    # ✅ إلغاء كل Refresh Tokens لهذا المستخدم
    refresh_token_manager.revoke_user_tokens(current_user["username"])

    return {
        "message": "تم تسجيل الخروج نهائيًا من جميع الجلسات ✅"
    }


@app.get("/me", response_model=UserPublic)
def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return UserPublic(
        username=current_user["username"],
        role=current_user["role"],
        created_at=current_user["created_at"],
    )


# ============ Endpoints عامة ============

@app.get("/subjects")
def list_subjects():
    return SUBJECTS


@app.get("/grades")
def list_grades():
    return GRADES


@app.post("/ask")
def ask(req: QuestionRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
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
        "sources": sources,
    }


# ============ توليد الامتحان (مدرّس فقط) ============

@app.post("/generate_exam", response_model=GeneratedExam)
def generate_exam(
    req: GenerateExamRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),  # ✅ أي مستخدم مسجل
):
    subject = req.subject.lower().strip()
    grade = req.grade.lower().strip()

    if subject not in SUBJECTS:
        raise HTTPException(400, "Invalid subject")

    if grade not in GRADES:
        raise HTTPException(400, "Invalid grade")

    raw_exam = exam_engine.generate_exam(subject, grade, req.num_questions)

    if "error" in raw_exam:
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


# ============ تصحيح امتحان كامل (طالب فقط) ============

@app.post("/submit_exam")
def submit_exam(
    submission: ExamSubmission,
    current_student: Dict[str, Any] = Depends(get_current_student),
):
    exam = submission.exam
    answers = submission.answers

    question_map = {q.id: q for q in exam.questions}

    per_question_results = []
    total_score = 0.0
    question_count = 0

    for ans in answers:
        q = question_map.get(ans.question_id)
        if not q:
            continue

        question_count += 1

        if q.type == "mcq":
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

    result = {
        "subject": exam.subject,
        "grade": exam.grade,
        "num_questions": question_count,
        "total_score": exam_score,
        "questions": per_question_results,
    }

    # حفظ النتيجة باسم الطالب (username) من الـ JWT
    student_id = current_student["username"]
    student_records.add_exam_result(student_id, result)

    return result


# ============ سجل الطالب ============

@app.get("/student/{student_id}")
def get_student_record_route(
    student_id: str,
    current_teacher: Dict[str, Any] = Depends(get_current_teacher),
):
    record = student_records.get_student_record(student_id)
    if not record:
        raise HTTPException(404, "Student not found")
    return record


@app.get("/student/{student_id}/stats")
def get_student_stats_route(
    student_id: str,
    current_teacher: Dict[str, Any] = Depends(get_current_teacher),
):
    return student_records.get_student_stats(student_id)


@app.get("/me/record")
def get_my_record(current_student: Dict[str, Any] = Depends(get_current_student)):
    student_id = current_student["username"]
    record = student_records.get_student_record(student_id)
    if not record:
        raise HTTPException(404, "No record yet")
    return record


@app.get("/me/stats")
def get_my_stats(current_student: Dict[str, Any] = Depends(get_current_student)):
    student_id = current_student["username"]
    return student_records.get_student_stats(student_id)




# from typing import List, Optional, Literal

# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel

# from rag.rag_pipeline import RAGPipeline
# from rag.grading_engine import GradingEngine
# from rag.exam_engine import ExamEngine
# from rag.student_record import StudentRecordManager
# from rag.config import SUBJECTS, GRADES

# app = FastAPI(
#     title="Educational RAG API",
#     version="4.0.0",
#     description=(
#         "نظام تعليمي يعتمد RAG + Groq + ChromaDB، "
#         "مع دعم الأسئلة المباشرة، التصحيح النصي، ونظام امتحانات كامل."
#     ),
# )

# # ====== الكيانات الأساسية ======

# rag = RAGPipeline()
# grading_engine = GradingEngine()
# exam_engine = ExamEngine()
# student_records = StudentRecordManager()


# # ====== موديلات الأسئلة ======

# class QuestionRequest(BaseModel):
#     question: str
#     subject: str
#     grade: str

# # ====== موديلات الامتحان ======

# class GeneratedQuestion(BaseModel):
#     id: int
#     type: Literal["mcq", "open"]
#     question: str
#     options: Optional[List[str]] = None
#     correct_option_index: Optional[int] = None
#     model_answer: str


# class GeneratedExam(BaseModel):
#     subject: str
#     grade: str
#     questions: List[GeneratedQuestion]


# class GenerateExamRequest(BaseModel):
#     subject: str
#     grade: str
#     num_questions: int = 5


# class StudentAnswer(BaseModel):
#     question_id: int
#     selected_option_index: Optional[int] = None  # لأسئلة MCQ
#     answer_text: Optional[str] = None           # لأسئلة open


# class ExamSubmission(BaseModel):
#     student_id: str
#     exam: GeneratedExam
#     answers: List[StudentAnswer]

# # ====== Endpoints أساسية ======

# @app.get("/subjects")
# def list_subjects():
#     return SUBJECTS

# @app.get("/grades")
# def list_grades():
#     return GRADES

# @app.post("/ask")
# def ask(req: QuestionRequest):
#     subject = req.subject.lower().strip()
#     grade = req.grade.lower().strip()

#     if subject not in SUBJECTS:
#         raise HTTPException(400, "Invalid subject")

#     if grade not in GRADES:
#         raise HTTPException(400, "Invalid grade")

#     answer, sources = rag.answer(req.question, subject, grade)

#     return {
#         "question": req.question,
#         "subject": subject,
#         "grade": grade,
#         "answer": answer,
#         "sources": sources
#     }

# @app.post("/grade")
# def grade_answer(req: dict):
#     """
#     {
#       "question": "...",
#       "student_answer": "...",
#       "subject": "...",
#       "grade": "..."
#     }
#     """

#     question = req["question"]
#     student_answer = req["student_answer"]
#     subject = req["subject"].lower()
#     grade = req["grade"].lower()

#     # 1️⃣ نحصل على الإجابة النموذجية عبر RAG
#     model_answer, _ = rag.answer(question, subject, grade)

#     # 2️⃣ نُرسل الإجابتين إلى محرك التصحيح
#     grading_result = grading_engine.grade(
#         question=question,
#         student_answer=student_answer,
#         model_answer=model_answer
#     )

#     return {
#         "question": question,
#         "student_answer": student_answer,
#         "model_answer": model_answer,
#         "grading_result": grading_result
#     }



# # ======  توليد الامتحان ======

# @app.post("/generate_exam", response_model=GeneratedExam)
# def generate_exam(req: GenerateExamRequest):
#     subject = req.subject.lower().strip()
#     grade = req.grade.lower().strip()

#     if subject not in SUBJECTS:
#         raise HTTPException(400, "Invalid subject")

#     if grade not in GRADES:
#         raise HTTPException(400, "Invalid grade")

#     raw_exam = exam_engine.generate_exam(subject, grade, req.num_questions)

#     if "error" in raw_exam:
#         # إرجاع الخطأ الخام لو حصلت مشكلة في JSON
#         raise HTTPException(
#             status_code=500,
#             detail={
#                 "message": "Exam generation failed",
#                 "error": raw_exam.get("error"),
#                 "raw_output": raw_exam.get("raw_output"),
#             },
#         )

#     questions = []
#     for q in raw_exam["questions"]:
#         try:
#             questions.append(
#                 GeneratedQuestion(
#                     id=int(q.get("id")),
#                     type=q.get("type"),
#                     question=q.get("question"),
#                     options=q.get("options"),
#                     correct_option_index=q.get("correct_option_index"),
#                     model_answer=q.get("model_answer"),
#                 )
#             )
#         except Exception as e:
#             print("Question parse error:", e, q)
#             continue

#     if not questions:
#         raise HTTPException(500, "No valid questions generated")

#     return GeneratedExam(subject=subject, grade=grade, questions=questions)


# # ======  تصحيح امتحان كامل ======

# @app.post("/submit_exam")
# def submit_exam(submission: ExamSubmission):
#     exam = submission.exam
#     answers = submission.answers

#     # نبني قاموس من id -> سؤال
#     question_map = {q.id: q for q in exam.questions}

#     per_question_results = []
#     total_score = 0.0
#     question_count = 0

#     for ans in answers:
#         q = question_map.get(ans.question_id)
#         if not q:
#             # تجاهل سؤال غير معروف
#             continue

#         question_count += 1

#         if q.type == "mcq":
#             # تصحيح اختيار من متعدد
#             if ans.selected_option_index is None:
#                 score = 0
#                 is_correct = False
#                 feedback = "لم يتم اختيار أي خيار."
#             else:
#                 is_correct = ans.selected_option_index == q.correct_option_index
#                 score = 100 if is_correct else 0
#                 feedback = "إجابة صحيحة." if is_correct else "إجابة خاطئة."

#             student_repr = None
#             if ans.selected_option_index is not None and q.options:
#                 idx = ans.selected_option_index
#                 if 0 <= idx < len(q.options):
#                     student_repr = q.options[idx]
#                 else:
#                     student_repr = f"خيار رقم {idx}"

#             per_question_results.append(
#                 {
#                     "question_id": q.id,
#                     "type": q.type,
#                     "question": q.question,
#                     "student_answer": student_repr,
#                     "model_answer": q.model_answer,
#                     "score": score,
#                     "is_correct": is_correct,
#                     "feedback": feedback,
#                 }
#             )
#             total_score += score

#         elif q.type == "open":
#             # تصحيح سؤال مفتوح باستخدام GradingEngine
#             if not ans.answer_text:
#                 grading_result = {
#                     "score": 0,
#                     "is_correct": False,
#                     "feedback": "لا توجد إجابة من الطالب.",
#                     "correct_answer": q.model_answer,
#                 }
#             else:
#                 grading_result = grading_engine.grade(
#                     question=q.question,
#                     student_answer=ans.answer_text,
#                     model_answer=q.model_answer,
#                 )

#             per_question_results.append(
#                 {
#                     "question_id": q.id,
#                     "type": q.type,
#                     "question": q.question,
#                     "student_answer": ans.answer_text,
#                     "model_answer": q.model_answer,
#                     "score": grading_result.get("score", 0),
#                     "is_correct": grading_result.get("is_correct", False),
#                     "feedback": grading_result.get("feedback", ""),
#                 }
#             )
#             total_score += grading_result.get("score", 0)

#         else:
#             # نوع سؤال غير معروف
#             per_question_results.append(
#                 {
#                     "question_id": q.id,
#                     "type": q.type,
#                     "question": q.question,
#                     "student_answer": None,
#                     "model_answer": q.model_answer,
#                     "score": 0,
#                     "is_correct": False,
#                     "feedback": "نوع سؤال غير مدعوم.",
#                 }
#             )

#     if question_count == 0:
#         raise HTTPException(400, "No valid answers/questions to grade")

#     exam_score = total_score / question_count

#     result = {
#     "subject": exam.subject,
#     "grade": exam.grade,
#     "num_questions": question_count,
#     "total_score": exam_score,
#     "questions": per_question_results,
#     }

#     # ✅ حفظ النتيجة في سجل الطالب
#     student_id = submission.dict().get("student_id", "anonymous")
#     student_records.add_exam_result(student_id, result)

#     return result


# # ====== عرض سجل الطالب ======

# @app.get("/student/{student_id}")
# def get_student_record(student_id: str):
#     record = student_records.get_student_record(student_id)
#     if not record:
#         raise HTTPException(404, "Student not found")
#     return record


# @app.get("/student/{student_id}/stats")
# def get_student_stats(student_id: str):
#     return student_records.get_student_stats(student_id)
