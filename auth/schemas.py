from pydantic import BaseModel

class RegisterSchema(BaseModel):
    username: str
    password: str
    role: str  # student / teacher

class LoginSchema(BaseModel):
    username: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str
