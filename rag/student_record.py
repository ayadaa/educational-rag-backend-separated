import json
import os
from datetime import datetime

RECORD_FILE = "student_records.json"


class StudentRecordManager:
    def __init__(self):
        self.file_path = RECORD_FILE
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _load(self):
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_exam_result(self, student_id: str, exam_result: dict):
        data = self._load()

        if student_id not in data:
            data[student_id] = {
                "student_id": student_id,
                "created_at": datetime.utcnow().isoformat(),
                "exams": []
            }

        exam_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "subject": exam_result.get("subject"),
            "grade": exam_result.get("grade"),
            "num_questions": exam_result.get("num_questions"),
            "total_score": exam_result.get("total_score"),
            "questions": exam_result.get("questions")
        }

        data[student_id]["exams"].append(exam_record)
        self._save(data)

    def get_student_record(self, student_id: str):
        data = self._load()
        return data.get(student_id)

    def get_student_stats(self, student_id: str):
        record = self.get_student_record(student_id)
        if not record or not record["exams"]:
            return {
                "student_id": student_id,
                "num_exams": 0,
                "average_score": 0
            }

        scores = [exam["total_score"] for exam in record["exams"]]
        avg = sum(scores) / len(scores)

        return {
            "student_id": student_id,
            "num_exams": len(scores),
            "average_score": round(avg, 2),
            "last_score": scores[-1]
        }
