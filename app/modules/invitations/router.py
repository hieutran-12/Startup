import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.core.revalidate import revalidate_invitation
from app.core.storage import Storage, get_storage
from app.modules.invitations import service
from app.modules.invitations.schemas import (
    InvitationCreate,
    InvitationOut,
    InvitationUpdate,
    PublicInvitationOut,
    SlugAvailability,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])
public_router = APIRouter(prefix="/public", tags=["public"])

StorageDep = Annotated[Storage, Depends(get_storage)]


@router.get("", response_model=list[InvitationOut])
async def list_my_invitations(user: CurrentUser, db: DbSession) -> list[InvitationOut]:
    invitations = await service.list_for_owner(db, user)
    return [InvitationOut.model_validate(i) for i in invitations]


# Khai báo trước "/{invitation_id}" để không bị route đó bắt nhầm
@router.get("/slug-availability", response_model=SlugAvailability)
async def check_slug_availability(
    user: CurrentUser, db: DbSession, slug: Annotated[str, Query(max_length=100)]
) -> SlugAvailability:
    return await service.check_slug(db, slug)


@router.post("", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    data: InvitationCreate, user: CurrentUser, db: DbSession
) -> InvitationOut:
    invitation = await service.create(db, user, data)
    return InvitationOut.model_validate(invitation)


@router.get("/{invitation_id}", response_model=InvitationOut)
async def get_invitation(
    invitation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> InvitationOut:
    return InvitationOut.model_validate(await service.get_owned(db, user, invitation_id))


@router.patch("/{invitation_id}", response_model=InvitationOut)
async def update_invitation(
    invitation_id: uuid.UUID,
    data: InvitationUpdate,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> InvitationOut:
    invitation, slugs = await service.update(db, user, invitation_id, data)
    background.add_task(revalidate_invitation, *slugs)
    return InvitationOut.model_validate(invitation)


@router.post("/{invitation_id}/publish", response_model=InvitationOut)
async def publish_invitation(
    invitation_id: uuid.UUID, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> InvitationOut:
    invitation = await service.publish(db, user, invitation_id)
    background.add_task(revalidate_invitation, invitation.slug)
    return InvitationOut.model_validate(invitation)


@router.post("/{invitation_id}/unpublish", response_model=InvitationOut)
async def unpublish_invitation(
    invitation_id: uuid.UUID, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> InvitationOut:
    invitation = await service.unpublish(db, user, invitation_id)
    background.add_task(revalidate_invitation, invitation.slug)
    return InvitationOut.model_validate(invitation)


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


@public_router.get("/invitations/{slug}", response_model=PublicInvitationOut)
async def get_public_invitation(
    slug: str, response: Response, db: DbSession, storage: StorageDep
) -> PublicInvitationOut:
    result = await service.get_public(db, slug, storage)
    # Next.js/CDN cache ngắn hạn; nội dung mới được đẩy bằng revalidate on-demand
    response.headers["Cache-Control"] = (
        "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    )
    return result
