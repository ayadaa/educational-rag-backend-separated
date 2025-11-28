import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from .config import BASE_DIR

# ملف تخزين المستخدمين (JSON بسيط)
USERS_FILE = os.path.join(BASE_DIR, "users.json")

# إعدادات JWT
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_SECRET_KEY")  # غيّرها في .env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # يوم كامل

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class UserManager:
    def __init__(self):
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _load(self) -> Dict[str, Any]:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: Dict[str, Any]):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        return data.get(username)

    def create_user(self, username: str, password: str, role: str = "student") -> Dict[str, Any]:
        data = self._load()
        if username in data:
            raise ValueError("User already exists")

        if role not in ["student", "teacher"]:
            role = "student"

        hashed = pwd_context.hash(password)

        user = {
            "username": username,
            "hashed_password": hashed,
            "role": role,
            "created_at": datetime.utcnow().isoformat()
        }

        data[username] = user
        self._save(data)
        return user

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user(username)
        if not user:
            return None
        if not pwd_context.verify(password, user["hashed_password"]):
            return None
        return user


user_manager = UserManager()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
