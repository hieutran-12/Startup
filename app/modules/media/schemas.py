"""Schema của module media (spec 03 › media, 05; quy tắc phụ Bước 7: docs/modules/media.md).

`kind` suy ra từ `content_type`, client không gửi. Lỗi gắn với một trường trả 422 (`content_type`,
`size_bytes`, `album_id`); vượt số lượng file là lỗi nghiệp vụ 400 `media_limit` ở service.
"""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from app.core.config import settings
from app.core.schemas import StrictModel, field_error
from app.core.types import Choice, RequiredSingleLine, Uuid
from app.modules.media.models import MediaKind, MediaMimeType

_MB = 1024 * 1024
AUDIO_NOT_IN_ALBUM = "File âm thanh không nằm trong album"


def max_size_bytes(kind: MediaKind) -> int:
    return settings.max_image_bytes if kind == MediaKind.IMAGE else settings.max_audio_bytes


def size_limit_message(kind: MediaKind) -> str:
    label = "Ảnh" if kind == MediaKind.IMAGE else "File âm thanh"
    return f"{label} tối đa {max_size_bytes(kind) // _MB} MB"


class UploadUrlRequest(StrictModel):
    filename: RequiredSingleLine(255)
    content_type: Choice(MediaMimeType) = Field(
        description="image/* là ảnh, audio/* là âm thanh; FE PUT file với đúng Content-Type này"
    )
    size_bytes: int = Field(gt=0, description="Ảnh tối đa 15 MB, âm thanh tối đa 10 MB")
    album_id: Uuid | None = Field(default=None, description="Chỉ ảnh mới nằm trong album")

    @model_validator(mode="after")
    def _check_kind_rules(self) -> Self:
        kind = self.content_type.kind
        errors: list[InitErrorDetails] = []
        if self.size_bytes > max_size_bytes(kind):
            message = size_limit_message(kind)
            errors.append(field_error(("size_bytes",), "out_of_range", message, self.size_bytes))
        if kind == MediaKind.AUDIO and self.album_id is not None:
            value = str(self.album_id)
            errors.append(
                field_error(("album_id",), "invalid_reference", AUDIO_NOT_IN_ALBUM, value)
            )
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self


class UploadUrlResponse(BaseModel):
    media_id: uuid.UUID
    upload_url: str
    method: str = "PUT"
    # FE phải gửi đúng các header này khi PUT file lên upload_url
    headers: dict[str, str]
    expires_in: int


class CompleteUploadRequest(StrictModel):
    # Kích thước ảnh do FE đọc trước khi upload, giúp trang thiệp dựng layout không bị giật.
    # File âm thanh không có kích thước: gửi khác null thì 422 (service kiểm tra).
    width: int | None = Field(default=None, gt=0, le=20000)
    height: int | None = Field(default=None, gt=0, le=20000)


class MediaResponse(BaseModel):
    id: uuid.UUID
    kind: str
    album_id: uuid.UUID | None
    url: str
    original_filename: str | None
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    status: str
    position: int
    created_at: datetime


class MediaUpdate(StrictModel):
    """Không gửi `album_id` thì giữ nguyên; gửi null để đưa ảnh ra khỏi album."""

    album_id: Uuid | None = None


class ReorderRequest(StrictModel):
    """Thứ tự ảnh trong thư viện; chỉ nhận id ảnh của thiệp."""

    media_ids: list[Uuid] = Field(min_length=1, max_length=500)


class AlbumCreate(StrictModel):
    title: RequiredSingleLine(120)


class AlbumUpdate(StrictModel):
    """Không gửi trường thì giữ nguyên; `title`, `position` không nhận null (422 `required`)."""

    title: RequiredSingleLine(120) = None
    position: int = Field(default=None, ge=0)


class AlbumResponse(BaseModel):
    id: uuid.UUID
    title: str
    position: int
    media_count: int
    created_at: datetime
