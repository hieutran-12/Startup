"""Seed danh sách mẫu thiệp. Chạy lại nhiều lần vẫn an toàn (upsert theo `key`).

uv run python -m app.scripts.seed_templates

Toàn bộ danh sách được kiểm tra bằng `TemplateCreate` (gồm `TemplateManifest`) trước khi ghi:
một mẫu sai thì không ghi mẫu nào, script in danh sách lỗi và thoát với mã 1.
Key mẫu, palette, font, nền là hợp đồng với component của web (repo SuperProject):
đổi ở đây thì đổi cả bên web.
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


# 4 mẫu theo web (repo SuperProject, my-fe-app/src/templates/): key là slug của web
# đổi "-" thành "_", position theo thứ tự trong registry.ts.
# Bảng màu, font, nền lấy đúng từ code của component.
TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "dragon_phoenix_red",
        "name": "Dragon Phoenix Red",
        "description": "Truyền thống với hoa văn rồng phượng, nền kem và viền vàng.",
        "category": "classic",
        "is_premium": False,
        "position": 0,
        "manifest": _manifest(
            sections=ALL_SECTIONS,
            palettes=[
                _palette("red_gold", "Đỏ – vàng kim", "#8B0000", "#D4AF37", "#FFF8E7", "#8B0000"),
            ],
            fonts={"georgia": "Georgia"},
            backgrounds={"plain": "Trơn"},
            max_gallery_images=200,  # web ghi "Ảnh không giới hạn": bằng giới hạn ảnh mỗi thiệp
        ),
    },
    {
        "key": "royal_blue",
        "name": "Royal Blue",
        "description": "Nền xanh navy sang trọng với khung vòm và chi tiết vàng.",
        "category": "modern",
        "is_premium": False,
        "position": 1,
        "manifest": _manifest(
            sections=ALL_SECTIONS,
            palettes=[
                _palette(
                    "navy_gold", "Xanh navy – vàng", "#E8C872", "#1B2A4A", "#0B1A33", "#F5F5F5"
                ),
            ],
            fonts={"georgia": "Georgia"},
            backgrounds={"plain": "Trơn"},
            max_gallery_images=30,
        ),
    },
    {
        "key": "cherry_blossom_pink",
        "name": "Cherry Blossom Pink",
        "description": "Lãng mạn với hoa anh đào hồng và bố cục bo tròn mềm mại.",
        "category": "floral",
        "is_premium": False,
        "position": 2,
        "manifest": _manifest(
            sections=ALL_SECTIONS,
            palettes=[
                _palette("rose_pink", "Hồng anh đào", "#880E4F", "#F48FB1", "#FDF0F4", "#880E4F"),
            ],
            fonts={"georgia": "Georgia"},
            backgrounds={"plain": "Trơn"},
            max_gallery_images=30,
        ),
    },
    {
        "key": "minimalism_dark_red",
        "name": "Minimalism Đỏ Đậm",
        "description": (
            "Tối giản sang trọng với nền kem, tông đỏ đô, hoa mẫu đơn và dấu triện mạ vàng."
        ),
        "category": "minimal",
        "is_premium": False,
        "position": 3,
        "manifest": _manifest(
            sections=ALL_SECTIONS,
            palettes=[
                _palette("wine_cream", "Đỏ đô – kem", "#511419", "#C9A24A", "#FFF7EB", "#511419"),
            ],
            fonts={"viaoda_libre": "Viaoda Libre"},
            backgrounds={"peony": "Hoa mẫu đơn"},
            max_gallery_images=30,
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
