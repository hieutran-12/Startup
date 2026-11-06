import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession
from app.core.revalidate import revalidate_invitation
from app.core.revision import IfMatch, etag
from app.core.storage import Storage, get_storage
from app.core.types import Choice
from app.modules.invitations import service
from app.modules.invitations.models import Invitation
from app.modules.invitations.schemas import (
    InvitationCreate,
    InvitationResponse,
    InvitationUpdate,
    PublicInvitationResponse,
    RecipientSide,
    SlugAvailabilityResponse,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])
public_router = APIRouter(prefix="/public", tags=["public"])

StorageDep = Annotated[Storage, Depends(get_storage)]


async def _respond(
    db: AsyncSession, response: Response, invitation: Invitation
) -> InvitationResponse:
    """Response của một thiệp: kèm header ETag chứa revision (spec 04 › Sửa thiệp)."""
    response.headers["ETag"] = etag(invitation.revision)
    return await service.to_response(db, invitation)


@router.get("", response_model=list[InvitationResponse])
async def list_my_invitations(user: CurrentUser, db: DbSession) -> list[InvitationResponse]:
    return await service.list_for_owner(db, user)


# Khai báo trước "/{invitation_id}" để không bị route đó bắt nhầm
@router.get("/slug-availability", response_model=SlugAvailabilityResponse)
async def check_slug_availability(
    user: CurrentUser, db: DbSession, slug: Annotated[str, Query(max_length=100)]
) -> SlugAvailabilityResponse:
    return await service.check_slug(db, slug)


@router.post("", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    data: InvitationCreate, user: CurrentUser, db: DbSession, response: Response
) -> InvitationResponse:
    invitation = await service.create(db, user, data)
    return await _respond(db, response, invitation)


@router.get("/{invitation_id}", response_model=InvitationResponse)
async def get_invitation(
    invitation_id: uuid.UUID, user: CurrentUser, db: DbSession, response: Response
) -> InvitationResponse:
    invitation = await service.get_owned(db, user, invitation_id)
    return await _respond(db, response, invitation)


@router.patch("/{invitation_id}", response_model=InvitationResponse)
async def update_invitation(
    invitation_id: uuid.UUID,
    data: InvitationUpdate,
    user: CurrentUser,
    if_match: IfMatch,  # sau CurrentUser: chưa đăng nhập thì 401 trước 428
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> InvitationResponse:
    """JSON Merge Patch (nhận cả `application/merge-patch+json`), bắt buộc If-Match."""
    invitation, slugs = await service.update(db, user, invitation_id, data, if_match)
    if slugs:
        background.add_task(revalidate_invitation, *slugs)
    return await _respond(db, response, invitation)


@router.post("/{invitation_id}/publish", response_model=InvitationResponse)
async def publish_invitation(
    invitation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> InvitationResponse:
    invitation = await service.publish(db, user, invitation_id)
    background.add_task(revalidate_invitation, invitation.slug)
    return await _respond(db, response, invitation)


@router.post("/{invitation_id}/unpublish", response_model=InvitationResponse)
async def unpublish_invitation(
    invitation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> InvitationResponse:
    invitation = await service.unpublish(db, user, invitation_id)
    background.add_task(revalidate_invitation, invitation.slug)
    return await _respond(db, response, invitation)


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invitation(
    invitation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    background: BackgroundTasks,
) -> None:
    slug, was_published, keys = await service.delete(db, user, invitation_id)
    for key in keys:
        background.add_task(storage.delete, key)
    if was_published:
        background.add_task(revalidate_invitation, slug)


_SIDE_DESCRIPTION = (
    "groom (link nhà trai) hoặc bride (link nhà gái): chỉ trả sự kiện của bên đó và của cả "
    "hai bên, cùng tài khoản mừng cưới của bên đó. Không gửi thì trả tất cả"
)


@public_router.get("/invitations/{slug}", response_model=PublicInvitationResponse)
async def get_public_invitation(
    slug: str,
    response: Response,
    db: DbSession,
    storage: StorageDep,
    side: Annotated[Choice(RecipientSide) | None, Query(description=_SIDE_DESCRIPTION)] = None,
) -> PublicInvitationResponse:
    """Trang public theo slug (spec 05 › Response của trang public). `side` sai giá trị → 422."""
    result = await service.get_public(db, slug, side, storage)
    # Next.js/CDN cache ngắn hạn; nội dung mới được đẩy bằng revalidate on-demand
    response.headers["Cache-Control"] = (
        "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    )
    return result
