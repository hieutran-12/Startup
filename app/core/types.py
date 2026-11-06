"""Kiểu dữ liệu chuẩn cho schema request.

Spec: 02 › Quy chuẩn dữ liệu, 04 › Chuẩn hóa chuỗi. Khi sai, mỗi kiểu raise PydanticCustomError
có `type` là mã lỗi của spec 05 (required, invalid_format...); handler trong app/core/errors.py
giữ nguyên mã đó. Riêng quá độ dài dùng `string_too_long` của Pydantic, vì `too_long` của Pydantic
là lỗi độ dài danh sách.

FastAPI validate body ở chế độ Python, nên trong StrictModel các kiểu gốc uuid.UUID, date, time
và Enum từ chối giá trị dạng chuỗi. Vì vậy dùng Uuid, IsoDate, LocalTime, Choice(...) ở đây.
"""

import contextlib
import math
import re
import unicodedata
import uuid
import zoneinfo
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from functools import cache, partial
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AfterValidator, PlainSerializer, PlainValidator, Strict, WithJsonSchema
from pydantic_core import PydanticCustomError

# Ký tự điều khiển (Unicode Cc: U+0000–U+001F, U+007F–U+009F) và ký tự ngắt dòng U+2028, U+2029
_SINGLE_LINE_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
# Nhiều dòng cho phép \t (U+0009) và \n (U+000A); \r đã được đổi thành \n trước khi kiểm tra
_MULTI_LINE_FORBIDDEN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f  ]")
# Sau khi đã chặn ký tự điều khiển, \s chỉ còn các dấu cách Unicode (Zs, gồm cả NBSP)
_SPACES = re.compile(r"\s+")
_MAX_BLANK_LINES = 2

# URL không được chứa khoảng trắng (kể cả dấu cách Unicode) hay ký tự điều khiển
_URL_FORBIDDEN = re.compile(r"[\s\x00-\x1f\x7f-\x9f]")
# Scheme không phân biệt hoa thường (RFC 3986), giá trị vẫn giữ nguyên như client gửi
_URL_SCHEME = re.compile(r"https?://", re.IGNORECASE)

_DIGITS = re.compile(r"[0-9]+")
_TIME = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _required() -> PydanticCustomError:
    return PydanticCustomError("required", "Không được để trống")


def _empty_or_too_long(value: str, *, max_length: int, required: bool) -> str | None:
    """Bước 5–6 của chuẩn hóa chuỗi: rỗng thì null/required, rồi kiểm tra độ dài."""
    if not value:
        if required:
            raise _required()
        return None
    if len(value) > max_length:
        # Dùng loại lỗi có sẵn của Pydantic; handler đổi thành mã too_long kèm message tiếng Việt
        raise PydanticCustomError(
            "string_too_long", "Tối đa {max_length} ký tự", {"max_length": max_length}
        )
    return value


def _single_line(value: str | None, *, max_length: int, required: bool) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value).strip()
    if _SINGLE_LINE_FORBIDDEN.search(value):
        raise PydanticCustomError(
            "invalid_characters", "Không được chứa xuống dòng hoặc ký tự điều khiển"
        )
    value = _SPACES.sub(" ", value)
    return _empty_or_too_long(value, max_length=max_length, required=required)


def _limit_blank_lines(value: str) -> str:
    """Giữ tối đa 2 dòng trống liền nhau; dòng chỉ có khoảng trắng cũng là dòng trống."""
    kept: list[str] = []
    blank_run = 0
    for line in value.split("\n"):
        blank_run = blank_run + 1 if not line.strip() else 0
        if blank_run <= _MAX_BLANK_LINES:
            kept.append(line)
    return "\n".join(kept)


def _multi_line(value: str | None, *, max_length: int, required: bool) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value).strip()
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if _MULTI_LINE_FORBIDDEN.search(value):
        raise PydanticCustomError("invalid_characters", "Không được chứa ký tự điều khiển")
    value = _limit_blank_lines(value)
    return _empty_or_too_long(value, max_length=max_length, required=required)


def _digits(value: str | None, *, min_length: int, max_length: int, required: bool) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value).strip()
    if not value:
        if required:
            raise _required()
        return None
    if not (min_length <= len(value) <= max_length and _DIGITS.fullmatch(value)):
        template = (
            "Phải gồm đúng {min_length} chữ số"
            if min_length == max_length
            else "Phải gồm {min_length}–{max_length} chữ số"
        )
        raise PydanticCustomError(
            "invalid_format", template, {"min_length": min_length, "max_length": max_length}
        )
    return value


