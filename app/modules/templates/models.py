from typing import Any

from sqlalchemy import Boolean, Integer, String, Text, false, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata của một mẫu thiệp. Phần giao diện nằm ở Next.js, tra theo `key`."""

    __tablename__ = "templates"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(50), index=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # Các phần nội dung mẫu này hỗ trợ, để editor ở FE biết hiển thị ô nhập nào
    field_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
