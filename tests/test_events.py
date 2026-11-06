"""Sự kiện của thiệp: CRUD, tên mặc định, thứ tự, giới hạn 10, If-Match, quy tắc nhiều cột.

Spec Bước 5: 03 › events; 04 › Sự kiện, Sửa thiệp; 05 (endpoint, mã lỗi). 11 đề xuất được duyệt
2026-11-06 (docs/modules/events.md). Các CHECK đã có test ở tầng database
(tests/test_db_schema.py); ở đây kiểm tra tầng API trả 422 đúng trường trước khi chạm database.
"""

import asyncio
import json
import unicodedata
import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response

from app.core.config import settings
from app.modules.events import router as events_router
from app.modules.events.models import EventType, HostSide, default_event_name

RECEPTION = {"event_type": "reception", "host_side": "both"}

NAMES = {
    "couple": {
        "groom": {"full_name": "Nguyễn Văn Nam", "display_name": "Nam"},
        "bride": {"full_name": "Lê Thị Lan", "display_name": "Lan"},
    }
}

EVENT_FIELDS = {
    "id",
    "event_type",
    "host_side",
    "event_name",
    "display_name",
    "event_date",
    "start_time",
    "end_time",
    "timezone",
    "venue_name",
    "address",
    "latitude",
    "longitude",
    "maps_url",
    "position",
    "created_at",
    "updated_at",
}

FULL_EVENT = {
    "event_type": "family_ceremony",
    "host_side": "bride",
    "event_name": None,
    "event_date": "2026-12-20",
    "start_time": "09:00",
    "end_time": "11:30",
    "timezone": "Asia/Ho_Chi_Minh",
    "venue_name": "Tư gia nhà gái",
    "address": "Số 5 ngõ 12 Láng Hạ, Đống Đa, Hà Nội",
    "latitude": 21.028511,
    "longitude": 105.804817,
    "maps_url": "https://maps.app.goo.gl/abc123",
}

# Bảng tên mặc định (spec 04 › Sự kiện): None là ô "Không hợp lệ" / "Bắt buộc có event_name"
DEFAULT_NAMES = [
    ("engagement", "groom", "Lễ ăn hỏi"),
    ("engagement", "bride", "Lễ ăn hỏi"),
    ("engagement", "both", "Lễ ăn hỏi"),
    ("family_ceremony", "groom", "Lễ thành hôn"),
    ("family_ceremony", "bride", "Lễ vu quy"),
    ("family_ceremony", "both", None),
    ("religious_ceremony", "groom", "Lễ cưới"),
    ("religious_ceremony", "bride", "Lễ cưới"),
    ("religious_ceremony", "both", "Lễ cưới"),
    ("reception", "groom", "Tiệc cưới nhà trai"),
    ("reception", "bride", "Tiệc cưới nhà gái"),
    ("reception", "both", "Tiệc cưới"),
    ("other", "groom", None),
    ("other", "bride", None),
    ("other", "both", None),
]


# ---------- Helper ----------


async def _invitation(client: AsyncClient, auth: dict, **payload: Any) -> dict:
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", **payload}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _url(inv: dict, event: dict | str | None = None) -> str:
    url = f"/invitations/{inv['id']}/events"
    if event is not None:
        url += f"/{event if isinstance(event, str) else event['id']}"
    return url


