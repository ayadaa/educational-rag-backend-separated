from sqlalchemy import Column, Integer, String, ForeignKey
from db.database import Base

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)


# from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
# from datetime import datetime
# from db.database import Base

# class RefreshToken(Base):
#     __tablename__ = "refresh_tokens"

#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("users.id"))
#     token = Column(String, unique=True)
#     expires_at = Column(DateTime)
