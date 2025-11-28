import json
import os
from datetime import datetime

from .config import BASE_DIR

BLACKLIST_FILE = os.path.join(BASE_DIR, "revoked_tokens.json")


class TokenBlacklist:
    def __init__(self):
        if not os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _load(self):
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data):
        with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def revoke(self, token: str):
        data = self._load()
        data.append({
            "token": token,
            "revoked_at": datetime.utcnow().isoformat()
        })
        self._save(data)

    def is_revoked(self, token: str) -> bool:
        data = self._load()
        return any(item["token"] == token for item in data)
