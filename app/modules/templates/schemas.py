"""Schema của module templates.

`TemplateManifest` là hợp đồng giữa backend và component React của template (spec 03 › templates).
Seed kiểm tra manifest bằng schema này; `GET /templates` trả manifest theo đúng schema đó.
Quy tắc phụ chốt ở Bước 3: danh sách không trùng và có ít nhất 1 phần tử, key snake_case tối đa
64 ký tự, không trim. Phần tử trùng trả `invalid_format`, tham chiếu tới giá trị không có trong
danh sách trả `invalid_choice`.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    WithJsonSchema,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.core.schemas import StrictModel
from app.core.types import Choice, MultiLine, RequiredSingleLine
from app.modules.templates.models import TemplateCategory


class SectionKey(StrEnum):
    """Key section cố định của v1 (spec 03 › Nội dung thiệp › appearance)."""

    COVER = "cover"
    GREETING = "greeting"
    COUPLE = "couple"
    LOVE_STORY = "love_story"
    EVENTS = "events"
    COUNTDOWN = "countdown"
    GALLERY = "gallery"
    GIFTS = "gifts"
    GUEST_NOTES = "guest_notes"


# ---------- Kiểu dùng trong manifest ----------

KEY_MAX_LENGTH = 64  # bằng templates.key VARCHAR(64)
_KEY = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
_HEX_COLOR = re.compile(r"#[0-9A-F]{6}")


def _key(value: str) -> str:
    # Key là mã định danh nên không trim, không đổi chữ hoa thường: sai là từ chối
    if not value:
        raise PydanticCustomError("required", "Không được để trống")
    if len(value) > KEY_MAX_LENGTH:
        raise PydanticCustomError(
            "string_too_long", "Tối đa {max_length} ký tự", {"max_length": KEY_MAX_LENGTH}
        )
    if not _KEY.fullmatch(value):
        raise PydanticCustomError(
            "invalid_format", "Key phải là snake_case chữ thường, ví dụ classic_01"
        )
    return value


Key = Annotated[
    str,
    AfterValidator(_key),
    WithJsonSchema(
        {
            "type": "string",
            "maxLength": KEY_MAX_LENGTH,
            "pattern": f"^{_KEY.pattern}$",
            "examples": ["classic_01"],
        }
    ),
]
"""Key snake_case chữ thường của template, palette, font, nền (spec 02 › Quy ước đặt tên)."""


def _hex_color(value: str) -> str:
    if not _HEX_COLOR.fullmatch(value):
        raise PydanticCustomError(
            "invalid_format", "Màu phải có dạng #RRGGBB chữ hoa, ví dụ #B08D57"
        )
    return value


HexColor = Annotated[
    str,
    AfterValidator(_hex_color),
    WithJsonSchema(
        {"type": "string", "pattern": f"^{_HEX_COLOR.pattern}$", "examples": ["#B08D57"]}
    ),
]
"""Màu dạng #RRGGBB chữ hoa. Không tự đổi chữ thường sang chữ hoa."""


# ---------- Manifest ----------


class Palette(StrictModel):
    key: Key
    name: RequiredSingleLine(120)
    primary: HexColor
    secondary: HexColor
    background: HexColor
    text: HexColor


class ManifestOption(StrictModel):
    """Một lựa chọn trong `fonts` hoặc `backgrounds`."""

    key: Key
    name: RequiredSingleLine(120)


class ManifestDefaults(StrictModel):
    palette_key: Key
    font_key: Key
    background_key: Key


def _error(loc: tuple[str | int, ...], code: str, message: str, value: object) -> InitErrorDetails:
    return InitErrorDetails(type=PydanticCustomError(code, message), loc=loc, input=value)


def _duplicates(
    field: str, values: Sequence[object], *, suffix: tuple[str, ...] = ()
) -> Iterable[InitErrorDetails]:
    """Lỗi cho mỗi phần tử trùng với một phần tử đứng trước nó."""
    seen: set[object] = set()
    for index, value in enumerate(values):
        if value in seen:
            yield _error((field, index, *suffix), "invalid_format", f"Bị trùng: {value}", value)
        seen.add(value)


class TemplateManifest(StrictModel):
    """Những gì template hỗ trợ: section, palette, font, nền, giá trị mặc định."""

    sections: list[Choice(SectionKey)] = Field(min_length=1)
    default_sections: list[Choice(SectionKey)] = Field(min_length=1)
    palettes: list[Palette] = Field(min_length=1)
    fonts: list[ManifestOption] = Field(min_length=1)
    backgrounds: list[ManifestOption] = Field(min_length=1)
    defaults: ManifestDefaults
    max_gallery_images: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        # Chỉ chạy khi mọi trường đã hợp lệ. Raise ValidationError để mỗi lỗi có đường dẫn riêng
        # (ví dụ default_sections[1], defaults.palette_key); Pydantic nối thêm tiền tố bên ngoài.
        errors = [
            *_duplicates("sections", self.sections),
            *_duplicates("default_sections", self.default_sections),
        ]
        errors += [
            _error(
                ("default_sections", index),
                "invalid_choice",
                f"{section} không có trong sections",
                section,
            )
            for index, section in enumerate(self.default_sections)
            if section not in self.sections
        ]
        options = {
            "palette_key": ("palettes", self.palettes),
            "font_key": ("fonts", self.fonts),
            "background_key": ("backgrounds", self.backgrounds),
        }
        for default_field, (field, items) in options.items():
            keys = [item.key for item in items]
            errors += _duplicates(field, keys, suffix=("key",))
            value = getattr(self.defaults, default_field)
            if value not in keys:
                errors.append(
                    _error(
                        ("defaults", default_field),
                        "invalid_choice",
                        f"{value} không có trong {field}",
                        value,
                    )
                )
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self


# ---------- Template ----------


class TemplateCreate(StrictModel):
    """Một mẫu trong danh sách seed (app/scripts/seed_templates.py). Không có endpoint tạo mẫu.

    Mọi cột seed được đều có mặt (kể cả cột có mặc định) để chạy lại seed thì ghi đè đủ.
    """

    key: Key
    name: RequiredSingleLine(120)
    description: MultiLine(500) = None
    category: Choice(TemplateCategory)
    is_premium: bool = False
    position: int = Field(ge=0)
    manifest: TemplateManifest


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None
    thumbnail_url: str | None
    category: str
    is_premium: bool
    manifest: TemplateManifest
