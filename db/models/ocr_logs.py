from sqlalchemy import Column, Integer, String
from db.database import Base

class OCRLog(Base):
    __tablename__ = "ocr_logs"

    id = Column(Integer, primary_key=True, index=True)
    raw_text = Column(String)
    latex = Column(String)
    source_type = Column(String)


# from sqlalchemy import Column, Integer, String, DateTime
# from datetime import datetime
# from db.database import Base

# class OCRLog(Base):
#     __tablename__ = "ocr_logs"

#     id = Column(Integer, primary_key=True, index=True)
#     raw_text = Column(String)
#     latex = Column(String)
#     source_type = Column(String)  # image / pdf
#     created_at = Column(DateTime, default=datetime.utcnow)
