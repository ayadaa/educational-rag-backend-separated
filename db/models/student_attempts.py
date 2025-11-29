from sqlalchemy import Column, Integer, String, Float, ForeignKey
from db.database import Base

class StudentAttempt(Base):
    __tablename__ = "student_attempts"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    exam_id = Column(Integer, ForeignKey("exams.id"))
    question_text = Column(String)
    student_answer = Column(String)
    score = Column(Float)
