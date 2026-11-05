import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)
    album_id: uuid.UUID | None = None


class UploadUrlResponse(BaseModel):
    media_id: uuid.UUID
    upload_url: str
    method: str = "PUT"
    # FE phải gửi đúng các header này khi PUT file lên upload_url
    headers: dict[str, str]
    expires_in: int


class CompleteUploadRequest(BaseModel):
    # Kích thước ảnh do FE đọc trước khi upload, giúp trang thiệp dựng layout không bị giật
    width: int | None = Field(default=None, gt=0, le=20000)
    height: int | None = Field(default=None, gt=0, le=20000)


class MediaOut(BaseModel):
    id: uuid.UUID
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


class MediaUpdate(BaseModel):
    """Gửi album_id = null để đưa ảnh ra khỏi album."""

    album_id: uuid.UUID | None = None


class ReorderRequest(BaseModel):
    media_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class AlbumCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AlbumUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    position: int | None = Field(default=None, ge=0)


class AlbumOut(BaseModel):
    id: uuid.UUID
    title: str
    position: int
    media_count: int
    created_at: datetime
