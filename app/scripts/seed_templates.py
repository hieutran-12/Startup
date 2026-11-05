"""Seed danh sách mẫu thiệp. Chạy lại nhiều lần vẫn an toàn (upsert theo `key`).

uv run python -m app.scripts.seed_templates
"""

import asyncio
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.core.db import SessionLocal, engine
from app.modules.templates.models import Template

ALL_SECTIONS = ["couple", "events", "greeting", "love_story", "gallery", "bank_accounts", "music"]

TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "classic-01",
        "name": "Cổ điển",
        "description": "Bố cục truyền thống, chữ serif, tông kem và vàng đồng.",
        "category": "classic",
        "is_premium": False,
        "position": 10,
        "manifest": {
            "sections": ALL_SECTIONS,
            "max_gallery_images": 30,
            "theme": {"primary_color": ["#B08D57", "#8C6A43", "#A3485A"]},
        },
    },
    {
        "key": "minimal-01",
        "name": "Tối giản",
        "description": "Nhiều khoảng trắng, một ảnh bìa lớn, phù hợp ảnh cưới đẹp.",
        "category": "minimal",
        "is_premium": False,
        "position": 20,
        "manifest": {
            "sections": ["couple", "events", "greeting", "gallery", "bank_accounts"],
            "max_gallery_images": 12,
            "theme": {"primary_color": ["#1F1F1F", "#5B6C5D", "#7A6F9B"]},
        },
    },
    {
        "key": "floral-01",
        "name": "Hoa cỏ",
        "description": "Hoạ tiết hoa vẽ tay, hợp đám cưới ngoài trời.",
        "category": "floral",
        "is_premium": False,
        "position": 30,
        "manifest": {
            "sections": ALL_SECTIONS,
            "max_gallery_images": 24,
            "theme": {"primary_color": ["#C7798A", "#6E8B5B", "#D19A4F"]},
        },
    },
    {
        "key": "vintage-01",
        "name": "Hoài cổ",
        "description": "Phong cách thư tay xưa, có hiệu ứng mở phong bì.",
        "category": "vintage",
        "is_premium": True,
        "position": 40,
        "manifest": {"sections": ALL_SECTIONS, "max_gallery_images": 40},
    },
]


async def seed() -> None:
    async with SessionLocal() as db:
        for data in TEMPLATES:
            stmt = insert(Template).values(**data)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Template.key],
                set_={
                    **{k: stmt.excluded[k] for k in data if k != "key"},
                    "updated_at": func.now(),
                },
            )
            await db.execute(stmt)
        await db.commit()
    await engine.dispose()
    print(f"Đã seed {len(TEMPLATES)} mẫu thiệp")


if __name__ == "__main__":
    asyncio.run(seed())
