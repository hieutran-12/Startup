"""Schema của module auth (spec 03 › Bảng giữ nguyên; quy tắc phụ: docs/modules/auth.md)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.schemas import StrictModel
from app.core.types import Email, Password, RequiredSingleLine


class RegisterRequest(StrictModel):
    email: Email
    password: Password(8, 128)
    full_name: RequiredSingleLine(120)


class LoginRequest(StrictModel):
    email: Email
    # Không áp độ dài tối thiểu của đăng ký: mật khẩu sai thì 401, không phải 422 (giữ như khung)
    password: Password(1, 128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
