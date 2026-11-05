from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import conflict, unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import LoginRequest, RegisterRequest

# Hai request refresh gần như đồng thời (vd. nhiều tab) không bị coi là token bị đánh cắp
REUSE_GRACE_PERIOD = timedelta(seconds=20)


@dataclass
class AuthResult:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str


async def _issue_tokens(db: AsyncSession, user: User, user_agent: str | None) -> AuthResult:
    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    await db.commit()
    access_token, expires_in = create_access_token(user.id)
    return AuthResult(user, access_token, expires_in, raw_refresh)


async def register(db: AsyncSession, data: RegisterRequest, user_agent: str | None) -> AuthResult:
    existing = await db.scalar(select(User.id).where(User.email == data.email))
    if existing is not None:
        raise conflict("email_taken", "Email này đã được đăng ký")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:  # hai request đăng ký cùng lúc
        await db.rollback()
        raise conflict("email_taken", "Email này đã được đăng ký") from exc
    return await _issue_tokens(db, user, user_agent)


async def login(db: AsyncSession, data: LoginRequest, user_agent: str | None) -> AuthResult:
    user = await db.scalar(select(User).where(User.email == data.email))
    if not verify_password(data.password, user.password_hash if user else None):
        raise unauthorized("invalid_credentials", "Email hoặc mật khẩu không đúng")
    assert user is not None
    if not user.is_active:
        raise unauthorized("account_disabled", "Tài khoản đã bị khoá")
    return await _issue_tokens(db, user, user_agent)


async def rotate_refresh_token(
    db: AsyncSession, raw_token: str | None, user_agent: str | None
) -> AuthResult:
    if not raw_token:
        raise unauthorized("missing_refresh_token", "Thiếu refresh token")

    token = await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    if token is None:
        raise unauthorized("invalid_refresh_token", "Refresh token không hợp lệ")

    now = datetime.now(UTC)
    if token.revoked_at is not None:
        if now - token.revoked_at > REUSE_GRACE_PERIOD:
            # Token cũ bị dùng lại: có thể đã bị lộ, thu hồi toàn bộ phiên của user
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await db.commit()
            raise unauthorized("refresh_token_reused", "Phiên đăng nhập đã bị thu hồi")
        raise unauthorized("refresh_token_rotated", "Refresh token vừa được làm mới")

    if token.expires_at <= now:
        raise unauthorized("refresh_token_expired", "Phiên đăng nhập đã hết hạn")

    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise unauthorized("account_disabled", "Tài khoản không khả dụng")

    token.revoked_at = now
    return await _issue_tokens(db, user, user_agent)


async def logout(db: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()
