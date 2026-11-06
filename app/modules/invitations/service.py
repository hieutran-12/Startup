import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ErrorDetail,
    bad_request,
    conflict,
    error_details,
    not_found,
    validation_error,
)
from app.core.merge_patch import merge_patch
from app.core.revision import check_revision
from app.core.storage import Storage
from app.modules.auth.models import User
from app.modules.events.models import Event, display_order
from app.modules.invitations.models import (
    MEDIA_REFERENCE_COLUMNS,
    Invitation,
    InvitationStatus,
)
from app.modules.invitations.schemas import (
    CONTENT_SCHEMA_VERSION,
    InvitationContent,
    InvitationCreate,
    InvitationResponse,
    InvitationUpdate,
    PublicAlbum,
    PublicInvitationOut,
    PublicMedia,
    SlugAvailability,
    appearance_options,
)
from app.modules.invitations.slugs import slug_error, slugify, with_random_suffix
from app.modules.media.models import Album, Media, MediaKind, MediaStatus
from app.modules.templates import service as template_service
from app.modules.templates.models import Template
from app.modules.templates.schemas import SectionKey, TemplateManifest

# Loại file mỗi cột *_media_id nhận (spec 04 › Tham chiếu media)
MEDIA_COLUMN_KINDS = {
    "cover_media_id": MediaKind.IMAGE,
    "groom_photo_media_id": MediaKind.IMAGE,
    "bride_photo_media_id": MediaKind.IMAGE,
    "music_media_id": MediaKind.AUDIO,
}

MediaReference = tuple[str, uuid.UUID, MediaKind]
"""(đường dẫn trường để báo lỗi, id file, loại file cần có)."""


# ---------- Đọc ----------


async def _primary_event_dates(
    db: AsyncSession, invitation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, date | None]:
    """Ngày chính của thiệp = MIN(events.event_date) (spec 03 › invitations), tính khi trả về."""
    if not invitation_ids:
        return {}
    rows = await db.execute(
        select(Event.invitation_id, func.min(Event.event_date))
        .where(Event.invitation_id.in_(invitation_ids))
        .group_by(Event.invitation_id)
    )
    return dict(rows.tuples().all())


def _to_response(invitation: Invitation, primary_event_date: date | None) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        slug=invitation.slug,
        title=invitation.title,
        status=invitation.status,
        template_key=invitation.template_key,
        content_schema_version=invitation.content_schema_version,
        revision=invitation.revision,
        content=InvitationContent.model_validate(invitation.content),
        cover_media_id=invitation.cover_media_id,
        groom_photo_media_id=invitation.groom_photo_media_id,
        bride_photo_media_id=invitation.bride_photo_media_id,
        music_media_id=invitation.music_media_id,
        primary_event_date=primary_event_date,
        published_at=invitation.published_at,
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
    )


async def to_response(db: AsyncSession, invitation: Invitation) -> InvitationResponse:
    dates = await _primary_event_dates(db, [invitation.id])
    return _to_response(invitation, dates.get(invitation.id))


async def list_for_owner(db: AsyncSession, owner: User) -> list[InvitationResponse]:
    stmt = (
        select(Invitation)
        .where(Invitation.owner_id == owner.id)
        .order_by(Invitation.created_at.desc())
    )
    invitations = (await db.scalars(stmt)).all()
    dates = await _primary_event_dates(db, [i.id for i in invitations])
    return [_to_response(i, dates.get(i.id)) for i in invitations]


async def get_owned(
    db: AsyncSession, owner: User, invitation_id: uuid.UUID, *, for_update: bool = False
) -> Invitation:
    stmt = select(Invitation).where(Invitation.id == invitation_id, Invitation.owner_id == owner.id)
    if for_update:
        stmt = stmt.with_for_update(of=Invitation)
    invitation = await db.scalar(stmt)
    if invitation is None:
        # Trả 404 cả khi thiệp thuộc người khác, để không lộ thiệp đó có tồn tại
        raise not_found("invitation_not_found", "Không tìm thấy thiệp")
    return invitation


# ---------- Slug ----------


