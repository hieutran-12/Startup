import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import bad_request, not_found
from app.core.storage import Storage
from app.modules.invitations.models import Invitation
from app.modules.media.models import Album, Media, MediaStatus
from app.modules.media.schemas import (
    AlbumCreate,
    AlbumOut,
    AlbumUpdate,
    CompleteUploadRequest,
    MediaOut,
    MediaUpdate,
    UploadUrlRequest,
    UploadUrlResponse,
)

EXTENSION_BY_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}


def to_media_out(media: Media, storage: Storage) -> MediaOut:
    return MediaOut(
        id=media.id,
        album_id=media.album_id,
        url=storage.public_url(media.storage_key),
        original_filename=media.original_filename,
        mime_type=media.mime_type,
        size_bytes=media.size_bytes,
        width=media.width,
        height=media.height,
        status=media.status,
        position=media.position,
        created_at=media.created_at,
    )


async def _get_album(db: AsyncSession, invitation: Invitation, album_id: uuid.UUID) -> Album:
    album = await db.scalar(
        select(Album).where(Album.id == album_id, Album.invitation_id == invitation.id)
    )
    if album is None:
        raise not_found("album_not_found", "Không tìm thấy album")
    return album


async def _get_media(db: AsyncSession, invitation: Invitation, media_id: uuid.UUID) -> Media:
    media = await db.scalar(
        select(Media).where(Media.id == media_id, Media.invitation_id == invitation.id)
    )
    if media is None:
        raise not_found("media_not_found", "Không tìm thấy ảnh")
    return media


# ---------- Upload ----------


async def create_upload(
    db: AsyncSession, invitation: Invitation, data: UploadUrlRequest, storage: Storage
) -> UploadUrlResponse:
    content_type = data.content_type.lower()
    extension = EXTENSION_BY_TYPE.get(content_type)
    if extension is None or content_type not in settings.allowed_image_types:
        raise bad_request("unsupported_file_type", "Chỉ hỗ trợ ảnh JPG, PNG, WEBP, AVIF")
    if data.size_bytes > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise bad_request("file_too_large", f"Ảnh tối đa {limit_mb}MB")
    if data.album_id is not None:
        await _get_album(db, invitation, data.album_id)

    count, max_position = (
        await db.execute(
            select(func.count(Media.id), func.max(Media.position)).where(
                Media.invitation_id == invitation.id
            )
        )
    ).one()
    if count >= settings.max_media_per_invitation:
        raise bad_request(
            "media_limit", f"Mỗi thiệp tối đa {settings.max_media_per_invitation} ảnh"
        )

    media_id = uuid.uuid4()
    media = Media(
        id=media_id,
        invitation_id=invitation.id,
        album_id=data.album_id,
        storage_key=f"invitations/{invitation.id}/{media_id}.{extension}",
        original_filename=data.filename,
        mime_type=content_type,
        size_bytes=data.size_bytes,
        status=MediaStatus.PENDING.value,
        position=(max_position + 1) if max_position is not None else 0,
    )
    db.add(media)
    await db.commit()

    return UploadUrlResponse(
        media_id=media.id,
        upload_url=storage.presign_put(media.storage_key, content_type),
        headers={"Content-Type": content_type},
        expires_in=settings.presigned_url_ttl_seconds,
    )


async def complete_upload(
    db: AsyncSession,
    invitation: Invitation,
    media_id: uuid.UUID,
    data: CompleteUploadRequest,
    storage: Storage,
) -> Media:
    media = await _get_media(db, invitation, media_id)
    if media.status == MediaStatus.READY.value:
        return media  # gọi lại nhiều lần không sao

    info = await storage.head(media.storage_key)
    if info is None:
        raise bad_request("upload_not_found", "Chưa thấy file trên storage, hãy upload lại")

    # Link presigned không giới hạn được dung lượng, nên kiểm tra lại file thật sau khi upload
    wrong_type = info.content_type is not None and info.content_type.lower() != media.mime_type
    if info.size_bytes > settings.max_upload_bytes or wrong_type:
        await storage.delete(media.storage_key)
        await db.delete(media)
        await db.commit()
        raise bad_request("invalid_upload", "File không hợp lệ (sai định dạng hoặc quá dung lượng)")

    media.size_bytes = info.size_bytes
    media.width = data.width
    media.height = data.height
    media.status = MediaStatus.READY.value
    await db.commit()
    return media


