"""Sự kiện của thiệp (spec 04 › Sự kiện, Sửa thiệp).

Mọi thao tác ghi: khóa dòng thiệp (`SELECT … FOR UPDATE`), kiểm tra If-Match với revision của
thiệp, ghi sự kiện rồi tăng revision của thiệp. Khóa này cũng giữ giới hạn 10 sự kiện khi có
request đồng thời. Thiệp đã publish: flush thay đổi rồi kiểm tra điều kiện publish trên trạng thái
mới trước khi commit (spec 04 › Publish). Thứ tự kiểm tra: xem docs/modules/events.md.
"""

import uuid
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import bad_request, error_details, not_found, validation_error
from app.core.revision import check_revision
from app.modules.auth.models import User
from app.modules.events.models import Event, display_order
from app.modules.events.schemas import EVENT_FIELDS, EventCreate, EventResponse, EventUpdate
from app.modules.invitations import service as invitation_service
from app.modules.invitations.models import Invitation

# ---------- Response ----------


def to_response(event: Event) -> EventResponse:
    """`display_name` tính trong schema (tên mặc định: `models.default_event_name`)."""
    return EventResponse.model_validate(event, from_attributes=True)


# ---------- Đọc ----------


async def list_for_invitation(
    db: AsyncSession, owner: User, invitation_id: uuid.UUID
) -> tuple[Invitation, list[Event]]:
    invitation = await invitation_service.get_owned(db, owner, invitation_id)
    events = await db.scalars(
        select(Event).where(Event.invitation_id == invitation.id).order_by(*display_order())
    )
    return invitation, list(events)


# ---------- Ghi ----------


async def _lock_invitation(
    db: AsyncSession, owner: User, invitation_id: uuid.UUID, if_match: str
) -> Invitation:
    invitation = await invitation_service.get_owned(db, owner, invitation_id, for_update=True)
    check_revision(if_match, invitation.revision)
    return invitation


async def _get_event(db: AsyncSession, invitation: Invitation, event_id: uuid.UUID) -> Event:
    event = await db.scalar(
        select(Event).where(Event.id == event_id, Event.invitation_id == invitation.id)
    )
    if event is None:
        raise not_found("event_not_found", "Không tìm thấy sự kiện")
    return event


def _column_values(data: EventCreate) -> dict[str, Any]:
    """Giá trị ghi vào cột: enum thành chuỗi, còn lại giữ kiểu Python (date, time, Decimal)."""
    return {
        field: value.value if isinstance(value, StrEnum) else value
        for field, value in ((field, getattr(data, field)) for field in EVENT_FIELDS)
    }


async def _commit(db: AsyncSession, invitation: Invitation) -> None:
    """Thiệp đã publish phải còn đủ điều kiện publish sau thay đổi: flush để đọc danh sách sự kiện
    mới theo thứ tự hiển thị; không đạt thì rollback, 400 `breaks_published_invitation`."""
    if invitation.is_published:
        await db.flush()
        await invitation_service.check_still_publishable(db, invitation)
    await db.commit()


async def create(
    db: AsyncSession, owner: User, invitation_id: uuid.UUID, data: EventCreate, if_match: str
) -> tuple[Invitation, Event]:
    invitation = await _lock_invitation(db, owner, invitation_id, if_match)
    count = await db.scalar(
        select(func.count()).select_from(Event).where(Event.invitation_id == invitation.id)
    )
    count = count or 0
    if count >= settings.max_events_per_invitation:
        raise bad_request(
            "event_limit", f"Mỗi thiệp tối đa {settings.max_events_per_invitation} sự kiện"
        )

    # position liên tục từ 0 (xoá thì đánh số lại), nên sự kiện mới nhận position = số hiện có
    event = Event(invitation_id=invitation.id, position=count, **_column_values(data))
    db.add(event)
    invitation.revision += 1
    await _commit(db, invitation)
    return invitation, event


def _merge(event: Event, data: EventUpdate) -> dict[str, Any]:
    """JSON Merge Patch phẳng: trường được gửi thay giá trị đã lưu, null là xoá."""
    stored: Mapping[str, Any] = {field: getattr(event, field) for field in EVENT_FIELDS}
    return {**stored, **{field: getattr(data, field) for field in data.model_fields_set}}


async def update(
    db: AsyncSession,
    owner: User,
    invitation_id: uuid.UUID,
    event_id: uuid.UUID,
    data: EventUpdate,
    if_match: str,
) -> tuple[Invitation, Event, bool]:
    """Trả về (thiệp, sự kiện, có thay đổi hay không). Không đổi gì thì không ghi."""
    invitation = await _lock_invitation(db, owner, invitation_id, if_match)
    event = await _get_event(db, invitation, event_id)
    try:
        merged = EventCreate.model_validate(_merge(event, data))
    except ValidationError as exc:
        raise validation_error(error_details(exc.errors())) from exc

    changes = {
        field: value
        for field, value in _column_values(merged).items()
        if value != getattr(event, field)
    }
    if not changes:
        return invitation, event, False
    for field, value in changes.items():
        setattr(event, field, value)
    invitation.revision += 1
    await _commit(db, invitation)
    return invitation, event, True


def _renumber(events: Sequence[Event]) -> None:
    for position, event in enumerate(events):
        if event.position != position:
            event.position = position


async def delete(
    db: AsyncSession, owner: User, invitation_id: uuid.UUID, event_id: uuid.UUID, if_match: str
) -> Invitation:
    invitation = await _lock_invitation(db, owner, invitation_id, if_match)
    event = await _get_event(db, invitation, event_id)
    await db.delete(event)
    # Giữ position liên tục 0..n-1 theo thứ tự position cũ (spec 02 › Thứ tự hiển thị)
    remaining = await db.scalars(
        select(Event)
        .where(Event.invitation_id == invitation.id, Event.id != event.id)
        .order_by(Event.position, Event.created_at, Event.id)
    )
    _renumber(list(remaining))
    invitation.revision += 1
    await _commit(db, invitation)
    return invitation
