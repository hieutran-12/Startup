import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check
from app.modules.templates.models import Template


class InvitationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


# Bốn cột tham chiếu file cố định của thiệp (spec 03 › invitations)
MEDIA_REFERENCE_COLUMNS = (
    "cover_media_id",
    "groom_photo_media_id",
    "bride_photo_media_id",
    "music_media_id",
)


def _media_reference_fk(column: str) -> ForeignKeyConstraint:
    """Khóa ngoại kép (id, <cột>) -> media (invitation_id, id).

    Database từ chối file của thiệp khác; xoá file thì chỉ <cột> về null (PostgreSQL ≥ 15).
    Đặt tên tường minh vì naming convention sẽ đặt cả bốn khóa là fk_invitations_id_media.
    use_alter: hai bảng trỏ vào nhau, khóa được thêm sau khi tạo cả hai bảng.
    """
    return ForeignKeyConstraint(
        ["id", column],
        ["media.invitation_id", "media.id"],
        name=f"fk_invitations_{column.removesuffix('_id')}",
        ondelete=f"SET NULL ({column})",
        use_alter=True,
    )


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(enum_check("status", InvitationStatus), name="status_valid"),
        CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) BETWEEN 3 AND 60",
            name="slug_valid",
        ),
        CheckConstraint(
            f"(status = '{InvitationStatus.PUBLISHED}') = (published_at IS NOT NULL)",
            name="published_at_matches_status",
        ),
        CheckConstraint("content_schema_version > 0", name="content_schema_version_positive"),
        *(_media_reference_fk(column) for column in MEDIA_REFERENCE_COLUMNS),
    )

    # Chỉ dùng để phân quyền, không trả ra API public
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    title: Mapped[str] = mapped_column(String(120))  # tên nội bộ hiển thị ở dashboard
    status: Mapped[str] = mapped_column(
        String(16), default=InvitationStatus.DRAFT.value, server_default=text("'draft'")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Service luôn ghi object đầy đủ theo schema, không dựa vào DEFAULT của database
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_schema_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1")
    )
    # Tăng 1 sau mỗi lần ghi vào thiệp hoặc sự kiện của thiệp (chống ghi đè)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    cover_media_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    groom_photo_media_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    bride_photo_media_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    music_media_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Many-to-one, load luôn bằng JOIN (async không hỗ trợ lazy load)
    template: Mapped[Template] = relationship(lazy="joined", innerjoin=True)

    @property
    def template_key(self) -> str:
        return self.template.key

    @property
    def is_published(self) -> bool:
        return self.status == InvitationStatus.PUBLISHED
