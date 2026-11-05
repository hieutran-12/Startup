from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.modules.templates.models import Template


async def list_active(db: AsyncSession, category: str | None = None) -> Sequence[Template]:
    stmt = select(Template).where(Template.is_active.is_(True))
    if category:
        stmt = stmt.where(Template.category == category)
    stmt = stmt.order_by(Template.position, Template.name)
    return (await db.scalars(stmt)).all()


async def get_by_key(db: AsyncSession, key: str) -> Template:
    template = await db.scalar(select(Template).where(Template.key == key))
    if template is None or not template.is_active:
        raise not_found("template_not_found", "Không tìm thấy mẫu thiệp")
    return template


async def get_usable_by_key(db: AsyncSession, key: str) -> Template:
    """Mẫu thiệp mà cặp đôi được phép chọn. Chưa có thanh toán nên chặn mẫu premium."""
    template = await get_by_key(db, key)
    if template.is_premium:
        raise bad_request("template_premium", "Mẫu thiệp này thuộc gói trả phí")
    return template
