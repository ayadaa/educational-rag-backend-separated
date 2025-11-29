from sqlalchemy import Column, Integer, String
from db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)  # null لمستخدمي Google
    role = Column(String(50))  # student / teacher / admin

    # ✅ Google OAuth
    google_id = Column(String(255), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