def _string_schema(schema: dict[str, Any], *, nullable: bool) -> WithJsonSchema:
    schema = {"type": "string", **schema}
    return WithJsonSchema({"anyOf": [schema, {"type": "null"}]} if nullable else schema)


# ---------- Văn bản ----------


def SingleLine(max_length: int) -> Any:
    """Văn bản một dòng không bắt buộc (tên, địa điểm). Rỗng sau chuẩn hóa thì thành None."""
    validate = partial(_single_line, max_length=max_length, required=False)
    return Annotated[
        str | None,
        AfterValidator(validate),
        _string_schema({"maxLength": max_length}, nullable=True),
    ]


def RequiredSingleLine(max_length: int) -> Any:
    """Văn bản một dòng bắt buộc. Rỗng, null hoặc thiếu đều trả `required`."""
    validate = partial(_single_line, max_length=max_length, required=True)
    return Annotated[
        str, AfterValidator(validate), _string_schema({"maxLength": max_length}, nullable=False)
    ]


def MultiLine(max_length: int) -> Any:
    """Văn bản nhiều dòng không bắt buộc (lời ngỏ, câu chuyện)."""
    validate = partial(_multi_line, max_length=max_length, required=False)
    return Annotated[
        str | None,
        AfterValidator(validate),
        _string_schema({"maxLength": max_length}, nullable=True),
    ]


def RequiredMultiLine(max_length: int) -> Any:
    """Văn bản nhiều dòng bắt buộc."""
    validate = partial(_multi_line, max_length=max_length, required=True)
    return Annotated[
        str, AfterValidator(validate), _string_schema({"maxLength": max_length}, nullable=False)
    ]


# ---------- URL ----------


def _http_url(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value).strip()
    if not value:
        return None
    if _URL_FORBIDDEN.search(value) or not _URL_SCHEME.match(value):
        raise PydanticCustomError(
            "invalid_format",
            "Link phải bắt đầu bằng http:// hoặc https:// và không có khoảng trắng",
        )
    try:
        host = urlsplit(value).hostname
    except ValueError:  # ví dụ IPv6 thiếu dấu ], cổng không phải số
        host = None
    if not host:
        raise PydanticCustomError("invalid_format", "Link thiếu tên miền")
    return _empty_or_too_long(value, max_length=max_length, required=False)


def HttpUrl(max_length: int) -> Any:
    """Link http/https không bắt buộc (spec 02 › URL). Rỗng sau trim thì thành None.

    Chỉ NFC và trim, không chuẩn hóa gì thêm (không thêm "/", không đổi host): sai thì từ chối.
    Khác `pydantic.HttpUrl` (kiểu đó tự sửa URL).
    """
    validate = partial(_http_url, max_length=max_length)
    schema = {"format": "uri", "maxLength": max_length, "pattern": "^[Hh][Tt][Tt][Pp][Ss]?://"}
    return Annotated[str | None, AfterValidator(validate), _string_schema(schema, nullable=True)]


# ---------- Tọa độ ----------

_COORDINATE_DECIMAL_PLACES = 6  # NUMERIC(9,6)


def _coordinate(value: Any, *, limit: int, name: str) -> Decimal:
    # Request JSON cho int/float; Decimal là giá trị đọc từ database (kiểm tra lại bản đã gộp)
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise PydanticCustomError("invalid_format", "Tọa độ phải là số")
    if isinstance(value, float):
        if not math.isfinite(value):  # json.loads nhận NaN, Infinity
            raise PydanticCustomError("invalid_format", "Tọa độ phải là số")
        value = Decimal(repr(value))  # repr: chữ số ngắn nhất, giống số client đã viết
    number = Decimal(value)
    if not number.is_finite():
        raise PydanticCustomError("invalid_format", "Tọa độ phải là số")
    if not -limit <= number <= limit:
        raise PydanticCustomError("out_of_range", f"{name} phải trong khoảng -{limit} đến {limit}")
    exponent = number.normalize().as_tuple().exponent
    if isinstance(exponent, int) and -exponent > _COORDINATE_DECIMAL_PLACES:
        # Không tự làm tròn (spec 02 › nguyên tắc 11); NUMERIC(9,6) sẽ làm tròn âm thầm
        raise PydanticCustomError("invalid_format", "Tối đa 6 chữ số sau dấu thập phân")
    return number


