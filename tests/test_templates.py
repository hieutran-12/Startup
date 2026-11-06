"""Bước 3: schema TemplateManifest, seed 4 mẫu, GET /templates trả manifest.

Spec: 03 › templates; 02 › Quy ước đặt tên. Quy tắc phụ (không trùng, tối thiểu 1 phần tử,
dạng key, mã lỗi) đã chốt ở Bước 3, xem docs/modules/templates.md.
"""

import copy
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import error_details
from app.modules.templates.models import Template
from app.modules.templates.schemas import SectionKey, TemplateManifest
from app.scripts.seed_templates import TEMPLATES, SeedError, seed, validate_templates
from tests.conftest import make_manifest

SEED_KEYS = {"classic_01", "minimal_01", "floral_01", "vintage_01"}


def _errors(data: Any) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as exc:
        TemplateManifest.model_validate(data)
    return [(d["field"], d["code"]) for d in error_details(exc.value.errors())]


def _rows() -> list[dict[str, Any]]:
    return copy.deepcopy(TEMPLATES)


# ---------- TemplateManifest ----------


def test_valid_manifest() -> None:
    manifest = TemplateManifest.model_validate(make_manifest())
    assert manifest.sections[0] is SectionKey.COVER
    assert manifest.model_dump(mode="json") == make_manifest()


def test_section_keys_of_v1() -> None:
    assert [s.value for s in SectionKey] == [
        "cover",
        "greeting",
        "couple",
        "love_story",
        "events",
        "countdown",
        "gallery",
        "gifts",
        "guest_notes",
    ]


def test_missing_and_unknown_fields() -> None:
    data = make_manifest(theme={"primary_color": ["#B08D57"]})
    del data["max_gallery_images"]
    assert sorted(_errors(data)) == [("max_gallery_images", "required"), ("theme", "unknown_field")]


@pytest.mark.parametrize("section", ["music", "bank_accounts", "Cover", ""])
def test_unknown_section(section: str) -> None:
    data = make_manifest(sections=["cover", section])
    assert _errors(data) == [("sections[1]", "invalid_choice")]


def test_default_sections_must_be_subset() -> None:
    data = make_manifest(sections=["cover", "couple"], default_sections=["cover", "events"])
    assert _errors(data) == [("default_sections[1]", "invalid_choice")]


def test_duplicate_sections() -> None:
    data = make_manifest(
        sections=["cover", "couple", "cover"], default_sections=["couple", "couple"]
    )
    assert _errors(data) == [
        ("sections[2]", "invalid_format"),
        ("default_sections[1]", "invalid_format"),
    ]


@pytest.mark.parametrize(
    "field", ["sections", "default_sections", "palettes", "fonts", "backgrounds"]
)
def test_lists_need_at_least_one_item(field: str) -> None:
    assert (field, "out_of_range") in _errors(make_manifest(**{field: []}))


@pytest.mark.parametrize("field", ["sections", "palettes", "defaults", "max_gallery_images"])
def test_null_is_required(field: str) -> None:
    assert _errors(make_manifest(**{field: None})) == [(field, "required")]


@pytest.mark.parametrize("color", ["#b08d57", "#FFF", "B08D57", "#B08D5", "#B08D57FF", " #B08D57"])
@pytest.mark.parametrize("field", ["primary", "secondary", "background", "text"])
def test_palette_colors_are_uppercase_rrggbb(field: str, color: str) -> None:
    data = make_manifest()
    data["palettes"][0][field] = color
    assert _errors(data) == [(f"palettes[0].{field}", "invalid_format")]


def test_palette_fields() -> None:
    data = make_manifest()
    del data["palettes"][0]["text"]
    data["palettes"][0]["name"] = "   "
    data["palettes"][0]["accent"] = "#000000"
    assert sorted(_errors(data)) == [
        ("palettes[0].accent", "unknown_field"),
        ("palettes[0].name", "required"),
        ("palettes[0].text", "required"),
    ]


def test_names_are_normalized() -> None:
    data = make_manifest()
    data["fonts"][0]["name"] = "  Playfair   Display "
    manifest = TemplateManifest.model_validate(data)
    assert manifest.fonts[0].name == "Playfair Display"


