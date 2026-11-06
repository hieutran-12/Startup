"""Seed danh sách mẫu thiệp. Chạy lại nhiều lần vẫn an toàn (upsert theo `key`).

uv run python -m app.scripts.seed_templates

Toàn bộ danh sách được kiểm tra bằng `TemplateCreate` (gồm `TemplateManifest`) trước khi ghi:
một mẫu sai thì không ghi mẫu nào, script in danh sách lỗi và thoát với mã 1.
Key palette, font, nền là hợp đồng với component React: đổi ở đây thì đổi cả bên Next.js.
"""

import asyncio
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, engine
from app.core.errors import error_details
from app.modules.templates.models import Template
from app.modules.templates.schemas import SectionKey, TemplateCreate

ALL_SECTIONS = [section.value for section in SectionKey]


def _palette(
    key: str, name: str, primary: str, secondary: str, background: str, text: str
) -> dict[str, str]:
    return {
        "key": key,
        "name": name,
        "primary": primary,
        "secondary": secondary,
        "background": background,
        "text": text,
    }


def _manifest(
    *,
    sections: list[str],
    palettes: list[dict[str, str]],
    fonts: dict[str, str],
    backgrounds: dict[str, str],
    max_gallery_images: int,
) -> dict[str, Any]:
    """Manifest với default_sections là mọi section, mặc định là lựa chọn đầu của mỗi danh sách."""
    font_options = [{"key": key, "name": name} for key, name in fonts.items()]
    background_options = [{"key": key, "name": name} for key, name in backgrounds.items()]
    return {
        "sections": list(sections),  # chép ra: các mẫu không được dùng chung một list
        "default_sections": list(sections),
        "palettes": palettes,
        "fonts": font_options,
        "backgrounds": background_options,
        "defaults": {
            "palette_key": palettes[0]["key"],
            "font_key": font_options[0]["key"],
            "background_key": background_options[0]["key"],
        },
        "max_gallery_images": max_gallery_images,
    }


TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "classic_01",
        "name": "Cổ điển",
        "description": "Bố cục truyền thống, chữ serif, tông kem và vàng đồng.",
        "category": "classic",
        "is_premium": False,
        "position": 0,
        "manifest": _manifest(
            sections=ALL_SECTIONS,
            palettes=[
                _palette(
                    "ivory_gold", "Ngà – vàng đồng", "#B08D57", "#E8DCC4", "#FBF7EF", "#3A2E22"
                ),
                _palette("walnut", "Nâu gỗ óc chó", "#8C6A43", "#D9C7A7", "#F7F1E6", "#2F241A"),
                _palette("burgundy", "Đỏ rượu vang", "#A3485A", "#E9C9CF", "#FCF6F4", "#3B1F25"),
            ],
            fonts={
                "playfair_display": "Playfair Display",
                "cormorant_garamond": "Cormorant Garamond",
            },
            backgrounds={"plain": "Trơn", "paper": "Giấy dó"},
            max_gallery_images=30,
        ),
    },
    {
        "key": "minimal_01",
        "name": "Tối giản",
        "description": "Nhiều khoảng trắng, một ảnh bìa lớn, phù hợp ảnh cưới đẹp.",
        "category": "minimal",
        "is_premium": False,
        "position": 1,
        "manifest": _manifest(
            sections=[s for s in ALL_SECTIONS if s != SectionKey.LOVE_STORY],
            palettes=[
                _palette("charcoal", "Than chì", "#1F1F1F", "#BDBDBD", "#FFFFFF", "#1F1F1F"),
                _palette("sage", "Xanh xô thơm", "#5B6C5D", "#C9D3C6", "#F6F7F4", "#222822"),
                _palette("lavender", "Oải hương", "#7A6F9B", "#D6D1E6", "#F8F7FB", "#26223A"),
            ],
            fonts={"be_vietnam_pro": "Be Vietnam Pro", "montserrat": "Montserrat"},
            backgrounds={"plain": "Trơn", "grain": "Nhiễu hạt"},
            max_gallery_images=12,
        ),
    },
    {
        "key": "floral_01",
        "name": "Hoa cỏ",
        "description": "Hoạ tiết hoa vẽ tay, hợp đám cưới ngoài trời.",
        "category": "floral",
        "is_premium": False,
        "position": 2,
        "manifest": _manifest(
            sections=ALL_SECTIONS,
            palettes=[
                _palette("rose", "Hồng phấn", "#C7798A", "#F1D4DA", "#FFF8F8", "#3E2A2E"),
                _palette("olive_leaf", "Xanh lá ô liu", "#6E8B5B", "#D5E0CC", "#F8FAF5", "#263021"),
                _palette(
                    "marigold", "Vàng cúc vạn thọ", "#D19A4F", "#F3DFC0", "#FFFBF3", "#3A2C17"
                ),
            ],
            fonts={"lora": "Lora", "dancing_script": "Dancing Script"},
            backgrounds={"plain": "Trơn", "watercolor_flowers": "Hoa màu nước"},
            max_gallery_images=24,
        ),
    },
    {
        "key": "vintage_01",
        "name": "Hoài cổ",
        "description": "Phong cách thư tay xưa, có hiệu ứng mở phong bì.",
        "category": "vintage",
        "is_premium": True,
        "position": 3,
        "manifest": _manifest(
            sections=ALL_SECTIONS,
            palettes=[
                _palette("sepia", "Nâu sepia", "#8B5E3C", "#D8C3A5", "#F4ECDD", "#3B2A1E"),
                _palette("dusty_rose", "Hồng tro", "#A26769", "#E3CFCB", "#F7F0EC", "#3A2626"),
            ],
            fonts={"old_standard_tt": "Old Standard TT", "great_vibes": "Great Vibes"},
            backgrounds={"old_paper": "Giấy cũ", "kraft": "Giấy kraft"},
            max_gallery_images=40,
        ),
    },
]


