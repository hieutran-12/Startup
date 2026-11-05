from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, false, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check


class TemplateCategory(StrEnum):
    CLASSIC = "classic"
    MINIMAL = "minimal"
    FLORAL = "floral"
    VINTAGE = "vintage"
    MODERN = "modern"


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata của một mẫu thiệp. Phần giao diện nằm ở Next.js, tra theo `key`."""

    __tablename__ = "templates"
    __table_args__ = (
        CheckConstraint(enum_check("category", TemplateCategory), name="category_valid"),
    )

    key: Mapped[str] = mapped_column(String(64), unique=True)  # snake_case, ví dụ classic_01
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    # Ảnh hệ thống, không phải file người dùng upload
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048))
    category: Mapped[str] = mapped_column(String(32), index=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # Hợp đồng với component React của template (spec 03 › templates); không có DEFAULT
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
