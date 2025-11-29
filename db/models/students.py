from sqlalchemy import Column, Integer, String, ForeignKey
from db.database import Base

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    full_name = Column(String(150))
    grade = Column(String(50))
