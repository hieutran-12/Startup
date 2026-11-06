"""Bước 4: schema content v1 (InvitationContent), kiểm tra appearance theo manifest.

Spec: 03 › Nội dung thiệp (content, schema version 1); 02 › NULL, rỗng và mặc định;
04 › Chuẩn hóa chuỗi. Mã lỗi: 05 › Định dạng lỗi. Trùng section → invalid_format, ngoài
manifest → invalid_choice (cùng mã với manifest, chốt ở Bước 3).
"""

import unicodedata
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.errors import error_details
from app.modules.invitations.schemas import InvitationContent
from app.modules.templates.schemas import SectionKey, TemplateManifest
from tests.conftest import empty_content, make_manifest

ALL_SECTIONS = [section.value for section in SectionKey]
# Manifest có đủ 9 section (ví dụ trong spec dùng cả gifts)
FULL_MANIFEST = TemplateManifest.model_validate(make_manifest(sections=ALL_SECTIONS))
# Manifest của fixture classic_01: không có love_story, countdown, gifts, guest_notes
SMALL_MANIFEST = TemplateManifest.model_validate(make_manifest())

# Ví dụ content hợp lệ trong spec 03
SPEC_EXAMPLE: dict[str, Any] = {
    "couple": {
        "groom": {
            "full_name": "Nguyễn Văn Nam",
            "display_name": "Nam",
            "birth_order": "eldest",
            "bio": None,
            "father": {"full_name": "Nguyễn Văn Hùng", "is_deceased": False},
            "mother": {"full_name": "Trần Thị Hoa", "is_deceased": True},
            "family_address": "Số 12 ngõ 34 Láng Hạ, Đống Đa, Hà Nội",
        },
        "bride": {
            "full_name": "Lê Thị Lan",
            "display_name": "Lan",
            "birth_order": None,
            "bio": None,
            "father": {"full_name": None, "is_deceased": False},
            "mother": {"full_name": None, "is_deceased": False},
            "family_address": None,
        },
    },
    "messages": {
        "greeting": "Cảm ơn bạn đã là một phần trong câu chuyện của chúng mình.",
        "invitation_message": None,
        "guest_notes": None,
    },
    "love_story": [
        {
            "title": "Lần đầu gặp nhau",
            "description": None,
            "year": 2019,
            "month": 3,
            "media_id": None,
        }
    ],
    "gifts": [
        {
            "recipient_side": "groom",
            "bank_bin": "970436",
            "account_number": "0123456789",
            "account_holder": "NGUYEN VAN NAM",
        }
    ],
    "appearance": {
        "palette_key": None,
        "font_key": None,
        "background_key": None,
        "sections": ["cover", "greeting", "couple", "events", "gallery", "gifts"],
    },
}

MEDIA_ID = "6f1c2b9e-3d4a-4e5f-8a7b-1c2d3e4f5a6b"


def _validate(data: dict[str, Any], manifest: TemplateManifest | None = FULL_MANIFEST):
    context = {"manifest": manifest} if manifest is not None else None
    return InvitationContent.model_validate(data, context=context)


def _errors(
    data: dict[str, Any], manifest: TemplateManifest | None = FULL_MANIFEST
) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as exc:
        _validate(data, manifest)
    return [(d["field"], d["code"]) for d in error_details(exc.value.errors())]


def _content(**groups: Any) -> dict[str, Any]:
    """Content tối thiểu hợp lệ (chỉ có appearance.sections), ghi đè từng nhóm."""
    return {"appearance": {"sections": ["cover"]}, **groups}


def _groom(**fields: Any) -> dict[str, Any]:
    return _content(couple={"groom": fields})


def _love_story(*items: dict[str, Any]) -> dict[str, Any]:
    return _content(love_story=list(items))


def _gift(**overrides: Any) -> dict[str, Any]:
    gift = {
        "recipient_side": "bride",
        "bank_bin": "970436",
        "account_number": "0123456789",
        "account_holder": "LE THI LAN",
    }
    return {**gift, **overrides}


# ---------- Cấu trúc ----------


def test_spec_example_is_valid() -> None:
    assert _validate(SPEC_EXAMPLE).model_dump(mode="json") == SPEC_EXAMPLE


