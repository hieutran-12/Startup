import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status

from app.core.deps import DbSession
from app.core.revalidate import revalidate_invitation
from app.core.revision import etag
from app.core.storage import Storage, get_storage
from app.modules.invitations.deps import OwnedInvitation
from app.modules.invitations.models import Invitation
from app.modules.media import service
from app.modules.media.schemas import (
    AlbumCreate,
    AlbumResponse,
    AlbumUpdate,
    CompleteUploadRequest,
    MediaResponse,
    MediaUpdate,
    ReorderRequest,
    UploadUrlRequest,
    UploadUrlResponse,
)

router = APIRouter(prefix="/invitations/{invitation_id}", tags=["media"])

StorageDep = Annotated[Storage, Depends(get_storage)]


def _revalidate_if_published(background: BackgroundTasks, invitation: Invitation) -> None:
    if invitation.is_published:
        background.add_task(revalidate_invitation, invitation.slug)


# ---------- File (ảnh, âm thanh) ----------


@router.post("/media/upload-url", response_model=UploadUrlResponse)
async def create_upload_url(
    data: UploadUrlRequest, invitation: OwnedInvitation, db: DbSession, storage: StorageDep
) -> UploadUrlResponse:
    """Bước 1: xin link upload. Bước 2: FE PUT file lên `upload_url`. Bước 3: gọi /complete.

    `kind` suy ra từ `content_type` (image/* là ảnh, audio/* là âm thanh), client không gửi.
    """
    return await service.create_upload(db, invitation, data, storage)


@router.post("/media/{media_id}/complete", response_model=MediaResponse)
async def complete_upload(
    media_id: uuid.UUID,
    data: CompleteUploadRequest,
    invitation: OwnedInvitation,
    db: DbSession,
    storage: StorageDep,
    background: BackgroundTasks,
) -> MediaResponse:
    media = await service.complete_upload(db, invitation, media_id, data, storage)
    _revalidate_if_published(background, invitation)
    return service.to_media_response(media, storage)


@router.get("/media", response_model=list[MediaResponse])
async def list_media(
    invitation: OwnedInvitation,
    db: DbSession,
    storage: StorageDep,
    album_id: uuid.UUID | None = None,
) -> list[MediaResponse]:
    items = await service.list_media(db, invitation, album_id)
    return [service.to_media_response(m, storage) for m in items]


# Khai báo trước "/media/{media_id}" để "order" không bị hiểu là media_id
@router.put("/media/order", response_model=list[MediaResponse])
async def reorder_media(
    data: ReorderRequest,
    invitation: OwnedInvitation,
    db: DbSession,
    storage: StorageDep,
    background: BackgroundTasks,
) -> list[MediaResponse]:
    items = await service.reorder_media(db, invitation, data.media_ids)
    _revalidate_if_published(background, invitation)
    return [service.to_media_response(m, storage) for m in items]


@router.patch("/media/{media_id}", response_model=MediaResponse)
async def update_media(
    media_id: uuid.UUID,
    data: MediaUpdate,
    invitation: OwnedInvitation,
    db: DbSession,
    storage: StorageDep,
    background: BackgroundTasks,
) -> MediaResponse:
    media = await service.update_media(db, invitation, media_id, data)
    _revalidate_if_published(background, invitation)
    return service.to_media_response(media, storage)


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: uuid.UUID,
    invitation: OwnedInvitation,
    db: DbSession,
    storage: StorageDep,
    background: BackgroundTasks,
    response: Response,
) -> None:
    """Xoá file; cột `*_media_id` và `love_story[].media_id` trỏ tới file về null.

    Không cần If-Match. Response 204 có header ETag là revision của thiệp sau khi xoá (tăng 1 nếu
    thiệp đang dùng file), để lần PATCH tiếp theo không bị 409.
    """
    invitation, key = await service.delete_media(db, invitation, media_id)
    response.headers["ETag"] = etag(invitation.revision)
    background.add_task(storage.delete, key)
    _revalidate_if_published(background, invitation)


# ---------- Album ----------


@router.get("/albums", response_model=list[AlbumResponse])
async def list_albums(invitation: OwnedInvitation, db: DbSession) -> list[AlbumResponse]:
    return await service.list_albums(db, invitation)


@router.post("/albums", response_model=AlbumResponse, status_code=status.HTTP_201_CREATED)
async def create_album(
    data: AlbumCreate, invitation: OwnedInvitation, db: DbSession, background: BackgroundTasks
) -> AlbumResponse:
    album = await service.create_album(db, invitation, data)
    _revalidate_if_published(background, invitation)
    return album


@router.patch("/albums/{album_id}", response_model=AlbumResponse)
async def update_album(
    album_id: uuid.UUID,
    data: AlbumUpdate,
    invitation: OwnedInvitation,
    db: DbSession,
    background: BackgroundTasks,
) -> AlbumResponse:
    album = await service.update_album(db, invitation, album_id, data)
    _revalidate_if_published(background, invitation)
    return album


@router.delete("/albums/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_album(
    album_id: uuid.UUID, invitation: OwnedInvitation, db: DbSession, background: BackgroundTasks
) -> None:
    await service.delete_album(db, invitation, album_id)
    _revalidate_if_published(background, invitation)
