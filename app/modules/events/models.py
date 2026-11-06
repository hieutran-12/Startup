import uuid
from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import TIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check


class EventType(StrEnum):
    ENGAGEMENT = "engagement"
    FAMILY_CEREMONY = "family_ceremony"
    RELIGIOUS_CEREMONY = "religious_ceremony"
    RECEPTION = "reception"
    OTHER = "other"


class HostSide(StrEnum):
    GROOM = "groom"
    BRIDE = "bride"
    BOTH = "both"


DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(enum_check("event_type", EventType), name="event_type_valid"),
        CheckConstraint(enum_check("host_side", HostSide), name="host_side_valid"),
        # Lễ gia tiên luôn thuộc một bên
        CheckConstraint(
            f"event_type <> '{EventType.FAMILY_CEREMONY}' OR host_side <> '{HostSide.BOTH}'",
            name="family_ceremony_single_side",
        ),
        CheckConstraint(
            f"event_type <> '{EventType.OTHER}' OR event_name IS NOT NULL",
            name="other_has_name",
        ),
        # V1 không hỗ trợ sự kiện kéo qua nửa đêm
        CheckConstraint(
            "end_time IS NULL OR (start_time IS NOT NULL AND end_time > start_time)",
            name="end_time_after_start_time",
        ),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coordinates_paired"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        Index("ix_events_invitation_position", "invitation_id", "position"),
    )

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(32))
    host_side: Mapped[str] = mapped_column(String(8))
    # null thì dùng tên mặc định theo loại lễ và bên
    event_name: Mapped[str | None] = mapped_column(String(120))
    # Được để trống khi còn nháp; bắt buộc khi publish (cùng start_time, address)
    event_date: Mapped[date | None] = mapped_column(Date)
    # Giờ địa phương tại địa điểm, đi kèm timezone
    start_time: Mapped[time | None] = mapped_column(TIME(precision=0))
    end_time: Mapped[time | None] = mapped_column(TIME(precision=0))
    timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=text(f"'{DEFAULT_TIMEZONE}'")
    )
    venue_name: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    # Link mở app chỉ đường; không parse lấy tọa độ từ link này
    maps_url: Mapped[str | None] = mapped_column(String(2048))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


def display_order() -> tuple[Any, ...]:
    """Thứ tự hiển thị (spec 04 › Sự kiện): ngày, rồi giờ bắt đầu, rồi position; chưa có ngày
    (hoặc chưa có giờ trong ngày) xếp cuối.

    Đặt ở models để invitations (điều kiện publish) dùng được mà không import events.service.
    """
    return (
        Event.event_date.asc().nulls_last(),
        Event.start_time.asc().nulls_last(),
        Event.position,
        Event.created_at,
        Event.id,
    )