def test_missing_fields_get_defaults_and_dump_is_complete() -> None:
    dumped = _validate({"appearance": {"sections": []}}).model_dump(mode="json")
    assert dumped == empty_content([])


def test_appearance_sections_has_no_default() -> None:
    assert _errors({}) == [("appearance", "required")]
    assert _errors({"appearance": {}}) == [("appearance.sections", "required")]
    assert _errors({"appearance": {"sections": None}}) == [("appearance.sections", "required")]


@pytest.mark.parametrize(
    ("data", "field"),
    [
        (_groom(short_name="Nam"), "couple.groom.short_name"),
        (_content(events=[]), "events"),
        (_content(theme={}), "theme"),
        (_content(couple={"groom": {"father": {"name": "Hùng"}}}), "couple.groom.father.name"),
        (_content(messages={"footer": "x"}), "messages.footer"),
        (_love_story({"title": "A", "date": "2019-03"}), "love_story[0].date"),
        (_content(gifts=[_gift(bank_name="VCB")]), "gifts[0].bank_name"),
        (_content(appearance={"sections": [], "color": "#FFFFFF"}), "appearance.color"),
    ],
)
def test_unknown_field_is_rejected(data: dict[str, Any], field: str) -> None:
    assert _errors(data) == [(field, "unknown_field")]


@pytest.mark.parametrize(
    ("data", "field"),
    [
        (_content(couple=None), "couple"),
        (_content(couple={"groom": None}), "couple.groom"),
        (_groom(father=None), "couple.groom.father"),
        (_content(messages=None), "messages"),
        (_content(appearance=None), "appearance"),
    ],
)
def test_null_object_group_is_required(data: dict[str, Any], field: str) -> None:
    assert _errors(data) == [(field, "required")]


@pytest.mark.parametrize(
    ("data", "field"),
    [
        (_content(couple=[]), "couple"),
        (_content(love_story={"title": "A"}), "love_story"),
        (_content(gifts="970436"), "gifts"),
        (_content(appearance={"sections": "cover"}), "appearance.sections"),
    ],
)
def test_wrong_container_type_is_invalid_format(data: dict[str, Any], field: str) -> None:
    assert _errors(data) == [(field, "invalid_format")]


# ---------- couple ----------


def test_person_text_is_normalized() -> None:
    decomposed = unicodedata.normalize("NFD", "Nguyễn  Văn Nam")
    content = _validate(
        _groom(
            full_name=f"  {decomposed} ",
            display_name="   ",
            bio="Kỹ sư\r\nThích leo núi",
            family_address="",
        )
    )
    groom = content.couple.groom
    assert groom.full_name == "Nguyễn Văn Nam"
    assert unicodedata.is_normalized("NFC", groom.full_name)
    assert groom.display_name is None
    assert groom.bio == "Kỹ sư\nThích leo núi"
    assert groom.family_address is None


@pytest.mark.parametrize(
    ("path", "max_length"),
    [
        (("couple", "groom", "full_name"), 100),
        (("couple", "bride", "display_name"), 40),
        (("couple", "groom", "bio"), 500),
        (("couple", "bride", "family_address"), 300),
        (("couple", "groom", "father", "full_name"), 100),
        (("couple", "bride", "mother", "full_name"), 100),
        (("messages", "greeting"), 1000),
        (("messages", "invitation_message"), 500),
        (("messages", "guest_notes"), 1000),
    ],
)
def test_text_limits(path: tuple[str, ...], max_length: int) -> None:
    def build(value: str) -> dict[str, Any]:
        node: Any = value
        for key in reversed(path):
            node = {key: node}
        return _content(**node)

    _validate(build("a" * max_length))
    assert _errors(build("a" * (max_length + 1))) == [(".".join(path), "too_long")]


def test_single_line_rejects_newline() -> None:
    assert _errors(_groom(display_name="Nam\nBéo")) == [
        ("couple.groom.display_name", "invalid_characters")
    ]


@pytest.mark.parametrize("value", ["eldest", "middle", "youngest", None])
def test_birth_order_accepts_enum_or_null(value: str | None) -> None:
    assert _validate(_groom(birth_order=value)).couple.groom.birth_order == value


@pytest.mark.parametrize("value", ["ELDEST", " eldest", "truong_nam", ""])
def test_birth_order_rejects_other_values(value: str) -> None:
    assert _errors(_groom(birth_order=value)) == [("couple.groom.birth_order", "invalid_choice")]


