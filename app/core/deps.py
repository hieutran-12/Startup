from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import unauthorized
from app.core.security import decode_access_token
from app.modules.auth.models import User

DbSession = Annotated[AsyncSession, Depends(get_db)]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise unauthorized()
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized("invalid_token", "Phiên đăng nhập không hợp lệ hoặc đã hết hạn")
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized("invalid_token", "Tài khoản không tồn tại hoặc đã bị khoá")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
