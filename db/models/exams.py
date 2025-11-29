from sqlalchemy import Column, Integer, String
from db.database import Base

class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(50))
    grade = Column(String(50))