def test_is_deceased_is_strict_boolean() -> None:
    assert _validate(_groom(father={"full_name": "Hùng"})).couple.groom.father.is_deceased is False
    assert _errors(_groom(father={"is_deceased": None})) == [
        ("couple.groom.father.is_deceased", "required")
    ]
    for value in ["true", 1, 0]:
        assert _errors(_groom(mother={"is_deceased": value})) == [
            ("couple.groom.mother.is_deceased", "invalid_format")
        ]


# ---------- love_story ----------


def test_love_story_item_defaults() -> None:
    item = _validate(_love_story({"title": "Lần đầu gặp nhau"})).model_dump(mode="json")
    assert item["love_story"] == [
        {
            "title": "Lần đầu gặp nhau",
            "description": None,
            "year": None,
            "month": None,
            "media_id": None,
        }
    ]


def test_love_story_has_at_most_12_items() -> None:
    _validate(_love_story(*[{"title": f"Mốc {i}"} for i in range(12)]))
    assert _errors(_love_story(*[{"title": f"Mốc {i}"} for i in range(13)])) == [
        ("love_story", "too_long")
    ]


@pytest.mark.parametrize("title", [None, "", "   "])
def test_love_story_title_is_required(title: str | None) -> None:
    assert _errors(_love_story({"title": title})) == [("love_story[0].title", "required")]
    assert _errors(_love_story({"year": 2019})) == [("love_story[0].title", "required")]


def test_love_story_text_limits() -> None:
    _validate(_love_story({"title": "a" * 100, "description": "b" * 1000}))
    assert _errors(_love_story({"title": "a" * 101, "description": "b" * 1001})) == [
        ("love_story[0].title", "too_long"),
        ("love_story[0].description", "too_long"),
    ]


@pytest.mark.parametrize(
    ("item", "field", "code"),
    [
        ({"year": 1899}, "year", "out_of_range"),
        ({"year": 2101}, "year", "out_of_range"),
        ({"year": 2019, "month": 0}, "month", "out_of_range"),
        ({"year": 2019, "month": 13}, "month", "out_of_range"),
        ({"year": "2019"}, "year", "invalid_format"),
        ({"year": 2019.0}, "year", "invalid_format"),
        ({"year": True}, "year", "invalid_format"),
        ({"year": 2019, "month": "03"}, "month", "invalid_format"),
    ],
)
def test_love_story_year_month_are_strict_integers(
    item: dict[str, Any], field: str, code: str
) -> None:
    assert _errors(_love_story({"title": "A", **item})) == [(f"love_story[0].{field}", code)]


def test_love_story_year_month_bounds_are_inclusive() -> None:
    _validate(_love_story({"title": "A", "year": 1900, "month": 1}, {"title": "B", "year": 2100}))
    _validate(_love_story({"title": "A", "year": 2019, "month": 12}))


def test_love_story_month_requires_year() -> None:
    data = _love_story({"title": "A"}, {"title": "B", "year": None, "month": 3})
    with pytest.raises(ValidationError) as exc:
        _validate(data)
    assert error_details(exc.value.errors()) == [
        {"field": "love_story[1].year", "code": "required", "message": "Cần nhập năm khi có tháng"}
    ]


def test_love_story_media_id_is_lowercase_uuid() -> None:
    item = _validate(_love_story({"title": "A", "media_id": MEDIA_ID})).love_story[0]
    assert str(item.media_id) == MEDIA_ID
    assert _errors(_love_story({"title": "A", "media_id": MEDIA_ID.upper()})) == [
        ("love_story[0].media_id", "invalid_format")
    ]


# ---------- gifts ----------


def test_gifts_have_at_most_4_items() -> None:
    _validate(_content(gifts=[_gift() for _ in range(4)]))
    assert _errors(_content(gifts=[_gift() for _ in range(5)])) == [("gifts", "too_long")]


