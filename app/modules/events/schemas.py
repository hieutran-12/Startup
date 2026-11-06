"""Schema của module events (spec 03 › events, 04 › Sự kiện).

`EventCreate` kiểm tra cả các quy tắc nhiều cột (cùng nội dung với CHECK của bảng events) để trả
422 đúng trường thay vì để database từ chối. PATCH gộp bản đã lưu với patch rồi kiểm tra lại
bằng `EventCreate` (xem `service.update`).
"""

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from app.core.schemas import StrictModel, field_error
from app.core.types import (
    Choice,
    HttpUrl,
    IsoDate,
    Latitude,
    LocalTime,
    Longitude,
    SingleLine,
    Timezone,
)
from app.modules.events.models import DEFAULT_TIMEZONE, EventType, HostSide

_EVENT_NAME_DESCRIPTION = "Tên hiển thị tùy chỉnh; null thì dùng tên mặc định theo loại lễ và bên"


def rule_errors(event: "EventCreate") -> list[InitErrorDetails]:
    """Quy tắc nhiều cột (spec 03 › events). Lỗi gắn vào trường phụ thuộc (đề xuất 6, Bước 5)."""
    errors: list[InitErrorDetails] = []
    if event.event_type == EventType.FAMILY_CEREMONY and event.host_side == HostSide.BOTH:
        message = "Lễ gia tiên phải thuộc nhà trai hoặc nhà gái"
        errors.append(field_error(("host_side",), "invalid_choice", message, event.host_side))
    if event.event_type == EventType.OTHER and event.event_name is None:
        message = "Sự kiện loại khác cần có tên"
        errors.append(field_error(("event_name",), "required", message, None))
    if event.end_time is not None:
        if event.start_time is None:
            message = "Cần nhập giờ bắt đầu khi có giờ kết thúc"
            errors.append(field_error(("start_time",), "required", message, None))
        elif event.end_time <= event.start_time:  # v1 không hỗ trợ sự kiện qua nửa đêm
            message = "Giờ kết thúc phải sau giờ bắt đầu"
            errors.append(field_error(("end_time",), "out_of_range", message, event.end_time))
    if (event.latitude is None) != (event.longitude is None):
        missing = "latitude" if event.latitude is None else "longitude"
        message = "Cần nhập cả vĩ độ và kinh độ"
        errors.append(field_error((missing,), "required", message, None))
    return errors


class EventCreate(StrictModel):
    event_type: Choice(EventType)
    host_side: Choice(HostSide)
    event_name: SingleLine(120) = Field(default=None, description=_EVENT_NAME_DESCRIPTION)
    event_date: IsoDate | None = None  # bắt buộc khi publish
    start_time: LocalTime | None = None  # giờ địa phương theo timezone; bắt buộc khi publish
    end_time: LocalTime | None = None
    timezone: Timezone = DEFAULT_TIMEZONE
    venue_name: SingleLine(200) = None
    address: SingleLine(500) = None  # bắt buộc khi publish
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    # Link mở app chỉ đường; không parse lấy tọa độ từ link này
    maps_url: HttpUrl(2048) = None

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        if errors := rule_errors(self):
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self


class EventUpdate(StrictModel):
    """PATCH theo JSON Merge Patch: chỉ trường được gửi mới bị đổi; null là xoá giá trị.

    `event_type`, `host_side`, `timezone` không nhận null (422 `required`). Quy tắc nhiều cột
    được kiểm tra trên bản đã gộp.
    """

    event_type: Choice(EventType) = None
    host_side: Choice(HostSide) = None
    event_name: SingleLine(120) = Field(default=None, description=_EVENT_NAME_DESCRIPTION)
    event_date: IsoDate | None = None
    start_time: LocalTime | None = None
    end_time: LocalTime | None = None
    timezone: Timezone = None
    venue_name: SingleLine(200) = None
    address: SingleLine(500) = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    maps_url: HttpUrl(2048) = None


EVENT_FIELDS = tuple(EventCreate.model_fields)
"""Các cột client ghi được (không gồm id, invitation_id, position, thời điểm)."""


class EventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    host_side: str
    event_name: str | None
    display_name: str = Field(description="event_name, hoặc tên mặc định theo loại lễ và bên")
    event_date: date | None
    start_time: LocalTime | None
    end_time: LocalTime | None
    timezone: str
    venue_name: str | None
    address: str | None
    latitude: Latitude | None
    longitude: Longitude | None
    maps_url: str | None
    position: int = Field(description="Thứ tự tạo, chỉ dùng khi trùng cả ngày và giờ")
    created_at: datetime
    updated_at: datetime