@pytest.mark.parametrize(
    ("key", "code"),
    [
        ("ivory-gold", "invalid_format"),
        ("IvoryGold", "invalid_format"),
        ("ivory gold", "invalid_format"),
        (" ivory", "invalid_format"),  # key không được trim
        ("_ivory", "invalid_format"),
        ("ivory_", "invalid_format"),
        ("ivory__gold", "invalid_format"),
        ("01_ivory", "invalid_format"),
        ("", "required"),
    ],
)
def test_option_keys_are_snake_case(key: str, code: str) -> None:
    data = make_manifest()
    data["backgrounds"][1]["key"] = key
    assert _errors(data) == [("backgrounds[1].key", code)]


def test_option_key_max_length() -> None:
    data = make_manifest()
    data["fonts"].append({"key": "a" * 65, "name": "Quá dài"})
    assert _errors(data) == [("fonts[1].key", "too_long")]
    data["fonts"][1]["key"] = "a" * 64
    TemplateManifest.model_validate(data)


@pytest.mark.parametrize("field", ["palettes", "fonts", "backgrounds"])
def test_duplicate_option_keys(field: str) -> None:
    data = make_manifest()
    data[field].append(copy.deepcopy(data[field][0]))
    assert _errors(data) == [(f"{field}[{len(data[field]) - 1}].key", "invalid_format")]


@pytest.mark.parametrize(
    ("field", "value"),
    [("palette_key", "rose"), ("font_key", "lora"), ("background_key", "kraft")],
)
def test_defaults_must_exist_in_lists(field: str, value: str) -> None:
    data = make_manifest()
    data["defaults"][field] = value
    assert _errors(data) == [(f"defaults.{field}", "invalid_choice")]


def test_defaults_are_required() -> None:
    data = make_manifest(defaults={"palette_key": "ivory_gold", "font_key": None})
    assert sorted(_errors(data)) == [
        ("defaults.background_key", "required"),
        ("defaults.font_key", "required"),
    ]


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("30", "invalid_format"),
        (30.0, "invalid_format"),
        (True, "invalid_format"),
        (-1, "out_of_range"),
    ],
)
def test_max_gallery_images_is_non_negative_int(value: Any, code: str) -> None:
    assert _errors(make_manifest(max_gallery_images=value)) == [("max_gallery_images", code)]


def test_max_gallery_images_zero_is_allowed() -> None:
    TemplateManifest.model_validate(make_manifest(max_gallery_images=0))


# ---------- Danh sách seed ----------


def test_seed_list_is_valid() -> None:
    templates = validate_templates(TEMPLATES)
    assert {t.key for t in templates} == SEED_KEYS
    assert sorted(t.position for t in templates) == [0, 1, 2, 3]
    assert [t.key for t in templates if t.is_premium] == ["vintage_01"]


def _seed_errors(rows: list[dict[str, Any]]) -> list[tuple[int, Any, str, str]]:
    with pytest.raises(SeedError) as exc:
        validate_templates(rows)
    return [(e["index"], e["key"], e["field"], e["code"]) for e in exc.value.errors]


@pytest.mark.parametrize("key", ["classic-01", "Classic_01", "classic 01", " classic_01"])
def test_seed_rejects_non_snake_case_key(key: str) -> None:
    rows = _rows()
    rows[0]["key"] = key
    assert _seed_errors(rows) == [(0, key, "key", "invalid_format")]


def test_seed_reports_manifest_errors_with_path() -> None:
    rows = _rows()
    rows[1]["manifest"]["defaults"]["palette_key"] = "khong_co"
    rows[3]["manifest"]["sections"].append("music")
    rows[3]["category"] = "royal"
    assert _seed_errors(rows) == [
        (1, rows[1]["key"], "manifest.defaults.palette_key", "invalid_choice"),
        (3, rows[3]["key"], "category", "invalid_choice"),
        (3, rows[3]["key"], "manifest.sections[9]", "invalid_choice"),
    ]


def test_seed_error_message_names_template_and_field() -> None:
    rows = _rows()
    del rows[2]["manifest"]["fonts"]
    with pytest.raises(SeedError) as exc:
        validate_templates(rows)
    assert f"{rows[2]['key']}" in str(exc.value)
    assert "manifest.fonts" in str(exc.value)


