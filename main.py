from typing import List, Optional, Literal, Dict, Any
from datetime import timedelta
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import os
# import requests
# from sqlalchemy.orm import Session
from jose import jwt, JWTError

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
from rag.file_processor import (
    # extract_text_from_image_google,
    extract_text_from_pdf_google,
    extract_rich_from_image_google
)
from rag.math_ocr import image_to_latex
from rag.groq_client import GroqClient
from rag.math_step_grader import MathStepGrader
from rag.auth import refresh_token_manager

from auth.security import ( 
    hash_password, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    SECRET_KEY,
    REFRESH_SECRET_KEY,
    ALGORITHM,
)
from auth.schemas import RegisterSchema, LoginSchema, RefreshRequest
# from auth.google_oauth import oauth
from auth.google_httpx import get_google_login_url
from auth.dependencies import get_current_user
from fastapi.responses import RedirectResponse

from db.database import Base, engine
from db.models.users import User
from db.models.students import Student
from db.models.exams import Exam
from db.models.student_attempts import StudentAttempt
from db.models.math_steps import MathStep
from db.models.ocr_logs import OCRLog
from db.models.refresh_tokens import RefreshToken

from sqlalchemy.orm import Session
from db.database import SessionLocal


app = FastAPI(
    title="Educational RAG API",
    version="5.0.0",
    description=(
        "نظام تعليمي يعتمد RAG + Groq + ChromaDB، "
        "مع دعم الحسابات (JWT)، الامتحانات، التصحيح، وسجل الطالب."
    ),
)

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
math_llm = GroqClient()
math_step_grader = MathStepGrader()


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


class MathStepsRequest(BaseModel):
    question: str
    correct_answer: str
    student_steps: List[str]


# ============ Endpoints الحسابات ============

# @app.post("/register", response_model=UserPublic)
# def register(req: RegisterRequest):
#     try:
#         user = user_manager.create_user(req.username, req.password, req.role)
#     except ValueError:
#         raise HTTPException(status_code=400, detail="Username already exists")

#     return UserPublic(
#         username=user["username"],
#         role=user["role"],
#         created_at=user["created_at"],
#     )

@app.post("/register")
def register(data: RegisterSchema, db: Session = Depends(get_db)):
    user_exists = db.query(User).filter(User.username == data.username).first()
    if user_exists:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User registered successfully ✅",
        "user_id": new_user.id
    }


# @app.post("/login")
# def login(form_data: OAuth2PasswordRequestForm = Depends()):
#     user = user_manager.verify_user(form_data.username, form_data.password)
#     if not user:
#         raise HTTPException(status_code=400, detail="Incorrect username or password")

#     access_token = create_access_token(
#         {"sub": user["username"], "role": user["role"]},
#         expires_delta=timedelta(minutes=15),  # ✅ قصير
#     )

#     refresh_token = refresh_token_manager.create_refresh_token(user["username"])

#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token,
#         "token_type": "bearer"
#     }

@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token({"sub": user.username, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.username})

    token_db = RefreshToken(user_id=user.id, token=refresh_token)
    db.add(token_db)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

# =========== Google OAuth Endpoints ============

# @app.get("/auth/google/login")
# def google_login():
#     return {
#         "login_url": get_google_login_url()
#     }


# @app.get("/auth/google")
# async def google_login(request: Request):
#     redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
#     return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google")
def google_login():
    url = get_google_login_url()
    return RedirectResponse(url)


# @app.get("/auth/google/callback")
# async def google_callback(code: str):
#     token_data = await exchange_code_for_token(code)
#     access_token = token_data["access_token"]

#     user_info = await get_google_user_info(access_token)
#     email = user_info.get("email")

#     if not email:
#         raise HTTPException(400, "Google account has no email")

#     user = user_manager.get_or_create_google_user(email)

#     jwt_access = create_access_token(
#         {"sub": user["username"], "role": user["role"]},
#         expires_delta=timedelta(minutes=15),
#     )

#     refresh_token = refresh_token_manager.create_refresh_token(user["username"])

#     return {
#         "access_token": jwt_access,
#         "refresh_token": refresh_token,
#         "token_type": "bearer",
#         "user": {
#             "username": user["username"],
#             "role": user["role"],
#         }
#     }


# @app.get("/auth/google/callback")
# async def google_callback(request: Request, db: Session = Depends(get_db)):
#     token = await oauth.google.authorize_access_token(request)
#     user_info = token.get("userinfo")

#     google_id = user_info["sub"]
#     email = user_info["email"]

#     # ✅ البحث عن المستخدم
#     user = db.query(User).filter(User.google_id == google_id).first()

#     # ✅ إذا لم يكن موجودًا ننشئه تلقائيًا
#     if not user:
#         user = User(
#             username=email.split("@")[0],
#             password_hash=None,
#             role="student",
#             google_id=google_id,
#             email=email
#         )
#         db.add(user)
#         db.commit()
#         db.refresh(user)

