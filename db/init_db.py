#  بدل المحتوى الموجود في main.py 
# python db/init_db.py


from db.database import Base, engine
from db.models.users import User
from db.models.students import Student
from db.models.exams import Exam
from db.models.student_attempts import StudentAttempt
from db.models.math_steps import MathStep
from db.models.ocr_logs import OCRLog
from db.models.refresh_tokens import RefreshToken

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Done ✅")