def test_seed_rejects_duplicate_keys() -> None:
    rows = _rows()
    rows[2]["key"] = rows[0]["key"]
    assert _seed_errors(rows) == [(2, rows[0]["key"], "key", "invalid_format")]


def test_seed_row_fields() -> None:
    rows = _rows()
    rows[0]["name"] = ""
    rows[0]["position"] = -1
    rows[0]["is_premium"] = "false"
    rows[0]["sort_order"] = 1
    assert sorted(_seed_errors(rows)) == [
        (0, "classic_01", "is_premium", "invalid_format"),
        (0, "classic_01", "name", "required"),
        (0, "classic_01", "position", "out_of_range"),
        (0, "classic_01", "sort_order", "unknown_field"),
    ]


# ---------- Ghi vào database ----------


async def _all_templates(session_maker: async_sessionmaker) -> dict[str, Template]:
    async with session_maker() as db:
        return {t.key: t for t in await db.scalars(select(Template))}


async def test_seed_twice_is_idempotent(session_maker: async_sessionmaker) -> None:
    async with session_maker() as db:
        assert await seed(db) == 4
    first = await _all_templates(session_maker)

    async with session_maker() as db:
        assert await seed(db) == 4
    second = await _all_templates(session_maker)

    assert set(second) == SEED_KEYS
    for row in validate_templates(TEMPLATES):
        stored = second[row.key]
        assert stored.id == first[row.key].id
        assert stored.manifest == row.manifest.model_dump(mode="json")
        assert (stored.name, stored.description, stored.category) == (
            row.name,
            row.description,
            row.category,
        )
        assert (stored.is_premium, stored.position, stored.is_active) == (
            row.is_premium,
            row.position,
            True,
        )


async def test_reseed_overwrites_changed_rows(session_maker: async_sessionmaker) -> None:
    async with session_maker() as db:
        await seed(db)
    rows = _rows()
    del rows[0]["description"]  # bỏ khỏi seed thì cột về mặc định (null)
    rows[0]["manifest"]["max_gallery_images"] = 5
    rows[0]["is_premium"] = True
    async with session_maker() as db:
        await seed(db, rows)

    stored = (await _all_templates(session_maker))["classic_01"]
    assert stored.description is None
    assert stored.manifest["max_gallery_images"] == 5
    assert stored.is_premium is True


async def test_invalid_seed_writes_nothing(session_maker: async_sessionmaker) -> None:
    async with session_maker() as db:
        await seed(db)
    before = await _all_templates(session_maker)

    rows = _rows()
    rows[0]["name"] = "Tên mới"  # dòng hợp lệ đứng trước dòng sai cũng không được ghi
    rows[1]["manifest"]["palettes"][0]["primary"] = "#abcdef"
    async with session_maker() as db:
        with pytest.raises(SeedError):
            await seed(db, rows)

    after = await _all_templates(session_maker)
    assert {k: (t.name, t.manifest) for k, t in after.items()} == {
        k: (t.name, t.manifest) for k, t in before.items()
    }


# ---------- API ----------


async def test_get_templates_returns_manifest(
    client: AsyncClient, session_maker: async_sessionmaker
) -> None:
    async with session_maker() as db:
        await seed(db)
    expected = {t.key: t for t in validate_templates(TEMPLATES)}

    resp = await client.get("/templates")
    assert resp.status_code == 200
    body = resp.json()
    # Sắp theo position
    assert [t["key"] for t in body] == sorted(expected, key=lambda k: expected[k].position)
    for item in body:
        assert set(item) == {
            "id",
            "key",
            "name",
            "description",
            "thumbnail_url",
            "category",
            "is_premium",
            "manifest",
        }
        assert item["manifest"] == expected[item["key"]].manifest.model_dump(mode="json")

    one = await client.get("/templates/floral_01")
    assert one.status_code == 200
    assert one.json()["manifest"] == expected["floral_01"].manifest.model_dump(mode="json")
    assert (await client.get("/templates/floral-01")).status_code == 404


async def test_manifest_schema_in_openapi(client: AsyncClient) -> None:
    schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]
    manifest = schemas["TemplateManifest"]
    assert set(manifest["properties"]) == {
        "sections",
        "default_sections",
        "palettes",
        "fonts",
        "backgrounds",
        "defaults",
        "max_gallery_images",
    }
    assert "TemplateResponse" in schemas
