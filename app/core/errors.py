"""Định dạng lỗi chung (spec 05 › Định dạng lỗi).

Mọi lỗi trả về {"error": {"code", "message", "details": [{"field", "code", "message"}]}}.
"""

import re
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

ErrorDetail = dict[str, str]
"""Một phần tử của `details`: {"field": ..., "code": ..., "message": ...}."""

# Mã lỗi của từng trường. Kiểu trong app/core/types.py raise thẳng các mã này.
FIELD_ERROR_CODES = frozenset(
    {
        "required",
        "invalid_format",
        "invalid_characters",
        "too_long",
        "out_of_range",
        "invalid_choice",
        "unknown_field",
        "invalid_reference",
    }
)

_CODE_MESSAGES = {
    "required": "Không được để trống",
    "invalid_format": "Sai định dạng",
    "invalid_characters": "Chứa ký tự không hợp lệ",
    "too_long": "Quá dài",
    "out_of_range": "Ngoài khoảng cho phép",
    "invalid_choice": "Giá trị không hợp lệ",
    "unknown_field": "Trường không được hỗ trợ",
    "invalid_reference": "Tham chiếu không hợp lệ",
}

# Loại lỗi của Pydantic -> mã lỗi của spec. Loại không có ở đây là invalid_format.
# Ngắn hơn tối thiểu cũng là out_of_range (spec 05 không có mã too_short).
_PYDANTIC_CODES = {
    "missing": "required",
    "extra_forbidden": "unknown_field",
    "string_too_long": "too_long",
    "too_long": "too_long",
    "string_too_short": "out_of_range",
    "too_short": "out_of_range",
    "greater_than": "out_of_range",
    "greater_than_equal": "out_of_range",
    "less_than": "out_of_range",
    "less_than_equal": "out_of_range",
    "enum": "invalid_choice",
    "literal_error": "invalid_choice",
}

_PYDANTIC_MESSAGES = {
    "string_too_long": "Tối đa {max_length} ký tự",
    "too_long": "Tối đa {max_length} phần tử",
    "string_too_short": "Tối thiểu {min_length} ký tự",
    "too_short": "Tối thiểu {min_length} phần tử",
    "greater_than": "Phải lớn hơn {gt}",
    "greater_than_equal": "Phải lớn hơn hoặc bằng {ge}",
    "less_than": "Phải nhỏ hơn {lt}",
    "less_than_equal": "Phải nhỏ hơn hoặc bằng {le}",
    "enum": "Phải là một trong: {expected}",
    "literal_error": "Phải là một trong: {expected}",
    "int_type": "Phải là số nguyên",
    "bool_type": "Phải là true hoặc false",
    "string_type": "Phải là chuỗi",
    "float_type": "Phải là số",
    "list_type": "Phải là danh sách",
    "dict_type": "Phải là object",
    "model_type": "Phải là object",
    "model_attributes_type": "Phải là object",
    "json_invalid": "JSON không hợp lệ",
}

_HTTP_MESSAGES = {
    status.HTTP_404_NOT_FOUND: "Không tìm thấy",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Phương thức không được hỗ trợ",
}

_NO_INPUT = object()


class AppError(Exception):
    """Lỗi nghiệp vụ. FE dựa vào `code` để hiển thị thông báo (không phụ thuộc message)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Sequence[ErrorDetail] = (),
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = list(details)
        self.headers = dict(headers or {})
        super().__init__(message)


def not_found(code: str = "not_found", message: str = "Không tìm thấy") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, code, message)


def conflict(code: str, message: str) -> AppError:
    return AppError(status.HTTP_409_CONFLICT, code, message)


def bad_request(code: str, message: str, details: Sequence[ErrorDetail] = ()) -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, code, message, details)


def unauthorized(code: str = "unauthorized", message: str = "Chưa đăng nhập") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, code, message)


def validation_error(details: Sequence[ErrorDetail]) -> AppError:
    """422 `validation_error` do service phát hiện (content sau Merge Patch, tham chiếu media)."""
    return AppError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", "Dữ liệu không hợp lệ", details
    )


# ---------- Chuyển lỗi Pydantic sang details ----------


def _field_path(error: Mapping[str, Any]) -> str:
    """("content", "love_story", 0, "title") -> "content.love_story[0].title"."""
    if error["type"] == "json_invalid":  # loc chứa vị trí ký tự hỏng, không phải trường
        return ""
    path = ""
    for part in error["loc"]:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path = f"{path}.{part}" if path else str(part)
    return path


def _message(error: Mapping[str, Any], code: str) -> str:
    error_type = error["type"]
    ctx = dict(error.get("ctx") or {})
    template = _PYDANTIC_MESSAGES.get(error_type)
    # Tra template trước: "too_long" vừa là mã spec vừa là lỗi độ dài danh sách của Pydantic
    if template is None:
        if error_type in FIELD_ERROR_CODES:  # lỗi từ app/core/types.py, message đã là tiếng Việt
            return error["msg"]
        if error_type in ("value_error", "assertion_error") and "error" in ctx:
            return str(ctx["error"])
        return _CODE_MESSAGES[code]
    if "expected" in ctx:  # "'groom' or 'bride'" -> "'groom', 'bride'"
        ctx["expected"] = str(ctx["expected"]).replace(" or ", ", ")
    try:
        return template.format_map(ctx)
    except (KeyError, ValueError):
        return _CODE_MESSAGES[code]


def error_details(errors: Sequence[Mapping[str, Any]]) -> list[ErrorDetail]:
    """Chuyển `ValidationError.errors()` thành `details`. `loc` không chứa body/query/path."""
    details: list[ErrorDetail] = []
    for error in errors:
        error_type = error["type"]
        if error_type in FIELD_ERROR_CODES:
            # Mã spec raise thẳng (types.py, model_validator): giữ nguyên mã và message,
            # kể cả khi input là null (ví dụ "Cần nhập năm khi có tháng" tại love_story[i].year)
            code = error_type
            message = _message(error, code)
        elif error_type != "extra_forbidden" and error.get("input", _NO_INPUT) is None:
            # null là "không có giá trị": gửi null cho trường không nhận null là thiếu giá trị
            code = "required"
            message = _CODE_MESSAGES["required"]
        else:
            code = _PYDANTIC_CODES.get(error_type, "invalid_format")
            message = _message(error, code)
        details.append({"field": _field_path(error), "code": code, "message": message})
    return details


# ---------- Handler ----------


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Sequence[ErrorDetail] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": list(details)}},
        headers=headers,
    )


def _http_error_code(status_code: int) -> str:
    """404 -> "not_found", 405 -> "method_not_allowed"."""
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return "http_error"
    return re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = dict(exc.headers)
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            headers.setdefault("WWW-Authenticate", "Bearer")
        return error_response(exc.status_code, exc.code, exc.message, exc.details, headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # loc của FastAPI bắt đầu bằng nơi chứa dữ liệu ("body", "query", "path"...): bỏ đi
        errors = [{**error, "loc": tuple(error["loc"])[1:]} for error in exc.errors()]
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "Dữ liệu không hợp lệ",
            error_details(errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Lỗi do Starlette tự sinh (route không tồn tại, sai method)
        message = _HTTP_MESSAGES.get(exc.status_code) or str(exc.detail)
        return error_response(
            exc.status_code, _http_error_code(exc.status_code), message, headers=exc.headers
        )
