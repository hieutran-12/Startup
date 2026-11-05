import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings

# Đặt tên constraint cố định để Alembic sinh migration ổn định giữa các máy
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_check(column: str, values: type[StrEnum]) -> str:
    """Biểu thức CHECK `<cột> IN (...)` sinh từ StrEnum, để tập giá trị chỉ khai báo một chỗ."""
    return f"{column} IN ({', '.join(f"'{v.value}'" for v in values)})"


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    # Giá trị sinh ở phía Python để object luôn có sẵn sau commit
    # (async SQLAlchemy không cho lazy-load lại cột bị expire).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


engine = create_async_engine(settings.database_url, echo=settings.database_echo, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
