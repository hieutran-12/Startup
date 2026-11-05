import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import bad_request, conflict, not_found
from app.core.storage import Storage
from app.modules.auth.models import User
from app.modules.invitations.models import Invitation, InvitationStatus
from app.modules.invitations.schemas import (
    InvitationContent,
    InvitationCreate,
    InvitationUpdate,
    PublicAlbum,
    PublicInvitationOut,
    PublicMedia,
    SlugAvailability,
)
from app.modules.invitations.slugs import slug_error, slugify, with_random_suffix
from app.modules.media.models import Album, Media, MediaStatus
from app.modules.templates import service as template_service


async def list_for_owner(db: AsyncSession, owner: User) -> Sequence[Invitation]:
    stmt = (
        select(Invitation)
        .where(Invitation.owner_id == owner.id)
        .order_by(Invitation.created_at.desc())
    )
    return (await db.scalars(stmt)).all()


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
    return person.short_name or person.full_name


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
        return f"{groom} & {bride}"[:120]
    return "Thiệp cưới của tôi"


async def create(db: AsyncSession, owner: User, data: InvitationCreate) -> Invitation:
    count = await db.scalar(
        select(func.count()).select_from(Invitation).where(Invitation.owner_id == owner.id)
    )
    if (count or 0) >= settings.max_invitations_per_user:
        raise bad_request(
            "invitation_limit",
            f"Mỗi tài khoản tạo tối đa {settings.max_invitations_per_user} thiệp",
        )

    template = await template_service.get_usable_by_key(db, data.template_key)

    if data.slug is not None:
        if not await is_slug_available(db, data.slug):
            raise conflict("slug_taken", "Đường dẫn đã có người dùng")
        slug = data.slug
    else:
        slug = await _generate_slug(db, data.content)

    invitation = Invitation(
        owner_id=owner.id,
        template=template,
        slug=slug,
        title=data.title or _default_title(data.content),
        content=data.content.model_dump(mode="json"),
    )
    db.add(invitation)
    try:
        await db.commit()
    except IntegrityError as exc:  # slug vừa bị người khác lấy
        await db.rollback()
        raise conflict("slug_taken", "Đường dẫn đã có người dùng") from exc
    return invitation


async def update(
    db: AsyncSession, owner: User, invitation_id: uuid.UUID, data: InvitationUpdate
) -> tuple[Invitation, list[str]]:
    """Trả về (thiệp, danh sách slug cần revalidate ở Next.js)."""
    invitation = await get_owned(db, owner, invitation_id, for_update=True)
    fields = data.model_fields_set
    old_slug = invitation.slug

    new_key = data.template_key if "template_key" in fields else None
    if new_key is not None and new_key != invitation.template.key:
        invitation.template = await template_service.get_usable_by_key(db, new_key)

    if "title" in fields and data.title is not None:
        invitation.title = data.title

    if "slug" in fields and data.slug is not None and data.slug != invitation.slug:
        if not await is_slug_available(db, data.slug, exclude_id=invitation.id):
            raise conflict("slug_taken", "Đường dẫn đã có người dùng")
        invitation.slug = data.slug

    if "content" in fields and data.content is not None:
        invitation.content = data.content.model_dump(mode="json")

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("slug_taken", "Đường dẫn đã có người dùng") from exc

    to_revalidate: list[str] = []
    if invitation.is_published:
        to_revalidate = list({old_slug, invitation.slug})
    return invitation, to_revalidate


async def publish(db: AsyncSession, owner: User, invitation_id: uuid.UUID) -> Invitation:
    invitation = await get_owned(db, owner, invitation_id, for_update=True)
    content = InvitationContent.model_validate(invitation.content)
    if not (_display_name(content, "groom") and _display_name(content, "bride")):
        raise bad_request("missing_couple_names", "Cần nhập tên cô dâu và chú rể trước khi đăng")
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