# ---------- Quản lý ảnh ----------


async def list_media(
    db: AsyncSession, invitation: Invitation, album_id: uuid.UUID | None = None
) -> Sequence[Media]:
    stmt = select(Media).where(
        Media.invitation_id == invitation.id, Media.status == MediaStatus.READY.value
    )
    if album_id is not None:
        stmt = stmt.where(Media.album_id == album_id)
    stmt = stmt.order_by(Media.position, Media.created_at)
    return (await db.scalars(stmt)).all()


async def update_media(
    db: AsyncSession, invitation: Invitation, media_id: uuid.UUID, data: MediaUpdate
) -> Media:
    media = await _get_media(db, invitation, media_id)
    if "album_id" in data.model_fields_set:
        if data.album_id is not None:
            await _get_album(db, invitation, data.album_id)
        media.album_id = data.album_id
    await db.commit()
    return media


async def reorder_media(
    db: AsyncSession, invitation: Invitation, media_ids: list[uuid.UUID]
) -> Sequence[Media]:
    if len(set(media_ids)) != len(media_ids):
        raise bad_request("duplicate_media_ids", "Danh sách ảnh bị trùng")
    rows = (
        await db.scalars(
            select(Media).where(Media.invitation_id == invitation.id, Media.id.in_(media_ids))
        )
    ).all()
    if len(rows) != len(media_ids):
        raise bad_request("invalid_media_ids", "Có ảnh không thuộc thiệp này")
    by_id = {m.id: m for m in rows}
    for position, media_id in enumerate(media_ids):
        by_id[media_id].position = position
    await db.commit()
    return [by_id[i] for i in media_ids]


async def delete_media(db: AsyncSession, invitation: Invitation, media_id: uuid.UUID) -> str:
    """Xoá bản ghi, trả về storage_key để xoá file trong background."""
    media = await _get_media(db, invitation, media_id)
    key = media.storage_key
    await db.delete(media)
    await db.commit()
    return key


# ---------- Album ----------


async def _media_counts(db: AsyncSession, invitation: Invitation) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Media.album_id, func.count(Media.id))
        .where(
            Media.invitation_id == invitation.id,
            Media.status == MediaStatus.READY.value,
            Media.album_id.is_not(None),
        )
        .group_by(Media.album_id)
    )
    return {album_id: count for album_id, count in rows.all()}


def _to_album_out(album: Album, media_count: int = 0) -> AlbumOut:
    return AlbumOut(
        id=album.id,
        title=album.title,
        position=album.position,
        media_count=media_count,
        created_at=album.created_at,
    )


async def list_albums(db: AsyncSession, invitation: Invitation) -> list[AlbumOut]:
    albums = (
        await db.scalars(
            select(Album)
            .where(Album.invitation_id == invitation.id)
            .order_by(Album.position, Album.created_at)
        )
    ).all()
    counts = await _media_counts(db, invitation)
    return [_to_album_out(a, counts.get(a.id, 0)) for a in albums]


async def create_album(db: AsyncSession, invitation: Invitation, data: AlbumCreate) -> AlbumOut:
    max_position = await db.scalar(
        select(func.max(Album.position)).where(Album.invitation_id == invitation.id)
    )
    album = Album(
        invitation_id=invitation.id,
        title=data.title.strip(),
        position=(max_position + 1) if max_position is not None else 0,
    )
    db.add(album)
    await db.commit()
    return _to_album_out(album)


async def update_album(
    db: AsyncSession, invitation: Invitation, album_id: uuid.UUID, data: AlbumUpdate
) -> AlbumOut:
    album = await _get_album(db, invitation, album_id)
    if data.title is not None:
        album.title = data.title.strip()
    if data.position is not None:
        album.position = data.position
    await db.commit()
    counts = await _media_counts(db, invitation)
    return _to_album_out(album, counts.get(album.id, 0))


async def delete_album(db: AsyncSession, invitation: Invitation, album_id: uuid.UUID) -> None:
    album = await _get_album(db, invitation, album_id)
    await db.delete(album)  # ảnh trong album được giữ lại (album_id -> NULL)
    await db.commit()
