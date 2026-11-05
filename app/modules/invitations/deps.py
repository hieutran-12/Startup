import uuid
from typing import Annotated

from fastapi import Depends

from app.core.deps import CurrentUser, DbSession
from app.modules.invitations import service
from app.modules.invitations.models import Invitation


async def get_owned_invitation(
    invitation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Invitation:
    """Dùng cho các route con /invitations/{invitation_id}/...: chỉ chủ thiệp mới truy cập được."""
    return await service.get_owned(db, user, invitation_id)


OwnedInvitation = Annotated[Invitation, Depends(get_owned_invitation)]
