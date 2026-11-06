from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict
from pydantic_core import InitErrorDetails, PydanticCustomError


class StrictModel(BaseModel):
    """Base model cho schema request (spec 02 › Quy tắc trên API).

    - strict=True: số và boolean không nhận chuỗi ("2", "02", "true" bị từ chối).
    - extra="forbid": trường không có trong schema trả 422, mã `unknown_field`.

    Chuỗi phải khai báo bằng kiểu trong app/core/types.py để được trim và chuẩn hóa NFC.
    UUID, ngày, giờ và enum cũng dùng kiểu ở đó (Uuid, IsoDate, LocalTime, Choice), vì strict
    ở chế độ Python từ chối các giá trị này khi chúng ở dạng chuỗi.
    """

    model_config = ConfigDict(strict=True, extra="forbid")


# ---------- Lỗi tham chiếu chéo trong model_validator ----------
# Gom các lỗi rồi `raise ValidationError.from_exception_data(<tên model>, errors)`: Pydantic giữ
# `loc` của từng lỗi và nối tiền tố bên ngoài (ví dụ content.appearance.sections[1]).


def field_error(
    loc: tuple[str | int, ...], code: str, message: str, value: object
) -> InitErrorDetails:
    """Một lỗi có mã spec (`code`) tại `loc`, tính từ model đang validate."""
    return InitErrorDetails(type=PydanticCustomError(code, message), loc=loc, input=value)


def duplicate_errors(
    field: str, values: Sequence[object], *, suffix: tuple[str, ...] = ()
) -> Iterable[InitErrorDetails]:
    """`invalid_format` cho mỗi phần tử trùng với một phần tử đứng trước nó."""
    seen: set[object] = set()
    for index, value in enumerate(values):
        if value in seen:
            yield field_error(
                (field, index, *suffix), "invalid_format", f"Bị trùng: {value}", value
            )
        seen.add(value)
