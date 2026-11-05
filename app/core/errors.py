from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Lỗi nghiệp vụ. FE dựa vào `code` để hiển thị thông báo (không phụ thuộc message)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def not_found(code: str = "not_found", message: str = "Không tìm thấy") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, code, message)


def conflict(code: str, message: str) -> AppError:
    return AppError(status.HTTP_409_CONFLICT, code, message)


def bad_request(code: str, message: str) -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, code, message)


def unauthorized(code: str = "unauthorized", message: str = "Chưa đăng nhập") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, code, message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=headers,
        )
