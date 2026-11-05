import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.templates.models import Template


class InvitationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = (CheckConstraint("status IN ('draft', 'published')", name="status_valid"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    title: Mapped[str] = mapped_column(String(120))  # tên nội bộ hiển thị ở dashboard
    status: Mapped[str] = mapped_column(
        String(20), default=InvitationStatus.DRAFT.value, server_default=text("'draft'")
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    event_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Many-to-one, load luôn bằng JOIN (async không hỗ trợ lazy load)
    template: Mapped[Template] = relationship(lazy="joined", innerjoin=True)

    @property
    def template_key(self) -> str:
        return self.template.key

    @property
    def is_published(self) -> bool:
        return self.status == InvitationStatus.PUBLISHED