@pytest.mark.parametrize(
    "field", ["recipient_side", "bank_bin", "account_number", "account_holder"]
)
def test_gift_fields_are_required(field: str) -> None:
    missing = _gift()
    del missing[field]
    assert _errors(_content(gifts=[missing])) == [(f"gifts[0].{field}", "required")]
    assert _errors(_content(gifts=[_gift(**{field: None})])) == [(f"gifts[0].{field}", "required")]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("recipient_side", "both", "invalid_choice"),
        ("recipient_side", "GROOM", "invalid_choice"),
        ("bank_bin", "97043", "invalid_format"),
        ("bank_bin", "9704361", "invalid_format"),
        ("bank_bin", "97043a", "invalid_format"),
        ("bank_bin", 970436, "invalid_format"),
        ("account_number", "12345", "invalid_format"),
        ("account_number", "1" * 20, "invalid_format"),
        ("account_number", "0123 456789", "invalid_format"),
        ("account_number", "0123.456789", "invalid_format"),
        ("account_holder", "   ", "required"),
        ("account_holder", "A" * 101, "too_long"),
    ],
)
def test_gift_field_rules(field: str, value: Any, code: str) -> None:
    assert _errors(_content(gifts=[_gift(**{field: value})])) == [(f"gifts[0].{field}", code)]


def test_gift_digits_keep_leading_zero_and_are_trimmed() -> None:
    gift = _validate(
        _content(gifts=[_gift(bank_bin=" 970436 ", account_number="000123456789")])
    ).gifts[0]
    assert gift.bank_bin == "970436"
    assert gift.account_number == "000123456789"
    _validate(_content(gifts=[_gift(account_number="123456"), _gift(account_number="1" * 19)]))


# ---------- appearance theo manifest ----------


def test_appearance_keys_must_be_in_manifest() -> None:
    data = _content(
        appearance={
            "palette_key": "walnut",
            "font_key": "lora",
            "background_key": "kraft",
            "sections": ["cover"],
        }
    )
    assert _errors(data) == [
        ("appearance.palette_key", "invalid_choice"),
        ("appearance.font_key", "invalid_choice"),
        ("appearance.background_key", "invalid_choice"),
    ]


def test_appearance_keys_accept_manifest_values_or_null() -> None:
    appearance = _validate(
        _content(
            appearance={
                "palette_key": "burgundy",
                "font_key": None,
                "background_key": "paper",
                "sections": ["cover"],
            }
        )
    ).appearance
    assert (appearance.palette_key, appearance.font_key, appearance.background_key) == (
        "burgundy",
        None,
        "paper",
    )


@pytest.mark.parametrize("value", ["Burgundy", " burgundy", ""])
def test_appearance_keys_are_matched_exactly(value: str) -> None:
    data = _content(appearance={"palette_key": value, "sections": ["cover"]})
    assert _errors(data) == [("appearance.palette_key", "invalid_choice")]


def test_appearance_key_must_be_string() -> None:
    data = _content(appearance={"font_key": 1, "sections": ["cover"]})
    assert _errors(data) == [("appearance.font_key", "invalid_format")]


def test_sections_keep_order_and_may_be_empty() -> None:
    sections = ["events", "cover", "gallery"]
    assert _validate(_content(appearance={"sections": sections})).appearance.sections == sections
    assert _validate(_content(appearance={"sections": []})).appearance.sections == []


def test_sections_must_be_in_manifest() -> None:
    data = _content(appearance={"sections": ["cover", "gifts", "events", "countdown"]})
    assert _errors(data, SMALL_MANIFEST) == [
        ("appearance.sections[1]", "invalid_choice"),
        ("appearance.sections[3]", "invalid_choice"),
    ]


def test_unknown_section_key_is_invalid_choice() -> None:
    data = _content(appearance={"sections": ["cover", "footer"]})
    assert _errors(data) == [("appearance.sections[1]", "invalid_choice")]


def test_duplicate_sections_are_invalid_format() -> None:
    data = _content(appearance={"sections": ["cover", "events", "cover", "events"]})
    assert _errors(data) == [
        ("appearance.sections[2]", "invalid_format"),
        ("appearance.sections[3]", "invalid_format"),
    ]


def test_without_manifest_only_structure_is_checked() -> None:
    # Dùng khi đọc content đã lưu để trả response: không có manifest trong context
    data = _content(appearance={"palette_key": "walnut", "sections": ["countdown"]})
    assert _validate(data, manifest=None).appearance.palette_key == "walnut"
    duplicated = _content(appearance={"sections": ["cover", "cover"]})
    assert _errors(duplicated, manifest=None) == [("appearance.sections[1]", "invalid_format")]
