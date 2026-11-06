"""Bước 4: JSON Merge Patch (RFC 7386) với quy ước null của spec.

Spec: 04 › Sửa thiệp (object gộp đệ quy, danh sách thay nguyên); 02 › NULL, rỗng và mặc định
(null là "không có giá trị": danh sách thành [], trường khác thành null để kiểm tra schema).
"""

import copy

from app.core.merge_patch import merge_patch

TARGET = {
    "couple": {
        "groom": {"full_name": "Nguyễn Văn Nam", "display_name": "Nam"},
        "bride": {"full_name": "Lê Thị Lan", "display_name": None},
    },
    "love_story": [{"title": "Lần đầu gặp nhau"}, {"title": "Cầu hôn"}],
    "appearance": {"palette_key": "ivory_gold", "sections": ["cover", "events"]},
}


def test_field_not_sent_is_kept() -> None:
    result = merge_patch(TARGET, {"couple": {"groom": {"display_name": "Nam Béo"}}})
    assert result["couple"]["groom"] == {"full_name": "Nguyễn Văn Nam", "display_name": "Nam Béo"}
    assert result["couple"]["bride"] == TARGET["couple"]["bride"]
    assert result["love_story"] == TARGET["love_story"]
    assert result["appearance"] == TARGET["appearance"]


def test_null_clears_value_but_keeps_key() -> None:
    result = merge_patch(TARGET, {"couple": {"groom": {"display_name": None}}})
    assert result["couple"]["groom"] == {"full_name": "Nguyễn Văn Nam", "display_name": None}


def test_null_on_list_becomes_empty_list() -> None:
    result = merge_patch(TARGET, {"love_story": None, "appearance": {"sections": None}})
    assert result["love_story"] == []
    assert result["appearance"]["sections"] == []


def test_null_on_object_becomes_none() -> None:
    # Không xoá trắng cả nhóm: để schema trả required (nhóm object luôn có mặt)
    assert merge_patch(TARGET, {"couple": None})["couple"] is None


def test_list_is_replaced_not_merged() -> None:
    result = merge_patch(TARGET, {"love_story": [{"title": "Đám cưới", "year": None}]})
    assert result["love_story"] == [{"title": "Đám cưới", "year": None}]


def test_object_patch_on_non_object_starts_from_empty_object() -> None:
    result = merge_patch(TARGET, {"couple": {"bride": {"display_name": {"x": 1}}}})
    assert result["couple"]["bride"]["display_name"] == {"x": 1}


def test_unknown_key_is_added_for_schema_to_reject() -> None:
    result = merge_patch(TARGET, {"theme": None, "extra": {"a": 1}})
    assert result["theme"] is None
    assert result["extra"] == {"a": 1}


def test_scalar_patch_replaces_target() -> None:
    assert merge_patch(TARGET, [1, 2]) == [1, 2]
    assert merge_patch("cũ", "mới") == "mới"


def test_empty_patch_changes_nothing() -> None:
    assert merge_patch(TARGET, {}) == TARGET


def test_target_is_not_mutated() -> None:
    before = copy.deepcopy(TARGET)
    merge_patch(
        TARGET,
        {
            "couple": {"groom": {"full_name": None}, "bride": {"display_name": "Lan"}},
            "love_story": None,
            "appearance": {"sections": ["cover"]},
        },
    )
    assert before == TARGET
