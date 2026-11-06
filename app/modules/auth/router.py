from typing import Annotated

from fastapi import APIRouter, Cookie, Header, Response, status

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.modules.auth import service
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(tags=["auth"])

# Cookie chỉ được gửi kèm các request tới /auth, không lộ ra ở các API khác
REFRESH_COOKIE_PATH = "/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)]
UserAgent = Annotated[str | None, Header()]


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _token_response(response: Response, result: service.AuthResult) -> TokenResponse:
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=UserResponse.model_validate(result.user),
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest, response: Response, db: DbSession, user_agent: UserAgent = None
) -> TokenResponse:
    result = await service.register(db, data, user_agent)
    return _token_response(response, result)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    data: LoginRequest, response: Response, db: DbSession, user_agent: UserAgent = None
) -> TokenResponse:
    result = await service.login(db, data, user_agent)
    return _token_response(response, result)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: DbSession,
    refresh_token: RefreshCookie = None,
    user_agent: UserAgent = None,
) -> TokenResponse:
    result = await service.rotate_refresh_token(db, refresh_token, user_agent)
    return _token_response(response, result)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, db: DbSession, refresh_token: RefreshCookie = None) -> None:
    await service.logout(db, refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