def _coordinate_type(limit: int, name: str) -> Any:
    return Annotated[
        Decimal,
        PlainValidator(partial(_coordinate, limit=limit, name=name)),
        PlainSerializer(float, return_type=float, when_used="json"),
        WithJsonSchema({"type": "number", "minimum": -limit, "maximum": limit}),
    ]


Latitude = _coordinate_type(90, "Vĩ độ")
"""Vĩ độ [-90, 90], tối đa 6 chữ số thập phân. Nhận số JSON (không nhận chuỗi), trả số JSON."""

Longitude = _coordinate_type(180, "Kinh độ")
"""Kinh độ [-180, 180], tối đa 6 chữ số thập phân."""


# ---------- Mã định danh toàn chữ số ----------


def Digits(min_length: int, max_length: int) -> Any:
    """Chuỗi chỉ gồm 0-9 (số tài khoản, BIN), không bắt buộc. Giữ số 0 ở đầu."""
    validate = partial(_digits, min_length=min_length, max_length=max_length, required=False)
    pattern = f"^[0-9]{{{min_length},{max_length}}}$"
    return Annotated[
        str | None, AfterValidator(validate), _string_schema({"pattern": pattern}, nullable=True)
    ]


def RequiredDigits(min_length: int, max_length: int) -> Any:
    """Chuỗi chỉ gồm 0-9, bắt buộc."""
    validate = partial(_digits, min_length=min_length, max_length=max_length, required=True)
    pattern = f"^[0-9]{{{min_length},{max_length}}}$"
    return Annotated[
        str, AfterValidator(validate), _string_schema({"pattern": pattern}, nullable=False)
    ]


# ---------- Giờ, ngày, múi giờ ----------


def _parse_local_time(value: Any) -> time:
    if isinstance(value, time) and value.second == value.microsecond == 0 and not value.tzinfo:
        return value
    if isinstance(value, str) and (match := _TIME.fullmatch(value)):
        return time(int(match[1]), int(match[2]))
    raise PydanticCustomError("invalid_format", "Giờ phải có dạng HH:MM")


LocalTime = Annotated[
    time,
    PlainValidator(_parse_local_time),
    PlainSerializer(lambda value: value.strftime("%H:%M"), return_type=str, when_used="json"),
    WithJsonSchema(
        {"type": "string", "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "examples": ["18:30"]}
    ),
]
"""Giờ địa phương của sự kiện, đúng dạng "HH:MM" 24 giờ. Không trim, không nhận giây."""


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and _DATE.fullmatch(value):
        with contextlib.suppress(ValueError):  # ngày không tồn tại, ví dụ 2026-02-30
            return date.fromisoformat(value)
    raise PydanticCustomError("invalid_format", "Ngày phải có dạng YYYY-MM-DD")


IsoDate = Annotated[
    date,
    PlainValidator(_parse_date),
    PlainSerializer(date.isoformat, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date", "examples": ["2026-12-20"]}),
]
"""Ngày dạng "YYYY-MM-DD". Không nhận "20/12/2026", timestamp hay chuỗi có giờ."""


@cache
def _iana_timezones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def _timezone(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if not value:
        raise _required()
    # So khớp đúng tên trong danh sách: ZoneInfo() trên Windows không phân biệt hoa thường
    if value not in _iana_timezones():
        raise PydanticCustomError(
            "invalid_choice", "Múi giờ phải là tên IANA, ví dụ Asia/Ho_Chi_Minh"
        )
    return value


Timezone = Annotated[
    str,
    AfterValidator(_timezone),
    WithJsonSchema({"type": "string", "maxLength": 64, "examples": ["Asia/Ho_Chi_Minh"]}),
]
"""Tên múi giờ IANA, phân biệt hoa thường. Bắt buộc."""


# ---------- ID, enum ----------


def _parse_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str) and _UUID.fullmatch(value):
        return uuid.UUID(value)
    raise PydanticCustomError("invalid_format", "ID phải là UUID viết thường")


Uuid = Annotated[
    uuid.UUID,
    PlainValidator(_parse_uuid),
    PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "uuid"}),
]
"""ID dạng chuỗi UUID chữ thường có gạch nối (36 ký tự)."""


def Choice[E: Enum](enum_cls: type[E]) -> Any:
    """Giá trị của StrEnum, nhận dạng chuỗi. Sai giá trị trả `invalid_choice`."""
    return Annotated[enum_cls, Strict(False)]
