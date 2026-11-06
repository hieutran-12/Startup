"""File của thiệp (ảnh, âm thanh) và album (spec 03 › media, 04 › Tham chiếu media).

Xin link upload và xoá file đều khóa dòng thiệp (`SELECT … FOR UPDATE`): xin link để đếm giới hạn
theo loại mà request đồng thời không vượt; xoá file để gỡ tham chiếu trong love_story cùng
transaction, không lẫn với PATCH thiệp đang gắn chính file đó.
Thứ tự kiểm tra: docs/modules/media.md.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import bad_request, not_found, validation_error
from app.core.storage import Storage
from app.modules.invitations import service as invitation_service
from app.modules.invitations.models import MEDIA_REFERENCE_COLUMNS, Invitation
from app.modules.media.models import Album, Media, MediaKind, MediaStatus
from app.modules.media.schemas import (
    AUDIO_NOT_IN_ALBUM,
    AlbumCreate,
    AlbumResponse,
    AlbumUpdate,
    CompleteUploadRequest,
    MediaResponse,
    MediaUpdate,
    UploadUrlRequest,
    UploadUrlResponse,
    max_size_bytes,
)


def to_media_response(media: Media, storage: Storage) -> MediaResponse:
    return MediaResponse(
        id=media.id,
        kind=media.kind,
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


async def _lock_invitation(db: AsyncSession, invitation: Invitation) -> Invitation:
    """Khóa dòng thiệp và đọc lại giá trị mới nhất (thiệp được nạp trước đó, khi chưa khóa)."""
    locked = await db.scalar(
        select(Invitation)
        .where(Invitation.id == invitation.id)
        .with_for_update(of=Invitation)
        .execution_options(populate_existing=True)
    )
    if locked is None:  # thiệp vừa bị xoá ở request khác
        raise not_found("invitation_not_found", "Không tìm thấy thiệp")
    return locked


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
        raise not_found("media_not_found", "Không tìm thấy file")
    return media


def _count_limit(kind: MediaKind) -> tuple[int, str]:
    if kind == MediaKind.IMAGE:
        limit = settings.max_images_per_invitation
        return limit, f"Mỗi thiệp tối đa {limit} ảnh"
    limit = settings.max_audio_per_invitation
    return limit, f"Mỗi thiệp tối đa {limit} file âm thanh"


# ---------- Upload ----------


async def create_upload(
    db: AsyncSession, invitation: Invitation, data: UploadUrlRequest, storage: Storage
) -> UploadUrlResponse:
    """Loại file, dung lượng, âm thanh không vào album: đã kiểm tra ở schema (422)."""
    content_type = data.content_type
    kind = content_type.kind
    invitation = await _lock_invitation(db, invitation)
    if data.album_id is not None:
        await _get_album(db, invitation, data.album_id)

    # Đếm cả file pending để không xin được link upload vô hạn (đề xuất 1, Bước 7)
    count, max_position = (
        await db.execute(
            select(func.count(Media.id), func.max(Media.position)).where(
                Media.invitation_id == invitation.id, Media.kind == kind.value
            )
        )
    ).one()
    limit, message = _count_limit(kind)
    if count >= limit:
        raise bad_request("media_limit", message)

    # Ảnh đánh số tiếp theo trong các ảnh; âm thanh không nằm trong thư viện nên luôn ở vị trí 0
    position = 0
    if kind == MediaKind.IMAGE and max_position is not None:
        position = max_position + 1

    media_id = uuid.uuid4()
    media = Media(
        id=media_id,
        invitation_id=invitation.id,
        album_id=data.album_id,
        kind=kind.value,
        storage_key=f"invitations/{invitation.id}/{media_id}.{content_type.extension}",
        original_filename=data.filename,
        mime_type=content_type.value,  # đúng loại client gửi (spec 03 › media)
        size_bytes=data.size_bytes,
        status=MediaStatus.PENDING.value,
        position=position,
    )
    db.add(media)
    await db.commit()

    return UploadUrlResponse(
        media_id=media.id,
        upload_url=storage.presign_put(media.storage_key, content_type.value),
        headers={"Content-Type": content_type.value},
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
    if media.kind == MediaKind.AUDIO:
        errors = [
            {
                "field": field,
                "code": "invalid_format",
                "message": "File âm thanh không có kích thước ảnh",
            }
            for field in ("width", "height")
            if getattr(data, field) is not None
        ]
        if errors:
            raise validation_error(errors)
    if media.status == MediaStatus.READY.value:
        return media  # gọi lại nhiều lần không sao

    info = await storage.head(media.storage_key)
    if info is None:
        raise bad_request("upload_not_found", "Chưa thấy file trên storage, hãy upload lại")

    # Link presigned không giới hạn được dung lượng, nên kiểm tra lại file thật sau khi upload
    wrong_type = info.content_type is not None and info.content_type.lower() != media.mime_type
    if info.size_bytes > max_size_bytes(MediaKind(media.kind)) or wrong_type:
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


# ---------- Quản lý file ----------


async def list_media(
    db: AsyncSession, invitation: Invitation, album_id: uuid.UUID | None = None
) -> Sequence[Media]:
    """Mọi file ready của thiệp (ảnh và âm thanh); lọc theo album thì chỉ còn ảnh."""
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
            if media.kind == MediaKind.AUDIO:
                raise validation_error(
                    [
                        {
                            "field": "album_id",
                            "code": "invalid_reference",
                            "message": AUDIO_NOT_IN_ALBUM,
                        }
                    ]
                )
            await _get_album(db, invitation, data.album_id)
        media.album_id = data.album_id
    await db.commit()
    return media


async def reorder_media(
    db: AsyncSession, invitation: Invitation, media_ids: list[uuid.UUID]
) -> Sequence[Media]:
    """Sắp xếp thư viện ảnh: mọi id phải là ảnh của thiệp (file âm thanh không có thứ tự)."""
    if len(set(media_ids)) != len(media_ids):
        raise bad_request("duplicate_media_ids", "Danh sách ảnh bị trùng")
    rows = (
        await db.scalars(
            select(Media).where(
                Media.invitation_id == invitation.id,
                Media.kind == MediaKind.IMAGE.value,
                Media.id.in_(media_ids),
            )
        )
    ).all()
    if len(rows) != len(media_ids):
        raise bad_request("invalid_media_ids", "Có id không phải ảnh của thiệp này")
    by_id = {m.id: m for m in rows}
    for position, media_id in enumerate(media_ids):
        by_id[media_id].position = position
    await db.commit()
    return [by_id[i] for i in media_ids]


async def delete_media(
    db: AsyncSession, invitation: Invitation, media_id: uuid.UUID
) -> tuple[Invitation, str]:
    """Xoá bản ghi và gỡ tham chiếu trong cùng transaction (spec 04 › Tham chiếu media).

    Trả về (thiệp sau khi xoá, storage_key để xoá file trong background). Revision của thiệp chỉ
    tăng khi thiệp đang dùng file; không cần If-Match (spec chỉ bắt buộc cho PATCH thiệp, sự kiện).
    """
    invitation = await _lock_invitation(db, invitation)
    media = await _get_media(db, invitation, media_id)
    key = media.storage_key
    invitation_service.release_media(invitation, media.id)
    await db.delete(media)
    await db.flush()
    # ON DELETE SET NULL (<cột>) chạy trong database; ORM không biết nên đọc lại bốn cột
    await db.refresh(invitation, attribute_names=list(MEDIA_REFERENCE_COLUMNS))
    await db.commit()
    return invitation, key


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


def _to_album_response(album: Album, media_count: int = 0) -> AlbumResponse:
    return AlbumResponse(
        id=album.id,
        title=album.title,
        position=album.position,
        media_count=media_count,
        created_at=album.created_at,
    )


async def list_albums(db: AsyncSession, invitation: Invitation) -> list[AlbumResponse]:
    albums = (
        await db.scalars(
            select(Album)
            .where(Album.invitation_id == invitation.id)
            .order_by(Album.position, Album.created_at)
        )
    ).all()
    counts = await _media_counts(db, invitation)
    return [_to_album_response(a, counts.get(a.id, 0)) for a in albums]


async def create_album(
    db: AsyncSession, invitation: Invitation, data: AlbumCreate
) -> AlbumResponse:
    max_position = await db.scalar(
        select(func.max(Album.position)).where(Album.invitation_id == invitation.id)
    )
    album = Album(
        invitation_id=invitation.id,
        title=data.title,
        position=(max_position + 1) if max_position is not None else 0,
    )
    db.add(album)
    await db.commit()
    return _to_album_response(album)


async def update_album(
    db: AsyncSession, invitation: Invitation, album_id: uuid.UUID, data: AlbumUpdate
) -> AlbumResponse:
    album = await _get_album(db, invitation, album_id)
    if "title" in data.model_fields_set:
        album.title = data.title
    if "position" in data.model_fields_set:
        album.position = data.position
    await db.commit()
    counts = await _media_counts(db, invitation)
    return _to_album_response(album, counts.get(album.id, 0))


async def delete_album(db: AsyncSession, invitation: Invitation, album_id: uuid.UUID) -> None:
    album = await _get_album(db, invitation, album_id)
    await db.delete(album)  # ảnh trong album được giữ lại (album_id -> NULL)
    await db.commit()
