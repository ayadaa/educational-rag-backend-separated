from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from db.database import Base

class MathStep(Base):
    __tablename__ = "math_steps"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("student_attempts.id"))
    step_text = Column(String)
    is_valid = Column(Boolean)
    reason = Column(String)
