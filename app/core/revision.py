"""Chống ghi đè bằng revision: header ETag và If-Match (spec 04 › Sửa thiệp).

Response của một thiệp có `ETag: "<revision>"`. Request ghi (PATCH thiệp, ghi sự kiện) phải gửi
`If-Match: "<revision>"`: thiếu thì 428 `revision_required`, khác revision hiện tại thì 409
`revision_conflict` kèm header ETag chứa revision mới nhất. If-Match chỉ khớp khi đúng nguyên
chuỗi `"<revision>"`; dạng khác (`5` thiếu ngoặc kép, `W/"5"`, `*`, danh sách) coi như không khớp.
"""

from typing import Annotated

from fastapi import Depends, Header, status

from app.core.errors import AppError


def etag(revision: int) -> str:
    return f'"{revision}"'


async def require_if_match(
    if_match: Annotated[
        str | None,
        Header(description='Revision đang sửa, lấy từ header ETag, ví dụ "3"'),
    ] = None,
) -> str:
    if if_match is None:
        raise AppError(
            status.HTTP_428_PRECONDITION_REQUIRED,
            "revision_required",
            'Cần gửi header If-Match: "<revision>" lấy từ ETag',
        )
    return if_match


IfMatch = Annotated[str, Depends(require_if_match)]
"""Giá trị header If-Match (bắt buộc). Kiểm tra với revision hiện tại bằng `check_revision`."""


def check_revision(if_match: str, current: int) -> None:
    """Gọi sau khi đã khóa dòng (SELECT … FOR UPDATE), trước mọi kiểm tra khác của request."""
    if if_match.strip() != etag(current):
        raise AppError(
            status.HTTP_409_CONFLICT,
            "revision_conflict",
            "Thiệp vừa được sửa ở nơi khác, hãy tải lại bản mới nhất",
            headers={"ETag": etag(current)},
        )