async def _etag(client: AsyncClient, auth: dict, inv: dict) -> str:
    resp = await client.get(_url(inv), headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.headers["etag"]


async def _revision(client: AsyncClient, auth: dict, inv: dict) -> int:
    resp = await client.get(f"/invitations/{inv['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()["revision"]


async def _headers(client: AsyncClient, auth: dict, inv: dict, if_match: str | None) -> dict:
    """If-Match là revision hiện tại của thiệp, trừ khi truyền `if_match`."""
    return {**auth, "If-Match": if_match or await _etag(client, auth, inv)}


async def _post(
    client: AsyncClient, auth: dict, inv: dict, body: Any, *, if_match: str | None = None
) -> Response:
    headers = await _headers(client, auth, inv, if_match)
    return await client.post(_url(inv), json=body, headers=headers)


async def _post_ok(client: AsyncClient, auth: dict, inv: dict, body: Any) -> dict:
    resp = await _post(client, auth, inv, body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _patch(
    client: AsyncClient,
    auth: dict,
    inv: dict,
    event: dict | str,
    body: Any,
    *,
    if_match: str | None = None,
) -> Response:
    headers = await _headers(client, auth, inv, if_match)
    return await client.patch(_url(inv, event), json=body, headers=headers)


async def _patch_ok(client: AsyncClient, auth: dict, inv: dict, event: dict, body: Any) -> dict:
    resp = await _patch(client, auth, inv, event, body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _delete(
    client: AsyncClient, auth: dict, inv: dict, event: dict | str, *, if_match: str | None = None
) -> Response:
    headers = await _headers(client, auth, inv, if_match)
    return await client.delete(_url(inv, event), headers=headers)


async def _list(client: AsyncClient, auth: dict, inv: dict) -> list[dict]:
    resp = await client.get(_url(inv), headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _details(resp: Response, status_code: int = 422) -> list[tuple[str, str]]:
    assert resp.status_code == status_code, resp.text
    return [(d["field"], d["code"]) for d in resp.json()["error"]["details"]]


def _error_code(resp: Response) -> str:
    return resp.json()["error"]["code"]


# ---------- Tạo, xem ----------


async def test_list_is_empty_and_has_etag(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    resp = await client.get(_url(inv), headers=auth)
    assert resp.status_code == 200
    assert resp.json() == []
    assert resp.headers["etag"] == '"1"'


async def test_create_minimal_event_fills_defaults(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    resp = await _post(client, auth, inv, RECEPTION)
    assert resp.status_code == 201, resp.text
    assert resp.headers["etag"] == '"2"'
    body = resp.json()
    assert set(body) == EVENT_FIELDS
    assert body["event_type"] == "reception"
    assert body["host_side"] == "both"
    assert body["event_name"] is None
    assert body["display_name"] == "Tiệc cưới"
    assert body["timezone"] == "Asia/Ho_Chi_Minh"
    assert body["position"] == 0
    for field in (
        "event_date",
        "start_time",
        "end_time",
        "venue_name",
        "address",
        "latitude",
        "longitude",
        "maps_url",
    ):
        assert body[field] is None, field
    assert await _list(client, auth, inv) == [body]


async def test_create_full_event(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    body = await _post_ok(client, auth, inv, FULL_EVENT)
    assert {k: body[k] for k in FULL_EVENT} == FULL_EVENT
    assert body["display_name"] == "Lễ vu quy"
    # Tọa độ trả về là số JSON, giờ là "HH:MM"
    assert isinstance(body["latitude"], float) and isinstance(body["longitude"], float)


async def test_create_normalizes_text(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    body = await _post_ok(
        client,
        auth,
        inv,
        {
            **RECEPTION,
            "event_name": unicodedata.normalize("NFD", "  Tiệc   báo hỷ  "),
            "venue_name": "   ",
            "address": " Số 1  Tràng Tiền ",
            "maps_url": "  https://maps.app.goo.gl/abc  ",
        },
    )
    assert body["event_name"] == "Tiệc báo hỷ"
    assert body["display_name"] == "Tiệc báo hỷ"
    assert body["venue_name"] is None
    assert body["address"] == "Số 1 Tràng Tiền"
    assert body["maps_url"] == "https://maps.app.goo.gl/abc"


async def test_create_rejects_invalid_fields(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    resp = await _post(
        client,
        auth,
        inv,
        {
            "event_type": "wedding",
            "host_side": "Groom",
            "event_name": "x" * 121,
            "event_date": "20/12/2026",
            "start_time": "18:30:00",
            "end_time": "6h",
            "timezone": "asia/ho_chi_minh",
            "venue_name": "Nhà hàng\nABC",
            "address": "a" * 501,
            "latitude": "21.02",
            "longitude": True,
            "maps_url": "maps.google.com",
        },
    )
    assert _details(resp) == [
        ("event_type", "invalid_choice"),
        ("host_side", "invalid_choice"),
        ("event_name", "too_long"),
        ("event_date", "invalid_format"),
        ("start_time", "invalid_format"),
        ("end_time", "invalid_format"),
        ("timezone", "invalid_choice"),
        ("venue_name", "invalid_characters"),
        ("address", "too_long"),
        ("latitude", "invalid_format"),
        ("longitude", "invalid_format"),
        ("maps_url", "invalid_format"),
    ]
    assert await _list(client, auth, inv) == []
    assert await _revision(client, auth, inv) == 1


async def test_create_requires_type_and_side(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    assert _details(await _post(client, auth, inv, {})) == [
        ("event_type", "required"),
        ("host_side", "required"),
    ]
    resp = await _post(client, auth, inv, {"event_type": None, "host_side": None})
    assert _details(resp) == [("event_type", "required"), ("host_side", "required")]


@pytest.mark.parametrize("timezone", [None, "", "  "])
async def test_create_timezone_null_or_empty_is_required(
    client: AsyncClient, templates, auth, timezone: str | None
) -> None:
    inv = await _invitation(client, auth)
    resp = await _post(client, auth, inv, {**RECEPTION, "timezone": timezone})
    assert _details(resp) == [("timezone", "required")]


async def test_create_accepts_other_iana_timezone(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    body = await _post_ok(client, auth, inv, {**RECEPTION, "timezone": "Europe/Paris"})
    assert body["timezone"] == "Europe/Paris"


@pytest.mark.parametrize("field", ["id", "invitation_id", "position", "display_name", "theme"])
async def test_create_rejects_unknown_fields(
    client: AsyncClient, templates, auth, field: str
) -> None:
    inv = await _invitation(client, auth)
    resp = await _post(client, auth, inv, {**RECEPTION, field: 1})
    assert _details(resp) == [(field, "unknown_field")]


# ---------- Tọa độ, link chỉ đường ----------


async def test_coordinates_are_json_numbers(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    body = await _post_ok(client, auth, inv, {**RECEPTION, "latitude": 21, "longitude": -180})
    assert (body["latitude"], body["longitude"]) == (21, -180)
    # 0 là một giá trị, không phải "không có" (spec 02 › NULL, rỗng và mặc định)
    zero = await _post_ok(client, auth, inv, {**RECEPTION, "latitude": 0, "longitude": 0})
    assert (zero["latitude"], zero["longitude"]) == (0, 0)
    edge = await _post_ok(client, auth, inv, {**RECEPTION, "latitude": -90, "longitude": 180.0})
    assert (edge["latitude"], edge["longitude"]) == (-90, 180)


@pytest.mark.parametrize(
    "raw",
    [
        '{"event_type": "reception", "host_side": "both", "latitude": NaN, "longitude": 1}',
        '{"event_type": "reception", "host_side": "both", "latitude": Infinity, "longitude": 1}',
    ],
)
async def test_coordinates_reject_non_finite_numbers(
    client: AsyncClient, templates, auth, raw: str
) -> None:
    inv = await _invitation(client, auth)
    headers = {**auth, "If-Match": '"1"', "Content-Type": "application/json"}
    resp = await client.post(_url(inv), content=raw, headers=headers)
    assert _details(resp) == [("latitude", "invalid_format")]


async def test_coordinates_reject_more_than_six_decimal_places(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _invitation(client, auth)
    resp = await _post(client, auth, inv, {**RECEPTION, "latitude": 21.0285111, "longitude": 105})
    assert resp.json()["error"]["details"] == [
        {
            "field": "latitude",
            "code": "invalid_format",
            "message": "Tối đa 6 chữ số sau dấu thập phân",
        }
    ]


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/map",
        "javascript:alert(1)",
        "https://",
        "https://maps.google.com/?q=Nhà hàng",
        "//maps.google.com",
    ],
)
async def test_maps_url_must_be_http_or_https(
    client: AsyncClient, templates, auth, url: str
) -> None:
    inv = await _invitation(client, auth)
    resp = await _post(client, auth, inv, {**RECEPTION, "maps_url": url})
    assert _details(resp) == [("maps_url", "invalid_format")]


async def test_maps_url_too_long(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    url = "https://maps.google.com/?q=" + "a" * 2048
    resp = await _post(client, auth, inv, {**RECEPTION, "maps_url": url})
    assert _details(resp) == [("maps_url", "too_long")]


# ---------- Quy tắc nhiều cột (CHECK) ----------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # Lễ gia tiên luôn thuộc một bên
        ({"event_type": "family_ceremony", "host_side": "both"}, [("host_side", "invalid_choice")]),
        # other bắt buộc có tên; tên chỉ có khoảng trắng là null
        ({"event_type": "other", "host_side": "both"}, [("event_name", "required")]),
        (
            {"event_type": "other", "host_side": "groom", "event_name": None},
            [("event_name", "required")],
        ),
        (
            {"event_type": "other", "host_side": "bride", "event_name": "   "},
            [("event_name", "required")],
        ),
        # Giờ kết thúc cần giờ bắt đầu và phải sau giờ bắt đầu (không qua nửa đêm)
        ({**RECEPTION, "end_time": "22:00"}, [("start_time", "required")]),
        ({**RECEPTION, "start_time": "18:00", "end_time": "18:00"}, [("end_time", "out_of_range")]),
        ({**RECEPTION, "start_time": "18:00", "end_time": "17:59"}, [("end_time", "out_of_range")]),
        ({**RECEPTION, "start_time": "23:00", "end_time": "01:00"}, [("end_time", "out_of_range")]),
        # Tọa độ đủ cặp, trong khoảng cho phép
        ({**RECEPTION, "latitude": 21.028511}, [("longitude", "required")]),
        ({**RECEPTION, "longitude": 105.804817}, [("latitude", "required")]),
        ({**RECEPTION, "latitude": 90.000001, "longitude": 105}, [("latitude", "out_of_range")]),
        ({**RECEPTION, "latitude": -91, "longitude": 105}, [("latitude", "out_of_range")]),
        ({**RECEPTION, "latitude": 21, "longitude": 180.5}, [("longitude", "out_of_range")]),
        ({**RECEPTION, "latitude": 21, "longitude": -181}, [("longitude", "out_of_range")]),
        # Nhiều quy tắc sai cùng lúc thì báo đủ
        (
            {"event_type": "family_ceremony", "host_side": "both", "end_time": "10:00"},
            [("host_side", "invalid_choice"), ("start_time", "required")],
        ),
    ],
)
async def test_create_checks_multi_column_rules(
    client: AsyncClient, templates, auth, body: dict, expected: list
) -> None:
    inv = await _invitation(client, auth)
    resp = await _post(client, auth, inv, body)
    assert _details(resp) == expected
    assert _error_code(resp) == "validation_error"
    assert await _list(client, auth, inv) == []
    assert await _revision(client, auth, inv) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"event_type": "family_ceremony", "host_side": "groom"},
        {"event_type": "family_ceremony", "host_side": "bride"},
        {"event_type": "other", "host_side": "both", "event_name": "Tiệc độc thân"},
        {**RECEPTION, "start_time": "18:00"},
        {**RECEPTION, "start_time": "18:00", "end_time": "18:01"},
        {**RECEPTION, "start_time": "00:00", "end_time": "23:59"},
        {**RECEPTION, "latitude": 90, "longitude": -180},
    ],
)
async def test_create_accepts_valid_combinations(
    client: AsyncClient, templates, auth, body: dict
) -> None:
    inv = await _invitation(client, auth)
    created = await _post_ok(client, auth, inv, body)
    assert {k: created[k] for k in body} == body


async def test_patch_checks_rules_on_merged_event(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    reception = await _post_ok(
        client,
        auth,
        inv,
        {**RECEPTION, "start_time": "18:00", "end_time": "21:00", "latitude": 21, "longitude": 105},
    )
    other = await _post_ok(
        client, auth, inv, {"event_type": "other", "host_side": "both", "event_name": "Rước dâu"}
    )
    revision = await _revision(client, auth, inv)

    # Lỗi nằm ở trường phụ thuộc, kể cả khi trường đó không được gửi
    cases = [
        (reception, {"event_type": "family_ceremony"}, [("host_side", "invalid_choice")]),
        (other, {"event_name": None}, [("event_name", "required")]),
        (other, {"event_name": " "}, [("event_name", "required")]),
        (reception, {"start_time": None}, [("start_time", "required")]),
        (reception, {"end_time": "17:00"}, [("end_time", "out_of_range")]),
        (reception, {"start_time": "21:30"}, [("end_time", "out_of_range")]),
        (reception, {"latitude": None}, [("latitude", "required")]),
        (reception, {"longitude": None}, [("longitude", "required")]),
        (reception, {"latitude": 95}, [("latitude", "out_of_range")]),
    ]
    for event, body, expected in cases:
        resp = await _patch(client, auth, inv, event, body)
        assert _details(resp) == expected, body

    assert await _revision(client, auth, inv) == revision
    assert await _list(client, auth, inv) == [reception, other]

    # Sửa đủ các trường liên quan cùng lúc thì hợp lệ
    family = await _patch_ok(
        client, auth, inv, reception, {"event_type": "family_ceremony", "host_side": "bride"}
    )
    assert family["display_name"] == "Lễ vu quy"
    cleared_fields = {"start_time": None, "end_time": None, "latitude": None, "longitude": None}
    cleared = await _patch_ok(client, auth, inv, reception, cleared_fields)
    assert (cleared["start_time"], cleared["end_time"]) == (None, None)
    assert (cleared["latitude"], cleared["longitude"]) == (None, None)
    renamed = await _patch_ok(client, auth, inv, other, {"event_type": "reception"})
    assert renamed["display_name"] == "Rước dâu"


# ---------- Tên mặc định ----------


def test_default_name_table_covers_every_cell() -> None:
    assert {(t, s) for t, s, _ in DEFAULT_NAMES} == {(t, s) for t in EventType for s in HostSide}


@pytest.mark.parametrize(("event_type", "host_side", "expected"), DEFAULT_NAMES)
def test_default_event_name(event_type: str, host_side: str, expected: str | None) -> None:
    assert default_event_name(EventType(event_type), HostSide(host_side)) == expected


async def test_display_name_via_api(client: AsyncClient, templates, auth) -> None:
    valid = [(t, s, name) for t, s, name in DEFAULT_NAMES if name is not None]
    assert len(valid) == 11  # quá giới hạn 10 sự kiện của một thiệp: chia cho hai thiệp
    for chunk in (valid[:6], valid[6:]):
        inv = await _invitation(client, auth)
        for event_type, host_side, _ in chunk:
            await _post_ok(client, auth, inv, {"event_type": event_type, "host_side": host_side})
        events = await _list(client, auth, inv)
        assert [(e["event_type"], e["host_side"], e["display_name"]) for e in events] == chunk
        assert all(e["event_name"] is None for e in events)

    # event_name có giá trị thì thay tên mặc định; xoá thì quay về tên mặc định
    first = events[0]
    named = await _patch_ok(client, auth, inv, first, {"event_name": "Lễ dạm ngõ"})
    assert (named["event_name"], named["display_name"]) == ("Lễ dạm ngõ", "Lễ dạm ngõ")
    unnamed = await _patch_ok(client, auth, inv, first, {"event_name": None})
    assert (unnamed["event_name"], unnamed["display_name"]) == (None, chunk[0][2])


# ---------- Thứ tự hiển thị ----------


async def test_events_are_listed_in_display_order(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    created = {
        "A": {"event_date": "2026-12-20", "start_time": "18:00"},
        "B": {"start_time": "08:00"},
        "C": {"event_date": "2026-12-20", "start_time": "10:00"},
        "D": {"event_date": "2026-12-18"},
        "E": {"event_date": "2026-12-20"},
        "F": {"event_date": "2026-12-20", "start_time": "10:00"},
        "G": {},
    }
    for name, fields in created.items():
        body = {"event_type": "other", "host_side": "both", "event_name": name, **fields}
        await _post_ok(client, auth, inv, body)

    events = await _list(client, auth, inv)
    # Ngày, rồi giờ, rồi position; chưa có ngày xếp cuối, chưa có giờ xếp cuối trong ngày
    assert [e["event_name"] for e in events] == ["D", "C", "F", "A", "E", "B", "G"]
    assert {e["event_name"]: e["position"] for e in events} == {
        "A": 0,
        "B": 1,
        "C": 2,
        "D": 3,
        "E": 4,
        "F": 5,
        "G": 6,
    }

    # Đổi ngày thì thứ tự đổi theo, position giữ nguyên
    g = next(e for e in events if e["event_name"] == "G")
    await _patch_ok(client, auth, inv, g, {"event_date": "2026-12-01"})
    events = await _list(client, auth, inv)
    assert [e["event_name"] for e in events] == ["G", "D", "C", "F", "A", "E", "B"]
    assert events[0]["position"] == 6


async def test_delete_renumbers_positions(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    a, b, c = [
        await _post_ok(client, auth, inv, {**RECEPTION, "event_name": name})
        for name in ("A", "B", "C")
    ]
    assert [a["position"], b["position"], c["position"]] == [0, 1, 2]

    resp = await _delete(client, auth, inv, b)
    assert resp.status_code == 204
    assert resp.content == b""
    assert resp.headers["etag"] == '"5"'

    events = await _list(client, auth, inv)
    assert [(e["event_name"], e["position"]) for e in events] == [("A", 0), ("C", 1)]
    d = await _post_ok(client, auth, inv, {**RECEPTION, "event_name": "D"})
    assert d["position"] == 2


# ---------- Merge Patch ----------


async def test_patch_keeps_fields_not_sent_and_null_clears(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _invitation(client, auth)
    event = await _post_ok(client, auth, inv, FULL_EVENT)

    venue = await _patch_ok(client, auth, inv, event, {"venue_name": "Nhà văn hóa thôn"})
    assert venue == {**event, "venue_name": "Nhà văn hóa thôn", "updated_at": venue["updated_at"]}
    assert venue["updated_at"] != event["updated_at"]

    cleared = await _patch_ok(
        client,
        auth,
        inv,
        event,
        {
            "event_date": None,
            "end_time": None,
            "venue_name": "",
            "address": None,
            "latitude": None,
            "longitude": None,
            "maps_url": None,
        },
    )
    for field in ("event_date", "end_time", "venue_name", "address", "latitude", "longitude"):
        assert cleared[field] is None, field
    assert cleared["maps_url"] is None
    assert cleared["start_time"] == "09:00"
    assert cleared["timezone"] == "Asia/Ho_Chi_Minh"


@pytest.mark.parametrize("field", ["event_type", "host_side", "timezone"])
async def test_patch_null_on_required_field_is_required(
    client: AsyncClient, templates, auth, field: str
) -> None:
    inv = await _invitation(client, auth)
    event = await _post_ok(client, auth, inv, RECEPTION)
    assert _details(await _patch(client, auth, inv, event, {field: None})) == [(field, "required")]


async def test_patch_rejects_unknown_and_invalid_fields(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _invitation(client, auth)
    event = await _post_ok(client, auth, inv, RECEPTION)
    resp = await _patch(
        client,
        auth,
        inv,
        event,
        {"position": 3, "start_time": "7:00", "timezone": "UTC+7", "maps_url": "ftp://x.vn"},
    )
    assert _details(resp) == [
        ("start_time", "invalid_format"),
        ("timezone", "invalid_choice"),
        ("maps_url", "invalid_format"),
        ("position", "unknown_field"),
    ]
    assert await _list(client, auth, inv) == [event]


async def test_patch_accepts_merge_patch_content_type(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    event = await _post_ok(client, auth, inv, RECEPTION)
    headers = {
        **auth,
        "If-Match": await _etag(client, auth, inv),
        "Content-Type": "application/merge-patch+json",
    }
    resp = await client.patch(
        _url(inv, event), content=json.dumps({"venue_name": "Nhà hàng ABC"}), headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["venue_name"] == "Nhà hàng ABC"


# ---------- revision, ETag, If-Match ----------


async def test_event_writes_bump_invitation_revision(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)

    created = await _post(client, auth, inv, RECEPTION)
    assert created.headers["etag"] == '"2"'
    event = created.json()
    invitation = await client.get(f"/invitations/{inv['id']}", headers=auth)
    assert invitation.headers["etag"] == '"2"'
    assert invitation.json()["revision"] == 2
    assert invitation.json()["updated_at"] != inv["updated_at"]

    patched = await _patch(client, auth, inv, event, {"venue_name": "Nhà hàng ABC"})
    assert patched.headers["etag"] == '"3"'

    # Không có giá trị nào đổi: không ghi, revision và updated_at giữ nguyên
    unchanged = await _patch(
        client, auth, inv, event, {"venue_name": " Nhà hàng  ABC ", "host_side": "both"}
    )
    assert unchanged.status_code == 200
    assert unchanged.headers["etag"] == '"3"'
    assert unchanged.json() == patched.json()
    assert (await _patch(client, auth, inv, event, {})).headers["etag"] == '"3"'

    deleted = await _delete(client, auth, inv, event)
    assert deleted.headers["etag"] == '"4"'
    assert await _revision(client, auth, inv) == 4

    # Revision dùng chung với thiệp: PATCH thiệp bằng revision cũ bị từ chối
    stale = await client.patch(
        f"/invitations/{inv['id']}", json={"title": "Mới"}, headers={**auth, "If-Match": '"3"'}
    )
    assert stale.status_code == 409
    assert stale.headers["etag"] == '"4"'


async def test_writes_without_if_match_are_428(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    event = await _post_ok(client, auth, inv, RECEPTION)

    responses = [
        await client.post(_url(inv), json=RECEPTION, headers=auth),
        await client.patch(_url(inv, event), json={"venue_name": "X"}, headers=auth),
        await client.delete(_url(inv, event), headers=auth),
        # Thiếu If-Match thì 428 trước lỗi body
        await client.post(_url(inv), json={"x": 1}, headers=auth),
    ]
    for resp in responses:
        assert resp.status_code == 428, resp.request
        assert _error_code(resp) == "revision_required"
    assert await _list(client, auth, inv) == [event]

    # Chưa đăng nhập thì 401 trước 428
    assert (await client.post(_url(inv), json=RECEPTION)).status_code == 401
    assert (await client.get(_url(inv))).status_code == 401


async def test_writes_with_stale_revision_are_409(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    event = await _post_ok(client, auth, inv, RECEPTION)  # revision 2

    responses = [
        await _post(client, auth, inv, RECEPTION, if_match='"1"'),
        await _patch(client, auth, inv, event, {"venue_name": "X"}, if_match='"1"'),
        await _delete(client, auth, inv, event, if_match='"1"'),
        await _post(client, auth, inv, RECEPTION, if_match="2"),
        await _post(client, auth, inv, RECEPTION, if_match='W/"2"'),
        # revision kiểm tra trước sự kiện có tồn tại hay không
        await _patch(client, auth, inv, str(uuid.uuid4()), {"venue_name": "X"}, if_match='"1"'),
    ]
    for resp in responses:
        assert resp.status_code == 409, resp.request
        assert _error_code(resp) == "revision_conflict"
        assert resp.headers["etag"] == '"2"'
    assert await _list(client, auth, inv) == [event]


async def test_concurrent_writes_with_same_revision(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    headers = {**auth, "If-Match": '"1"'}
    responses = await asyncio.gather(
        client.post(_url(inv), json=RECEPTION, headers=headers),
        client.post(_url(inv), json=RECEPTION, headers=headers),
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len(await _list(client, auth, inv)) == 1
    assert await _revision(client, auth, inv) == 2


# ---------- Giới hạn 10 sự kiện ----------


async def test_event_limit(client: AsyncClient, templates, auth) -> None:
    assert settings.max_events_per_invitation == 10
    inv = await _invitation(client, auth)
    for _ in range(10):
        await _post_ok(client, auth, inv, RECEPTION)

    resp = await _post(client, auth, inv, RECEPTION)
    assert resp.status_code == 400
    assert _error_code(resp) == "event_limit"
    assert len(await _list(client, auth, inv)) == 10
    assert await _revision(client, auth, inv) == 11

    # Xoá bớt thì tạo lại được
    first = (await _list(client, auth, inv))[0]
    assert (await _delete(client, auth, inv, first)).status_code == 204
    await _post_ok(client, auth, inv, RECEPTION)


async def test_concurrent_creates_do_not_exceed_limit(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    for _ in range(9):
        await _post_ok(client, auth, inv, RECEPTION)

    headers = {**auth, "If-Match": await _etag(client, auth, inv)}
    responses = await asyncio.gather(
        *(client.post(_url(inv), json=RECEPTION, headers=headers) for _ in range(3))
    )
    assert sorted(r.status_code for r in responses) == [201, 409, 409]
    assert len(await _list(client, auth, inv)) == 10
    retry = await _post(client, auth, inv, RECEPTION)
    assert retry.status_code == 400 and _error_code(retry) == "event_limit"


# ---------- Quyền, 404 ----------


async def test_other_user_cannot_access_events(
    client: AsyncClient, templates, auth, other_auth
) -> None:
    inv = await _invitation(client, auth)
    event = await _post_ok(client, auth, inv, RECEPTION)
    headers = {**other_auth, "If-Match": '"2"'}

    responses = [
        await client.get(_url(inv), headers=other_auth),
        await client.post(_url(inv), json=RECEPTION, headers=headers),
        await client.patch(_url(inv, event), json={"venue_name": "X"}, headers=headers),
        await client.delete(_url(inv, event), headers=headers),
    ]
    for resp in responses:
        assert resp.status_code == 404
        assert _error_code(resp) == "invitation_not_found"
    assert await _list(client, auth, inv) == [event]


async def test_event_of_another_invitation_is_404(client: AsyncClient, templates, auth) -> None:
    first = await _invitation(client, auth)
    second = await _invitation(client, auth)
    event = await _post_ok(client, auth, first, RECEPTION)

    for resp in [
        await _patch(client, auth, second, event, {"venue_name": "X"}),
        await _delete(client, auth, second, event),
        await _patch(client, auth, first, str(uuid.uuid4()), {"venue_name": "X"}),
        await _delete(client, auth, first, str(uuid.uuid4())),
    ]:
        assert resp.status_code == 404
        assert _error_code(resp) == "event_not_found"
    assert await _revision(client, auth, first) == 2
    assert await _revision(client, auth, second) == 1
    assert await _list(client, auth, first) == [event]


async def test_deleting_invitation_deletes_events(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    await _post_ok(client, auth, inv, RECEPTION)
    assert (await client.delete(f"/invitations/{inv['id']}", headers=auth)).status_code == 204
    assert (await client.get(_url(inv), headers=auth)).status_code == 404


# ---------- Ngày chính của thiệp, revalidate ----------


async def test_primary_event_date_follows_events(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)

    async def primary_date() -> str | None:
        resp = await client.get(f"/invitations/{inv['id']}", headers=auth)
        return resp.json()["primary_event_date"]

    late = await _post_ok(client, auth, inv, {**RECEPTION, "event_date": "2026-12-20"})
    early = await _post_ok(client, auth, inv, {**RECEPTION, "event_date": "2026-12-18"})
    await _post_ok(client, auth, inv, RECEPTION)
    assert await primary_date() == "2026-12-18"

    await _patch_ok(client, auth, inv, late, {"event_date": "2026-12-01"})
    assert await primary_date() == "2026-12-01"
    await _delete(client, auth, inv, late)
    assert await primary_date() == "2026-12-18"
    await _patch_ok(client, auth, inv, early, {"event_date": None})
    assert await primary_date() is None


async def test_event_writes_revalidate_published_invitation(
    client: AsyncClient, templates, auth, monkeypatch
) -> None:
    calls: list[tuple[str, ...]] = []

    async def record(*slugs: str) -> None:
        calls.append(slugs)

    monkeypatch.setattr(events_router, "revalidate_invitation", record)
    draft = await _invitation(client, auth, slug="thiep-nhap")
    await _post_ok(client, auth, draft, RECEPTION)
    assert calls == []

    inv = await _invitation(client, auth, content=NAMES, slug="nam-lan")
    await _post_ok(client, auth, inv, FULL_EVENT)
    assert calls == []  # thiệp còn nháp: không revalidate
    published = await client.post(f"/invitations/{inv['id']}/publish", headers=auth)
    assert published.status_code == 200, published.text
    assert calls == []  # webhook của publish gửi từ router thiệp, không phải router này

    # Thiệp đã publish: sự kiện mới phải đủ ngày, giờ, địa chỉ (tests/test_publish.py)
    event = await _post_ok(client, auth, inv, FULL_EVENT)
    await _patch_ok(client, auth, inv, event, {"venue_name": "Nhà hàng ABC"})
    await _patch_ok(client, auth, inv, event, {"venue_name": "Nhà hàng ABC"})  # không đổi gì
    await _delete(client, auth, inv, event)
    await _post(client, auth, inv, RECEPTION, if_match='"1"')  # 409, không ghi
    assert calls == [("nam-lan",), ("nam-lan",), ("nam-lan",)]


# ---------- OpenAPI ----------


async def test_openapi_has_event_schemas(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    schemas = spec["components"]["schemas"]
    assert {"EventCreate", "EventUpdate"} <= set(schemas)
    assert any(name.startswith("EventResponse") for name in schemas)
    fields = set(FULL_EVENT)
    assert set(schemas["EventCreate"]["properties"]) == fields
    assert set(schemas["EventUpdate"]["properties"]) == fields
    assert sorted(schemas["EventCreate"]["required"]) == ["event_type", "host_side"]
    assert "required" not in schemas["EventUpdate"]

    paths = spec["paths"]
    assert set(paths["/invitations/{invitation_id}/events"]) == {"get", "post"}
    assert set(paths["/invitations/{invitation_id}/events/{event_id}"]) == {"patch", "delete"}
