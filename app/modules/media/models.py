import uuid
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check


class MediaStatus(StrEnum):
    PENDING = "pending"  # đã cấp link upload, chưa xác nhận
    READY = "ready"


class MediaKind(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"


class MediaMimeType(StrEnum):
    """Loại file nhận upload (spec 03 › media › Loại file cho phép).

    `mime_type` lưu đúng loại client gửi: audio/mp3 và audio/x-m4a không bị đổi sang audio/mpeg,
    audio/mp4, vì link upload đã ký đúng Content-Type đó.
    """

    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    AVIF = "image/avif"
    MPEG = "audio/mpeg"
    MP3 = "audio/mp3"  # một số trình duyệt báo file .mp3 như vậy
    MP4 = "audio/mp4"
    X_M4A = "audio/x-m4a"  # trình duyệt thường báo file .m4a như vậy

    @property
    def kind(self) -> MediaKind:
        """image/* là ảnh, audio/* là âm thanh (spec 05 › upload-url)."""
        return MediaKind(self.value.split("/", 1)[0])

    @property
    def extension(self) -> str:
        """Đuôi file trong storage_key."""
        return _EXTENSIONS[self]


_EXTENSIONS = {
    MediaMimeType.JPEG: "jpg",
    MediaMimeType.PNG: "png",
    MediaMimeType.WEBP: "webp",
    MediaMimeType.AVIF: "avif",
    MediaMimeType.MPEG: "mp3",
    MediaMimeType.MP3: "mp3",
    MediaMimeType.MP4: "m4a",
    MediaMimeType.X_M4A: "m4a",
}


class Album(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "albums"

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class Media(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint(enum_check("status", MediaStatus), name="status_valid"),
        CheckConstraint(enum_check("kind", MediaKind), name="kind_valid"),
        # File âm thanh không có kích thước ảnh và không nằm trong album
        CheckConstraint(
            f"kind = '{MediaKind.IMAGE}' OR "
            "(width IS NULL AND height IS NULL AND album_id IS NULL)",
            name="audio_has_no_image_fields",
        ),
        # Đích đến của các khóa ngoại kép từ invitations (*_media_id)
        UniqueConstraint("invitation_id", "id"),
        Index("ix_media_invitation_position", "invitation_id", "position"),
    )

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE")
    )
    # Xoá album thì ảnh vẫn giữ lại trong thư viện chung của thiệp
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("albums.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default=MediaStatus.PENDING.value, server_default=text("'pending'")
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