async def is_slug_available(
    db: AsyncSession, slug: str, exclude_id: uuid.UUID | None = None
) -> bool:
    stmt = select(Invitation.id).where(Invitation.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(Invitation.id != exclude_id)
    return await db.scalar(stmt) is None


async def check_slug(db: AsyncSession, raw_slug: str) -> SlugAvailability:
    slug = raw_slug.strip().lower()
    if reason := slug_error(slug):
        return SlugAvailability(slug=slug, available=False, reason=reason)
    if not await is_slug_available(db, slug):
        return SlugAvailability(slug=slug, available=False, reason="Đường dẫn đã có người dùng")
    return SlugAvailability(slug=slug, available=True)


def _display_name(content: InvitationContent, side: str) -> str | None:
    person = getattr(content.couple, side)
    return person.display_name or person.full_name


async def _generate_slug(db: AsyncSession, content: InvitationContent) -> str:
    names = [n for n in (_display_name(content, "groom"), _display_name(content, "bride")) if n]
    base = slugify("-".join(names)) or "thiep-cuoi"
    if slug_error(base) is None and await is_slug_available(db, base):
        return base
    for _ in range(5):
        candidate = with_random_suffix(base)
        if slug_error(candidate) is None and await is_slug_available(db, candidate):
            return candidate
    return with_random_suffix("thiep") + "-" + uuid.uuid4().hex[:6]


def _default_title(content: InvitationContent) -> str:
    groom, bride = _display_name(content, "groom"), _display_name(content, "bride")
    if groom and bride:
        return f"{groom} & {bride}"[:120].rstrip()
    return "Thiệp cưới của tôi"


def _is_slug_conflict(exc: IntegrityError) -> bool:
    """Slug vừa bị request khác lấy giữa lúc kiểm tra và lúc commit."""
    return "uq_invitations_slug" in str(exc.orig)


# ---------- Content ----------


def _manifest(template: Template) -> TemplateManifest:
    return TemplateManifest.model_validate(template.manifest)


def default_content(manifest: TemplateManifest) -> dict[str, Any]:
    """Content v1 đầy đủ của thiệp mới (spec 04 › Tạo thiệp)."""
    sections = [section.value for section in manifest.default_sections]
    content = InvitationContent.model_validate({"appearance": {"sections": sections}})
    return content.model_dump(mode="json")


def adjust_appearance(appearance: Mapping[str, Any], manifest: TemplateManifest) -> dict[str, Any]:
    """Đưa appearance đã lưu về hợp lệ với template mới (spec 04 › Đổi template), không báo lỗi.

    Key palette/font/nền không có trong manifest mới thì về null. Section giữ những section
    template mới hỗ trợ, đúng thứ tự cũ; không còn section nào thì lấy default_sections.
    """
    result = dict(appearance)
    for field, keys in appearance_options(manifest).items():
        if result.get(field) not in keys:
            result[field] = None
    sections = [s for s in appearance.get("sections", []) if s in manifest.sections]
    result["sections"] = sections or [s.value for s in manifest.default_sections]
    return result


def _parse_content(
    data: Mapping[str, Any], manifest: TemplateManifest
) -> tuple[InvitationContent | None, list[ErrorDetail]]:
    """Kiểm tra toàn bộ content theo schema v1 và manifest. Lỗi có tiền tố `content.`."""
    try:
        content = InvitationContent.model_validate(data, context={"manifest": manifest})
    except ValidationError as exc:
        errors = [{**error, "loc": ("content", *error["loc"])} for error in exc.errors()]
        return None, error_details(errors)
    return content, []


def _love_story_references(content: InvitationContent) -> list[MediaReference]:
    return [
        (f"content.love_story[{index}].media_id", item.media_id, MediaKind.IMAGE)
        for index, item in enumerate(content.love_story)
        if item.media_id is not None
    ]


async def _media_reference_errors(
    db: AsyncSession, invitation_id: uuid.UUID, references: Sequence[MediaReference]
) -> list[ErrorDetail]:
    """File phải thuộc chính thiệp, đúng loại và đã ready (spec 04 › Tham chiếu media)."""
    if not references:
        return []
    rows = await db.execute(
        select(Media.id, Media.kind, Media.status).where(
            Media.invitation_id == invitation_id,
            Media.id.in_({media_id for _, media_id, _ in references}),
        )
    )
    found = {row.id: row for row in rows}
    errors: list[ErrorDetail] = []
    for field, media_id, kind in references:
        media = found.get(media_id)
        if media is None:
            message = "Không có file này trong thiệp"
        elif media.kind != kind:
            message = "Cần một file ảnh" if kind == MediaKind.IMAGE else "Cần một file âm thanh"
        elif media.status != MediaStatus.READY:
            message = "File chưa upload xong"
        else:
            continue
        errors.append({"field": field, "code": "invalid_reference", "message": message})
    return errors


# ---------- Điều kiện publish (spec 04 › Publish) ----------

_REQUIRED_NAMES = {
    "groom": "Cần nhập họ tên chú rể",
    "bride": "Cần nhập họ tên cô dâu",
}
_REQUIRED_EVENT_FIELDS = {
    "event_date": "Cần nhập ngày tổ chức",
    "start_time": "Cần nhập giờ bắt đầu",
    "address": "Cần nhập địa chỉ",
}
_REQUIRED_SECTIONS = {
    SectionKey.COVER: "Cần hiển thị phần ảnh bìa (cover)",
    SectionKey.EVENTS: "Cần hiển thị phần sự kiện (events)",
}


def _missing(field: str, message: str) -> ErrorDetail:
    return {"field": field, "code": "required", "message": message}


def publish_errors(content: InvitationContent, events: Sequence[Event]) -> list[ErrorDetail]:
    """Các điều kiện publish còn thiếu, theo thứ tự spec liệt kê; rỗng là đủ điều kiện.

    `events` theo thứ tự hiển thị, nên `events[i]` khớp vị trí trong GET .../events.
    """
    errors = [
        _missing(f"content.couple.{side}.full_name", message)
        for side, message in _REQUIRED_NAMES.items()
        if not getattr(content.couple, side).full_name
    ]
    if not events:
        errors.append(_missing("events", "Cần có ít nhất một sự kiện"))
    errors += [
        _missing(f"events[{index}].{field}", message)
        for index, event in enumerate(events)
        for field, message in _REQUIRED_EVENT_FIELDS.items()
        if getattr(event, field) is None
    ]
    errors += [
        _missing("content.appearance.sections", message)
        for section, message in _REQUIRED_SECTIONS.items()
        if section not in content.appearance.sections
    ]
    return errors


async def _events_in_display_order(db: AsyncSession, invitation_id: uuid.UUID) -> list[Event]:
    stmt = select(Event).where(Event.invitation_id == invitation_id).order_by(*display_order())
    return list(await db.scalars(stmt))


async def check_still_publishable(
    db: AsyncSession, invitation: Invitation, content: InvitationContent | None = None
) -> None:
    """Thiệp đã publish phải còn đủ điều kiện publish sau mỗi lần sửa.

    Gọi ngay trước commit, khi thiệp đã bị khóa (`FOR UPDATE`) và thay đổi sự kiện đã được flush.
    `content`: content mới (PATCH thiệp); không truyền thì dùng content đã lưu. Không đạt thì
    rollback mọi thay đổi chưa commit rồi trả 400 `breaks_published_invitation`.
    """
    if not invitation.is_published:
        return
    if content is None:
        content = InvitationContent.model_validate(invitation.content)
    errors = publish_errors(content, await _events_in_display_order(db, invitation.id))
    if errors:
        await db.rollback()
        raise bad_request(
            "breaks_published_invitation",
            "Thiệp đang đăng phải giữ đủ thông tin bắt buộc",
            details=errors,
        )


# ---------- Ghi ----------


async def create(db: AsyncSession, owner: User, data: InvitationCreate) -> Invitation:
    # Khóa dòng users của chủ thiệp trước khi đếm, để hai request đồng thời không vượt giới hạn.
    # Khóa giữ tới hết transaction (commit, hoặc rollback khi đóng session lúc có lỗi).
    await db.execute(select(User.id).where(User.id == owner.id).with_for_update())
    count = await db.scalar(
        select(func.count()).select_from(Invitation).where(Invitation.owner_id == owner.id)
    )
    if (count or 0) >= settings.max_invitations_per_user:
        raise bad_request(
            "invitation_limit",
            f"Mỗi tài khoản tạo tối đa {settings.max_invitations_per_user} thiệp",
        )

    template = await template_service.get_usable_by_key(db, data.template_key)
    manifest = _manifest(template)

    content_data = default_content(manifest)
    if data.content is not None:
        content_data = merge_patch(content_data, data.content)
    content, errors = _parse_content(content_data, manifest)
    invitation_id = uuid.uuid4()
    if content is not None:
        # Thiệp mới chưa có file nào, nên mọi media_id trong love_story đều bị từ chối
        errors += await _media_reference_errors(db, invitation_id, _love_story_references(content))
    if errors:
        raise validation_error(errors)
    assert content is not None

    if data.slug is not None:
        if not await is_slug_available(db, data.slug):
            raise conflict("slug_taken", "Đường dẫn đã có người dùng")
        slug = data.slug
    else:
        slug = await _generate_slug(db, content)

    invitation = Invitation(
        id=invitation_id,
        owner_id=owner.id,
        template=template,
        slug=slug,
        title=data.title or _default_title(content),
        content=content.model_dump(mode="json"),
        content_schema_version=CONTENT_SCHEMA_VERSION,
        revision=1,
    )
    db.add(invitation)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _is_slug_conflict(exc):
            raise conflict("slug_taken", "Đường dẫn đã có người dùng") from exc
        raise
    return invitation


async def update(
    db: AsyncSession,
    owner: User,
    invitation_id: uuid.UUID,
    data: InvitationUpdate,
    if_match: str,
) -> tuple[Invitation, list[str]]:
    """PATCH theo JSON Merge Patch (spec 04 › Sửa thiệp, Đổi template, Tham chiếu media).

    Trả về (thiệp, các slug cần revalidate ở Next.js). Không có gì thay đổi thì không ghi,
    revision giữ nguyên.
    """
    invitation = await get_owned(db, owner, invitation_id, for_update=True)
    check_revision(if_match, invitation.revision)
    fields = data.model_fields_set

    template = invitation.template
    template_changed = "template_key" in fields and data.template_key != template.key
    if template_changed:
        template = await template_service.get_usable_by_key(db, data.template_key)
    manifest = _manifest(template)

    # Đổi template: chỉnh appearance đã lưu theo manifest mới trước, rồi mới gộp patch; giá trị
    # client gửi tường minh vẫn được kiểm tra chặt theo manifest mới.
    new_content = invitation.content
    parsed_content: InvitationContent | None = None  # None: content giữ nguyên
    errors: list[ErrorDetail] = []
    if template_changed or "content" in fields:
        content_data = dict(invitation.content)
        if template_changed:
            content_data["appearance"] = adjust_appearance(content_data["appearance"], manifest)
        if "content" in fields:
            content_data = merge_patch(content_data, data.content)
        content, errors = _parse_content(content_data, manifest)
        if content is not None:
            parsed_content = content
            new_content = content.model_dump(mode="json")
            # Chỉ kiểm tra tham chiếu có trong request: gửi love_story thì kiểm tra cả danh sách
            if "content" in fields and "love_story" in data.content:
                errors += await _media_reference_errors(
                    db, invitation.id, _love_story_references(content)
                )

    column_references = [
        (column, media_id, MEDIA_COLUMN_KINDS[column])
        for column in MEDIA_REFERENCE_COLUMNS
        if column in fields and (media_id := getattr(data, column)) is not None
    ]
    errors += await _media_reference_errors(db, invitation.id, column_references)
    if errors:
        raise validation_error(errors)

    slug_changed = "slug" in fields and data.slug != invitation.slug
    if slug_changed and not await is_slug_available(db, data.slug, exclude_id=invitation.id):
        raise conflict("slug_taken", "Đường dẫn đã có người dùng")

    old_slug = invitation.slug
    changed = False
    if "title" in fields and data.title != invitation.title:
        invitation.title = data.title
        changed = True
    if slug_changed:
        invitation.slug = data.slug
        changed = True
    if template_changed:
        invitation.template = template
        changed = True
    if new_content != invitation.content:
        invitation.content = new_content
        changed = True
    for column in MEDIA_REFERENCE_COLUMNS:
        if column in fields and getattr(data, column) != getattr(invitation, column):
            setattr(invitation, column, getattr(data, column))
            changed = True
    if not changed:
        return invitation, []

    await check_still_publishable(db, invitation, parsed_content)
    invitation.revision += 1
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _is_slug_conflict(exc):
            raise conflict("slug_taken", "Đường dẫn đã có người dùng") from exc
        raise

    to_revalidate: list[str] = []
    if invitation.is_published:
        to_revalidate = list({old_slug, invitation.slug})
    return invitation, to_revalidate


async def publish(db: AsyncSession, owner: User, invitation_id: uuid.UUID) -> Invitation:
    """Đủ điều kiện publish thì đăng, thiếu thì 400 `not_ready_to_publish` (spec 04 › Publish).

    Khóa dòng thiệp trước khi đọc sự kiện: thao tác ghi sự kiện cũng khóa dòng này, nên không xoá
    được sự kiện giữa lúc kiểm tra và lúc đăng. Không cần If-Match, không tăng revision; publish
    lại thiệp đã đăng thì kiểm tra lại và đặt lại `published_at` (giữ như khung).
    """
    invitation = await get_owned(db, owner, invitation_id, for_update=True)
    content = InvitationContent.model_validate(invitation.content)
    errors = publish_errors(content, await _events_in_display_order(db, invitation.id))
    if errors:
        raise bad_request("not_ready_to_publish", "Thiệp chưa đủ thông tin để đăng", details=errors)
    invitation.status = InvitationStatus.PUBLISHED.value
    invitation.published_at = datetime.now(UTC)
    await db.commit()
    return invitation


async def unpublish(db: AsyncSession, owner: User, invitation_id: uuid.UUID) -> Invitation:
    invitation = await get_owned(db, owner, invitation_id, for_update=True)
    invitation.status = InvitationStatus.DRAFT.value
    invitation.published_at = None
    await db.commit()
    return invitation


async def delete(
    db: AsyncSession, owner: User, invitation_id: uuid.UUID
) -> tuple[str, bool, list[str]]:
    """Xoá thiệp (album và media bị xoá theo nhờ ON DELETE CASCADE).

    Trả về (slug, đã publish hay chưa, các storage_key cần xoá khỏi storage).
    """
    invitation = await get_owned(db, owner, invitation_id, for_update=True)
    keys = list(
        await db.scalars(select(Media.storage_key).where(Media.invitation_id == invitation.id))
    )
    slug, was_published = invitation.slug, invitation.is_published
    await db.delete(invitation)
    await db.commit()
    return slug, was_published, keys


# ---------- Trang public (dạng khung, đổi ở Bước 10) ----------


async def get_public(db: AsyncSession, slug: str, storage: Storage) -> PublicInvitationOut:
    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.slug == slug.lower(),
            Invitation.status == InvitationStatus.PUBLISHED.value,
        )
    )
    if invitation is None:
        raise not_found("invitation_not_found", "Không tìm thấy thiệp")

    albums = (
        await db.scalars(
            select(Album)
            .where(Album.invitation_id == invitation.id)
            .order_by(Album.position, Album.created_at)
        )
    ).all()
    media = (
        await db.scalars(
            select(Media)
            .where(Media.invitation_id == invitation.id, Media.status == MediaStatus.READY.value)
            .order_by(Media.position, Media.created_at)
        )
    ).all()

    return PublicInvitationOut(
        slug=invitation.slug,
        template_key=invitation.template_key,
        content=invitation.content,
        published_at=invitation.published_at,
        updated_at=invitation.updated_at,
        albums=[PublicAlbum(id=a.id, title=a.title, position=a.position) for a in albums],
        media=[
            PublicMedia(
                id=m.id,
                album_id=m.album_id,
                url=storage.public_url(m.storage_key),
                width=m.width,
                height=m.height,
            )
            for m in media
        ],
    )