#     # ✅ توليد JWT
#     access_token = create_access_token({"sub": user.id, "role": user.role})
#     refresh_token = create_refresh_token({"sub": user.id})

#     token_db = RefreshToken(user_id=user.id, token=refresh_token)
#     db.add(token_db)
#     db.commit()

#     return {
#         "message": "Google login successful ✅",
#         "access_token": access_token,
#         "refresh_token": refresh_token,
#         "token_type": "bearer"
#     }


@app.get("/auth/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    try:
        # 1️⃣ تبادل code مقابل access_token
        token_data = await exchange_code_for_token(code)
        access_token_google = token_data["access_token"]

        # 2️⃣ جلب بيانات المستخدم من Google
        user_info = await get_google_user_info(access_token_google)

        google_id = user_info["sub"]
        email = user_info.get("email")
        name = user_info.get("name", email)

        # 3️⃣ البحث عن المستخدم في قاعدة البيانات
        user = db.query(User).filter(User.google_id == google_id).first()

        # 4️⃣ إذا لم يكن موجودًا → ننشئه
        if not user:
            user = User(
                username=email.split("@")[0] if email else google_id,
                email=email,
                google_id=google_id,
                role="student",
                password_hash=None
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # 5️⃣ إنشاء JWT Tokens
        access_token = create_access_token(
            {"sub": user.id, "role": user.role}
        )
        refresh_token = create_refresh_token(
            {"sub": user.id}
        )

        # 6️⃣ حفظ Refresh Token في DB
        token_db = RefreshToken(
            user_id=user.id,
            token=refresh_token
        )
        db.add(token_db)
        db.commit()

        return {
            "message": "Google login successful ✅",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# @app.post("/refresh")
# def refresh_token(refresh_token: str):
#     username = refresh_token_manager.verify_refresh_token(refresh_token)
#     if not username:
#         raise HTTPException(status_code=401, detail="Invalid refresh token")

#     user = user_manager.get_user(username)

#     new_access_token = create_access_token(
#         {"sub": user["username"], "role": user["role"]},
#         expires_delta=timedelta(minutes=15),
#     )

#     return {
#         "access_token": new_access_token,
#         "token_type": "bearer"
#     }


@app.post("/refresh")
def refresh_token_endpoint(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    refresh_token = data.refresh_token

    # 1) فك تشفير الـ Refresh Token والتأكد من صلاحيته
    try:
        payload = jwt.decode(
            refresh_token,
            REFRESH_SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # 2) التأكد أن الـ Refresh Token موجود في قاعدة البيانات
    token_in_db = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token == refresh_token,
            RefreshToken.user_id == int(user_id),
        )
        .first()
    )

    if not token_in_db:
        raise HTTPException(status_code=401, detail="Refresh token not found or revoked")

    # 3) جلب المستخدم
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # 4) إصدار Access Token جديد + Refresh Token جديد (تدوير)
    new_access_token = create_access_token(
        {"sub": user.id, "role": user.role},
        minutes=60,   # غيرها كما تريد
    )

    new_refresh_token = create_refresh_token(
        {"sub": user.id},
        days=7,       # غيرها كما تريد
    )

    # 5) تدوير الـ Refresh Token في قاعدة البيانات
    token_in_db.token = new_refresh_token
    db.commit()

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


# @app.post("/logout")
# def logout(
#     token: str = Depends(oauth2_scheme),
#     current_user: Dict[str, Any] = Depends(get_current_user),
# ):
#     token_blacklist.revoke(token)
    
#     # ✅ إلغاء كل Refresh Tokens لهذا المستخدم
#     refresh_token_manager.revoke_user_tokens(current_user["username"])

#     return {
#         "message": "تم تسجيل الخروج نهائيًا من جميع الجلسات ✅"
#     }

@app.post("/logout")
def logout(
    refresh_token: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    token_in_db = db.query(RefreshToken).filter(
        RefreshToken.token == refresh_token,
        RefreshToken.user_id == current_user.id
    ).first()

    if not token_in_db:
        return {"message": "Token already invalid or not found ✅"}

    db.delete(token_in_db)
    db.commit()

    return {"message": "Logged out successfully ✅"}


@app.post("/logout-all")
def logout_all(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id
    ).delete()

    db.commit()

    return {"message": "Logged out from all devices ✅"}


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


@app.post("/ask_file")
async def ask_from_file(
    subject: str,
    grade: str,
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    file_bytes = await file.read()
    filename = file.filename.lower()

    if filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        rich = extract_rich_from_image_google(file_bytes)
        extracted_text = rich["merged"]

    elif filename.endswith(".pdf"):
        extracted_text = extract_text_from_pdf_google(file_bytes)
        rich = {
            "detected_type": "text",
            "used_pix2tex": False,
            "latex": None,
        }

    else:
        raise HTTPException(400, "Unsupported file type")

    if not extracted_text:
        raise HTTPException(400, "لم يتم التعرف على أي نص من الملف.")

    answer, sources = rag.answer(extracted_text, subject, grade)

    return {
        "question_extracted": extracted_text,
        "detected_type": rich.get("detected_type"),
        "used_pix2tex": rich.get("used_pix2tex"),
        "latex": rich.get("latex"),
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


@app.post("/submit_answer_file")
async def submit_answer_from_file(
    question: str,
    model_answer: str,
    file: UploadFile = File(...),
    current_student: Dict[str, Any] = Depends(get_current_student),
):
    file_bytes = await file.read()
    filename = file.filename.lower()

    if filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        rich = extract_rich_from_image_google(file_bytes)
        student_answer_text = rich["merged"]
        latex = rich["latex"]

    elif filename.endswith(".pdf"):
        student_answer_text = extract_text_from_pdf_google(file_bytes)
        latex = None
        rich = {
            "detected_type": "text",
            "used_pix2tex": False,
        }

    else:
        raise HTTPException(400, "Unsupported file type")

    if not student_answer_text:
        raise HTTPException(400, "لم يتم التعرف على أي نص من إجابة الطالب.")

    grading_result = grading_engine.grade(
        question=question,
        student_answer=student_answer_text,
        model_answer=model_answer,
    )

    return {
        "question": question,
        "detected_type": rich.get("detected_type"),
        "used_pix2tex": rich.get("used_pix2tex"),
        "student_answer_extracted": student_answer_text,
        "student_answer_latex": latex,
        "grading_result": grading_result,
    }


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


@app.post("/math_ocr")
async def math_ocr_endpoint(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    file_bytes = await file.read()
    filename = file.filename.lower()

    if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(400, "هذا المسار خاص بالصور فقط (png/jpg/jpeg/webp).")

    try:
        latex = image_to_latex(file_bytes)
    except Exception as e:
        raise HTTPException(500, f"فشل تحويل الصورة إلى LaTeX: {e}")

    return {
        "latex": latex
    }


@app.post("/ask_math_file")
async def ask_math_from_file(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    file_bytes = await file.read()
    filename = file.filename.lower()

    if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(400, "هذا المسار خاص بصور المعادلات (png/jpg/jpeg/webp).")

    try:
        latex = image_to_latex(file_bytes)
    except Exception as e:
        raise HTTPException(500, f"فشل تحويل الصورة إلى LaTeX: {e}")

    # نبني برومبت للـ LLM لحل أو شرح المعادلة
    system_prompt = (
        "أنت مدرس رياضيات خبير. "
        "اكتشفت المعادلة التالية بصيغة LaTeX، أرجو حلها خطوة بخطوة وشرح الخطوات بالعربية."
    )

    user_prompt = f"المعادلة (LaTeX):\n{latex}\n\nحل المعادلة مع شرح الخطوات."

    answer = math_llm.generate(system_prompt, user_prompt)

    return {
        "latex": latex,
        "answer": answer
    }



@app.post("/submit_math_answer_file")
async def submit_math_answer_from_file(
    question: str,
    model_answer: str,  # ممكن تكون نصية أو LaTeX
    file: UploadFile = File(...),
    current_student: Dict[str, Any] = Depends(get_current_student),
):
    file_bytes = await file.read()
    filename = file.filename.lower()

    if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(400, "هذا المسار خاص بصور المعادلات (png/jpg/jpeg/webp).")

    try:
        student_latex = image_to_latex(file_bytes)
    except Exception as e:
        raise HTTPException(500, f"فشل تحويل صورة الطالب إلى LaTeX: {e}")

    # نبني إجابة طالب نصية/رمزية لإرسالها لمحرك التصحيح
    student_answer_text = f"إجابة الطالب بالصيغة LaTeX: {student_latex}"

    grading_result = grading_engine.grade(
        question=question,
        student_answer=student_answer_text,
        model_answer=model_answer
    )

    return {
        "question": question,
        "student_answer_latex": student_latex,
        "model_answer": model_answer,
        "grading_result": grading_result
    }



@app.post("/grade_math_steps")
def grade_math_steps(
    req: MathStepsRequest,
    current_student: Dict[str, Any] = Depends(get_current_student),
):
    """
    تصحيح حل رياضي خطوة بخطوة.
    مثال للـ JSON:

    {
      "question": "حل المعادلة 2x + 3 = 7",
      "correct_answer": "x = 2",
      "student_steps": [
        "2x + 3 = 7",
        "2x = 4",
        "x = 2"
      ]
    }
    """
    result = math_step_grader.grade_steps(
        question=req.question,
        student_steps=req.student_steps,
        correct_answer=req.correct_answer,
    )
    return result
