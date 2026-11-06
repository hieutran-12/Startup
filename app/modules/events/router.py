import uuid

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.core.deps import CurrentUser, DbSession
from app.core.revalidate import revalidate_invitation
from app.core.revision import IfMatch, etag
from app.modules.events import service
from app.modules.events.schemas import EventCreate, EventResponse, EventUpdate
from app.modules.invitations.models import Invitation

router = APIRouter(prefix="/invitations/{invitation_id}/events", tags=["events"])


def _after_write(response: Response, background: BackgroundTasks, invitation: Invitation) -> None:
    """ETag là revision mới của thiệp; thiệp đã publish thì báo Next.js build lại."""
    response.headers["ETag"] = etag(invitation.revision)
    if invitation.is_published:
        background.add_task(revalidate_invitation, invitation.slug)


@router.get("", response_model=list[EventResponse])
async def list_events(
    invitation_id: uuid.UUID, user: CurrentUser, db: DbSession, response: Response
) -> list[EventResponse]:
    """Danh sách theo thứ tự hiển thị. Header ETag là revision hiện tại của thiệp."""
    invitation, events = await service.list_for_invitation(db, user, invitation_id)
    response.headers["ETag"] = etag(invitation.revision)
    return [service.to_response(event) for event in events]


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    invitation_id: uuid.UUID,
    data: EventCreate,
    user: CurrentUser,
    if_match: IfMatch,  # sau CurrentUser: chưa đăng nhập thì 401 trước 428
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> EventResponse:
    invitation, event = await service.create(db, user, invitation_id, data, if_match)
    _after_write(response, background, invitation)
    return service.to_response(event)


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    invitation_id: uuid.UUID,
    event_id: uuid.UUID,
    data: EventUpdate,
    user: CurrentUser,
    if_match: IfMatch,
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> EventResponse:
    """JSON Merge Patch (nhận cả `application/merge-patch+json`), bắt buộc If-Match."""
    invitation, event, changed = await service.update(
        db, user, invitation_id, event_id, data, if_match
    )
    response.headers["ETag"] = etag(invitation.revision)
    if changed:
        _after_write(response, background, invitation)
    return service.to_response(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    invitation_id: uuid.UUID,
    event_id: uuid.UUID,
    user: CurrentUser,
    if_match: IfMatch,
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> None:
    """Response 204 có header ETag là revision mới của thiệp."""
    invitation = await service.delete(db, user, invitation_id, event_id, if_match)
    _after_write(response, background, invitation)