class SeedError(Exception):
    """Danh sách seed sai. `errors`: [{index, key, field, code, message}]."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        lines = [
            f"  [{e['index']}] {e['key']} › {e['field'] or '(mẫu)'}: {e['code']} — {e['message']}"
            for e in errors
        ]
        super().__init__("Danh sách mẫu thiệp không hợp lệ, chưa ghi gì:\n" + "\n".join(lines))


def validate_templates(rows: Sequence[Mapping[str, Any]]) -> list[TemplateCreate]:
    """Kiểm tra mọi mẫu (cấu trúc, manifest, key không trùng). Sai thì raise SeedError."""
    templates: list[TemplateCreate] = []
    errors: list[dict[str, Any]] = []
    first_index: dict[str, int] = {}
    for index, row in enumerate(rows):
        key = row.get("key") if isinstance(row, Mapping) else None
        try:
            template = TemplateCreate.model_validate(row)
        except ValidationError as exc:
            errors += [{"index": index, "key": key, **d} for d in error_details(exc.errors())]
            continue
        if template.key in first_index:
            errors.append(
                {
                    "index": index,
                    "key": key,
                    "field": "key",
                    "code": "invalid_format",
                    "message": f"Bị trùng với mẫu [{first_index[template.key]}]",
                }
            )
            continue
        first_index[template.key] = index
        templates.append(template)
    if errors:
        raise SeedError(errors)
    return templates


async def seed(db: AsyncSession, rows: Sequence[Mapping[str, Any]] = TEMPLATES) -> int:
    """Upsert các mẫu theo `key` trong một transaction. Trả số mẫu đã ghi."""
    templates = validate_templates(rows)
    for template in templates:
        data = template.model_dump(mode="json")
        stmt = insert(Template).values(**data)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Template.key],
            set_={
                **{column: stmt.excluded[column] for column in data if column != "key"},
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
    await db.commit()
    return len(templates)


async def main() -> int:
    try:
        async with SessionLocal() as db:
            count = await seed(db)
    except SeedError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(f"Đã seed {count} mẫu thiệp")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
