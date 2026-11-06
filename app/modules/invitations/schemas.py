"""Schema của module invitations.

Content v1 (spec 03 › Nội dung thiệp) là object đầy đủ: nhóm object luôn có mặt, văn bản không bắt
buộc là null, danh sách là [], boolean mặc định false (spec 02 › NULL, rỗng và mặc định).
Validate có context là kiểm tra content của request: `appearance` theo manifest của template
(`context={"manifest": TemplateManifest}`), `gifts[].bank_bin` theo danh sách ngân hàng (Bước 8).
Không có context (đọc content đã lưu để trả response) thì chỉ kiểm tra cấu trúc, nên BIN đã bị bỏ
khỏi danh sách vẫn đọc được.
"""

import unicodedata
import uuid
from datetime import date, datetime
from enum import StrEnum
from functools import partial
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    ValidationError,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.schemas import StrictModel, duplicate_errors, field_error
from app.core.types import (
    Choice,
    MultiLine,
    RequiredDigits,
    RequiredSingleLine,
    SingleLine,
    Uuid,
)
from app.modules.banks.service import is_known_bin
from app.modules.invitations.slugs import (
    SLUG_MAX_LENGTH,
    SLUG_MIN_LENGTH,
    SLUG_PATTERN,
    slug_error,
)
from app.modules.templates.schemas import Key, SectionKey, TemplateManifest

CONTENT_SCHEMA_VERSION = 1


class BirthOrder(StrEnum):
    ELDEST = "eldest"
    MIDDLE = "middle"
    YOUNGEST = "youngest"


class RecipientSide(StrEnum):
    GROOM = "groom"
    BRIDE = "bride"


# ---------- Nội dung thiệp (cột JSONB `content`, schema version 1) ----------


class Parent(StrictModel):
    full_name: SingleLine(100) = None
    # true thì template in chữ "Cố" trước tên; người dùng không gõ chữ này vào ô tên
    is_deceased: bool = False


class Person(StrictModel):
    full_name: SingleLine(100) = None  # bắt buộc khi publish
    display_name: SingleLine(40) = None  # tên in to trên thiệp; null thì dùng full_name
    birth_order: Choice(BirthOrder) | None = None
    bio: MultiLine(500) = None
    father: Parent = Field(default_factory=Parent)
    mother: Parent = Field(default_factory=Parent)
    family_address: SingleLine(300) = None


class Couple(StrictModel):
    groom: Person = Field(default_factory=Person)
    bride: Person = Field(default_factory=Person)


class Messages(StrictModel):
    greeting: MultiLine(1000) = None
    invitation_message: MultiLine(500) = None  # null thì template dùng câu mặc định
    guest_notes: MultiLine(1000) = None


class LoveStoryItem(StrictModel):
    title: RequiredSingleLine(100)
    description: MultiLine(1000) = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)  # chỉ được có khi đã có year
    media_id: Uuid | None = None  # ảnh ready của chính thiệp: service kiểm tra

    @model_validator(mode="after")
    def _month_needs_year(self) -> Self:
        if self.month is not None and self.year is None:
            error = field_error(("year",), "required", "Cần nhập năm khi có tháng", None)
            raise ValidationError.from_exception_data(type(self).__name__, [error])
        return self


class Gift(StrictModel):
    recipient_side: Choice(RecipientSide)
    bank_bin: RequiredDigits(6, 6)  # có trong danh sách ngân hàng (GET /banks)
    account_number: RequiredDigits(6, 19)  # giao diện bỏ khoảng trắng, dấu chấm trước khi gửi
    account_holder: RequiredSingleLine(100)

    @field_validator("bank_bin")
    @classmethod
    def _bank_in_list(cls, value: str, info: ValidationInfo) -> str:
        # Chỉ chạy khi đúng dạng 6 chữ số; chỉ kiểm tra content của request (có context)
        if info.context is not None and not is_known_bin(value):
            raise PydanticCustomError("invalid_choice", "Không có ngân hàng với mã BIN này")
        return value


def appearance_options(manifest: TemplateManifest) -> dict[str, set[str]]:
    """Trường key của appearance → các key manifest cho phép."""
    return {
        "palette_key": {item.key for item in manifest.palettes},
        "font_key": {item.key for item in manifest.fonts},
        "background_key": {item.key for item in manifest.backgrounds},
    }


_OPTION_DESCRIPTION = "Key có trong manifest của template; null thì dùng manifest.defaults"


