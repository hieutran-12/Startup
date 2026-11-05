import uuid
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MediaStatus(StrEnum):
    PENDING = "pending"  # đã cấp link upload, chưa xác nhận
    READY = "ready"


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
        CheckConstraint("status IN ('pending', 'ready')", name="status_valid"),
        Index("ix_media_invitation_position", "invitation_id", "position"),
    )

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE")
    )
    # Xoá album thì ảnh vẫn giữ lại trong thư viện chung của thiệp
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("albums.id", ondelete="SET NULL"), index=True
    )
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