class Appearance(StrictModel):
    # Key so khớp nguyên văn với manifest (không trim, không đổi chữ hoa thường)
    palette_key: str | None = Field(default=None, description=_OPTION_DESCRIPTION)
    font_key: str | None = Field(default=None, description=_OPTION_DESCRIPTION)
    background_key: str | None = Field(default=None, description=_OPTION_DESCRIPTION)
    # Section hiển thị theo đúng thứ tự; section không có trong danh sách bị ẩn
    sections: list[Choice(SectionKey)]

    @model_validator(mode="after")
    def _check_manifest(self, info: ValidationInfo) -> Self:
        errors = list(duplicate_errors("sections", self.sections))
        manifest: TemplateManifest | None = (info.context or {}).get("manifest")
        if manifest is not None:
            for field, keys in appearance_options(manifest).items():
                value = getattr(self, field)
                if value is not None and value not in keys:
                    message = f"Mẫu thiệp không có {value}"
                    errors.append(field_error((field,), "invalid_choice", message, value))
            errors += [
                field_error(
                    ("sections", index),
                    "invalid_choice",
                    f"Mẫu thiệp không có section {section}",
                    section,
                )
                for index, section in enumerate(self.sections)
                if section not in manifest.sections
            ]
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self


class InvitationContent(StrictModel):
    couple: Couple = Field(default_factory=Couple)
    messages: Messages = Field(default_factory=Messages)
    love_story: list[LoveStoryItem] = Field(default_factory=list, max_length=12)
    gifts: list[Gift] = Field(default_factory=list, max_length=4)
    appearance: Appearance  # không có mặc định: service lấy sections từ manifest.default_sections


# ---------- Request ----------


def _slug(value: str | None, *, required: bool) -> str | None:
    """NFC, trim, chữ thường; rỗng thì null hoặc required; sai quy tắc thì invalid_format."""
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value).strip().lower()
    if not value:
        if required:
            raise PydanticCustomError("required", "Không được để trống")
        return None
    if reason := slug_error(value):
        raise PydanticCustomError("invalid_format", reason)
    return value


_SLUG_SCHEMA = {
    "type": "string",
    "minLength": SLUG_MIN_LENGTH,
    "maxLength": SLUG_MAX_LENGTH,
    "pattern": SLUG_PATTERN.pattern,
}

Slug = Annotated[str, AfterValidator(partial(_slug, required=True)), WithJsonSchema(_SLUG_SCHEMA)]
OptionalSlug = Annotated[
    str | None,
    AfterValidator(partial(_slug, required=False)),
    WithJsonSchema({"anyOf": [_SLUG_SCHEMA, {"type": "null"}]}),
]

_CONTENT_PATCH_DESCRIPTION = (
    "JSON Merge Patch áp lên content (schema InvitationContent): không gửi thì giữ nguyên, "
    "null thì xoá giá trị (danh sách thành []), danh sách bị thay nguyên"
)


class InvitationCreate(StrictModel):
    template_key: Key
    title: SingleLine(120) = Field(
        default=None, description="Bỏ trống thì đặt theo tên cô dâu chú rể"
    )
    slug: OptionalSlug = Field(default=None, description="Bỏ trống thì tự sinh từ tên")
    # Gộp lên content mặc định (appearance.sections lấy từ manifest.default_sections)
    content: dict[str, Any] = Field(default=None, description=_CONTENT_PATCH_DESCRIPTION)


class InvitationUpdate(StrictModel):
    """PATCH theo JSON Merge Patch: chỉ trường được gửi mới bị đổi.

    `title`, `slug`, `template_key`, `content` không nhận null (422 `required`);
    `*_media_id` gửi null thì gỡ file khỏi thiệp.
    """

    title: RequiredSingleLine(120) = None
    slug: Slug = None
    template_key: Key = None
    content: dict[str, Any] = Field(default=None, description=_CONTENT_PATCH_DESCRIPTION)
    cover_media_id: Uuid | None = None
    groom_photo_media_id: Uuid | None = None
    bride_photo_media_id: Uuid | None = None
    music_media_id: Uuid | None = None


# ---------- Response ----------


class InvitationResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    status: str
    template_key: str
    content_schema_version: int
    revision: int
    content: InvitationContent
    cover_media_id: uuid.UUID | None
    groom_photo_media_id: uuid.UUID | None
    bride_photo_media_id: uuid.UUID | None
    music_media_id: uuid.UUID | None
    primary_event_date: date | None = Field(description="MIN(events.event_date) của thiệp")
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SlugAvailability(BaseModel):
    slug: str
    available: bool
    reason: str | None = None


# Response public giữ dạng khung, đổi ở Bước 10
class PublicAlbum(BaseModel):
    id: uuid.UUID
    title: str
    position: int


class PublicMedia(BaseModel):
    id: uuid.UUID
    album_id: uuid.UUID | None
    url: str
    width: int | None
    height: int | None


class PublicInvitationOut(BaseModel):
    slug: str
    template_key: str
    content: dict[str, Any]
    published_at: datetime | None
    updated_at: datetime
    albums: list[PublicAlbum]
    media: list[PublicMedia]
