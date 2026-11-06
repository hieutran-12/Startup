"""Publish: điều kiện publish (`not_ready_to_publish`) và giữ điều kiện sau khi publish
(`breaks_published_invitation`).

Spec Bước 6: 04 › Publish; 03 › Nội dung thiệp, events; 05 › Định dạng lỗi. 8 đề xuất được duyệt
2026-11-06 (docs/modules/invitations.md): mọi dòng details mã `required`; `events[i]` theo thứ tự
hiển thị của trạng thái sau khi sửa; kiểm tra sau mọi lỗi 422, 409 slug, 400 event_limit.
"""

import asyncio
from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.merge_patch import merge_patch
from app.models import Template
from app.modules.events import router as events_router
from app.modules.invitations import router as invitations_router
from tests.conftest import make_manifest

NAMES = {
    "couple": {
        "groom": {"full_name": "Nguyễn Văn Nam", "display_name": "Nam"},
        "bride": {"full_name": "Lê Thị Lan", "display_name": "Lan"},
    }
}

READY_EVENT = {
    "event_type": "reception",
    "host_side": "both",
    "event_date": "2026-12-20",
    "start_time": "11:00",
    "address": "Nhà hàng ABC, 12 Láng Hạ, Hà Nội",
}

GIFT = {
    "recipient_side": "bride",
    "bank_bin": "970436",
    "account_number": "0123456789",
    "account_holder": "LE THI LAN",
}

MESSAGES = {
    "content.couple.groom.full_name": "Cần nhập họ tên chú rể",
    "content.couple.bride.full_name": "Cần nhập họ tên cô dâu",
    "events": "Cần có ít nhất một sự kiện",
}
EVENT_MESSAGES = {
    "event_date": "Cần nhập ngày tổ chức",
    "start_time": "Cần nhập giờ bắt đầu",
    "address": "Cần nhập địa chỉ",
}

SECTIONS = ("content.appearance.sections", "required")


# ---------- Helper ----------


async def _invitation(client: AsyncClient, auth: dict, **payload: Any) -> dict:
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", **payload}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _get(client: AsyncClient, auth: dict, inv: dict) -> dict:
    resp = await client.get(f"/invitations/{inv['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _if_match(client: AsyncClient, auth: dict, inv: dict) -> dict:
    return {**auth, "If-Match": f'"{(await _get(client, auth, inv))["revision"]}"'}


async def _patch(client: AsyncClient, auth: dict, inv: dict, body: Any) -> Response:
    headers = await _if_match(client, auth, inv)
    return await client.patch(f"/invitations/{inv['id']}", json=body, headers=headers)


def _events_url(inv: dict, event: dict | None = None) -> str:
    url = f"/invitations/{inv['id']}/events"
    return url if event is None else f"{url}/{event['id']}"


async def _post_event(client: AsyncClient, auth: dict, inv: dict, body: Any) -> Response:
    headers = await _if_match(client, auth, inv)
    return await client.post(_events_url(inv), json=body, headers=headers)


async def _add_event(client: AsyncClient, auth: dict, inv: dict, body: Any) -> dict:
    resp = await _post_event(client, auth, inv, body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _patch_event(
    client: AsyncClient, auth: dict, inv: dict, event: dict, body: Any
) -> Response:
    headers = await _if_match(client, auth, inv)
    return await client.patch(_events_url(inv, event), json=body, headers=headers)


async def _delete_event(client: AsyncClient, auth: dict, inv: dict, event: dict) -> Response:
    headers = await _if_match(client, auth, inv)
    return await client.delete(_events_url(inv, event), headers=headers)


async def _events(client: AsyncClient, auth: dict, inv: dict) -> list[dict]:
    resp = await client.get(_events_url(inv), headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _publish(client: AsyncClient, auth: dict, inv: dict) -> Response:
    return await client.post(f"/invitations/{inv['id']}/publish", headers=auth)


async def _ready(client: AsyncClient, auth: dict, **payload: Any) -> dict:
    """Thiệp nháp đủ điều kiện publish: tên hai bên, một sự kiện đủ ngày giờ địa chỉ."""
    inv = await _invitation(client, auth, content=NAMES, **payload)
    await _add_event(client, auth, inv, READY_EVENT)
    return await _get(client, auth, inv)


async def _published(client: AsyncClient, auth: dict, **payload: Any) -> dict:
    inv = await _ready(client, auth, **payload)
    resp = await _publish(client, auth, inv)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _error(resp: Response, code: str) -> list[tuple[str, str]]:
    """Lỗi 400 mã `code`; trả (field, code) của từng dòng details."""
    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == code
    return [(d["field"], d["code"]) for d in error["details"]]


def _messages(resp: Response) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for detail in resp.json()["error"]["details"]:
        result.setdefault(detail["field"], []).append(detail["message"])
    return result


@pytest.fixture
def revalidated(monkeypatch) -> list[tuple[str, ...]]:
    """Ghi lại các lần gọi webhook revalidate từ router thiệp và router sự kiện."""
    calls: list[tuple[str, ...]] = []

    async def record(*slugs: str) -> None:
        calls.append(slugs)

    monkeypatch.setattr(invitations_router, "revalidate_invitation", record)
    monkeypatch.setattr(events_router, "revalidate_invitation", record)
    return calls


@pytest.fixture
async def no_events_template(session_maker: async_sessionmaker, templates) -> Template:
    """Mẫu không hỗ trợ section events: đổi sang mẫu này thì appearance mất events."""
    template = Template(
        key="no_events_01",
        name="Không có sự kiện",
        category="modern",
        manifest=make_manifest(
            sections=["cover", "couple", "gallery"], default_sections=["cover", "couple"]
        ),
    )
    async with session_maker() as db:
        db.add(template)
        await db.commit()
    return template


# ---------- Publish: điều kiện ----------


async def test_publish_ready_invitation(client: AsyncClient, templates, auth, revalidated) -> None:
    inv = await _ready(client, auth, slug="nam-lan")
    assert (await client.get("/public/invitations/nam-lan")).status_code == 404

    resp = await _publish(client, auth, inv)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None
    assert body["revision"] == inv["revision"]  # publish không tăng revision
    assert resp.headers["etag"] == f'"{inv["revision"]}"'
    assert revalidated == [("nam-lan",)]
    assert (await client.get("/public/invitations/nam-lan")).status_code == 200


MISSING_CASES: dict[str, tuple[dict, list[dict], list[tuple[str, str]]]] = {
    "groom_name": (
        {"couple": {"groom": {"full_name": None}}},
        [READY_EVENT],
        [("content.couple.groom.full_name", "required")],
    ),
    "bride_name": (
        {"couple": {"bride": {"full_name": None}}},
        [READY_EVENT],
        [("content.couple.bride.full_name", "required")],
    ),
    "no_event": ({}, [], [("events", "required")]),
    "event_date": (
        {},
        [{**READY_EVENT, "event_date": None}],
        [("events[0].event_date", "required")],
    ),
    "start_time": (
        {},
        [{**READY_EVENT, "start_time": None}],
        [("events[0].start_time", "required")],
    ),
    "address": ({}, [{**READY_EVENT, "address": None}], [("events[0].address", "required")]),
    "cover_section": (
        {"appearance": {"sections": ["couple", "events"]}},
        [READY_EVENT],
        [SECTIONS],
    ),
    "events_section": (
        {"appearance": {"sections": ["cover", "couple"]}},
        [READY_EVENT],
        [SECTIONS],
    ),
}


@pytest.mark.parametrize("case", MISSING_CASES)
async def test_each_missing_condition_is_in_details(
    client: AsyncClient, templates, auth, case: str
) -> None:
    content_patch, events, expected = MISSING_CASES[case]
    inv = await _invitation(client, auth, content=merge_patch(NAMES, content_patch))
    for event in events:
        await _add_event(client, auth, inv, event)

    resp = await _publish(client, auth, inv)
    assert _error(resp, "not_ready_to_publish") == expected
    assert (await _get(client, auth, inv))["status"] == "draft"


@pytest.mark.parametrize(
    ("sections", "missing"),
    [(["couple", "events"], "cover"), (["cover", "couple"], "events")],
)
async def test_missing_section_message_names_the_section(
    client: AsyncClient, templates, auth, sections: list[str], missing: str
) -> None:
    content = merge_patch(NAMES, {"appearance": {"sections": sections}})
    inv = await _invitation(client, auth, content=content)
    await _add_event(client, auth, inv, READY_EVENT)
    resp = await _publish(client, auth, inv)
    [message] = _messages(resp)["content.appearance.sections"]
    assert f"({missing})" in message


async def test_all_missing_conditions_in_spec_order(
    client: AsyncClient, templates, auth, revalidated
) -> None:
    # Không tên, sections thiếu cả cover lẫn events
    inv = await _invitation(client, auth, content={"appearance": {"sections": ["couple"]}})
    # Tạo theo thứ tự B, C, A; thứ tự hiển thị là A (20/12), C (21/12), B (chưa có ngày)
    await _add_event(client, auth, inv, {"event_type": "engagement", "host_side": "bride"})
    await _add_event(
        client,
        auth,
        inv,
        {**READY_EVENT, "event_date": "2026-12-21", "start_time": "18:00", "address": None},
    )
    await _add_event(client, auth, inv, READY_EVENT)
    before = await _get(client, auth, inv)

    resp = await _publish(client, auth, inv)
    assert resp.json()["error"]["message"] == "Thiệp chưa đủ thông tin để đăng"
    assert _error(resp, "not_ready_to_publish") == [
        ("content.couple.groom.full_name", "required"),
        ("content.couple.bride.full_name", "required"),
        ("events[1].address", "required"),
        ("events[2].event_date", "required"),
        ("events[2].start_time", "required"),
        ("events[2].address", "required"),
        SECTIONS,
        SECTIONS,
    ]
    messages = _messages(resp)
    for side in ("groom", "bride"):
        field = f"content.couple.{side}.full_name"
        assert messages[field] == [MESSAGES[field]]
    for field, message in EVENT_MESSAGES.items():
        assert messages[f"events[2].{field}"] == [message]
    assert ["(cover)" in m for m in messages["content.appearance.sections"]] == [True, False]
    assert ["(events)" in m for m in messages["content.appearance.sections"]] == [False, True]

    # Không ghi gì, không revalidate
    after = await _get(client, auth, inv)
    assert after == before
    assert revalidated == []


async def test_no_event_message(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth, content=NAMES)
    resp = await _publish(client, auth, inv)
    assert _messages(resp) == {"events": [MESSAGES["events"]]}


async def test_republish_published_invitation(client: AsyncClient, templates, auth) -> None:
    """Giữ như khung: publish lại vẫn kiểm tra điều kiện và đặt lại published_at."""
    inv = await _published(client, auth)
    again = await _publish(client, auth, inv)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "published"
    published_at = datetime.fromisoformat(again.json()["published_at"])
    assert published_at >= datetime.fromisoformat(inv["published_at"])
    assert again.json()["revision"] == inv["revision"]


# ---------- Thiệp đã publish: sửa thiệp ----------

BREAKING_PATCHES: dict[str, tuple[dict, list[tuple[str, str]]]] = {
    "bride_name_null": (
        {"content": {"couple": {"bride": {"full_name": None}}}},
        [("content.couple.bride.full_name", "required")],
    ),
    "bride_name_blank": (
        {"content": {"couple": {"bride": {"full_name": "   "}}}},
        [("content.couple.bride.full_name", "required")],
    ),
    "groom_name_null": (
        {"content": {"couple": {"groom": {"full_name": None}}}},
        [("content.couple.groom.full_name", "required")],
    ),
    "drop_cover": ({"content": {"appearance": {"sections": ["couple", "events"]}}}, [SECTIONS]),
    "drop_events": ({"content": {"appearance": {"sections": ["cover"]}}}, [SECTIONS]),
    "several": (
        {
            "title": "Đổi tên nội bộ",
            "content": {
                "couple": {"groom": {"full_name": None}, "bride": {"full_name": None}},
                "appearance": {"sections": ["couple"]},
            },
        },
        [
            ("content.couple.groom.full_name", "required"),
            ("content.couple.bride.full_name", "required"),
            SECTIONS,
            SECTIONS,
        ],
    ),
}


@pytest.mark.parametrize("case", BREAKING_PATCHES)
async def test_patch_breaking_published_invitation_is_rejected(
    client: AsyncClient, templates, auth, revalidated, case: str
) -> None:
    body, expected = BREAKING_PATCHES[case]
    inv = await _published(client, auth)
    revalidated.clear()

    resp = await _patch(client, auth, inv, body)
    assert resp.json()["error"]["message"] == "Thiệp đang đăng phải giữ đủ thông tin bắt buộc"
    assert _error(resp, "breaks_published_invitation") == expected
    assert "etag" not in resp.headers

    after = await _get(client, auth, inv)
    assert after == inv  # không ghi: revision, title, content, updated_at giữ nguyên
    assert revalidated == []


async def test_bride_name_message_on_breaking_patch(client: AsyncClient, templates, auth) -> None:
    inv = await _published(client, auth)
    resp = await _patch(client, auth, inv, {"content": {"couple": {"bride": {"full_name": None}}}})
    assert _messages(resp) == {
        "content.couple.bride.full_name": [MESSAGES["content.couple.bride.full_name"]]
    }


async def test_template_change_dropping_events_section_is_rejected(
    client: AsyncClient, templates, no_events_template, auth
) -> None:
    inv = await _published(client, auth)
    resp = await _patch(client, auth, inv, {"template_key": "no_events_01"})
    assert _error(resp, "breaks_published_invitation") == [SECTIONS]
    assert "(events)" in _messages(resp)["content.appearance.sections"][0]
    assert await _get(client, auth, inv) == inv

    # Thiệp nháp thì vẫn đổi được, appearance tự chỉnh, không báo lỗi (04 › Đổi template)
    draft = await _ready(client, auth)
    changed = await _patch(client, auth, draft, {"template_key": "no_events_01"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["content"]["appearance"]["sections"] == ["cover", "couple"]


async def test_template_change_keeping_conditions_is_allowed(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _published(client, auth)
    resp = await _patch(client, auth, inv, {"template_key": "minimal_01"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["content"]["appearance"]["sections"] == ["cover", "events"]
    assert resp.json()["status"] == "published"


async def test_validation_error_comes_before_breaks(client: AsyncClient, templates, auth) -> None:
    inv = await _published(client, auth)
    body = {
        "content": {
            "couple": {"bride": {"full_name": None}},
            "appearance": {"palette_key": "khong_co"},
        }
    }
    resp = await _patch(client, auth, inv, body)
    assert resp.status_code == 422, resp.text
    details = [(d["field"], d["code"]) for d in resp.json()["error"]["details"]]
    assert details == [("content.appearance.palette_key", "invalid_choice")]


async def test_slug_conflict_comes_before_breaks(client: AsyncClient, templates, auth) -> None:
    await _invitation(client, auth, slug="da-co-nguoi")
    inv = await _published(client, auth)
    body = {"slug": "da-co-nguoi", "content": {"couple": {"bride": {"full_name": None}}}}
    resp = await _patch(client, auth, inv, body)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "slug_taken"


async def test_published_invitation_accepts_edits_keeping_conditions(
    client: AsyncClient, templates, auth, revalidated
) -> None:
    inv = await _published(client, auth, slug="nam-lan")
    revalidated.clear()
    body = {
        "title": "Thiệp chính",
        "content": {
            "couple": {"bride": {"full_name": "Lê Thị Ngọc Lan"}},
            "gifts": [GIFT],
            "appearance": {"sections": ["events", "couple", "cover"]},
        },
    }
    resp = await _patch(client, auth, inv, body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["revision"] == inv["revision"] + 1
    assert resp.json()["content"]["couple"]["bride"]["full_name"] == "Lê Thị Ngọc Lan"
    assert revalidated == [("nam-lan",)]

    # PATCH không đổi gì vẫn 200 như trước
    same = await _patch(client, auth, inv, body)
    assert same.status_code == 200, same.text
    assert same.json()["revision"] == inv["revision"] + 1


# ---------- Thiệp đã publish: ghi sự kiện ----------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {**READY_EVENT, "event_date": "2026-12-21", "address": None},
            [("events[1].address", "required")],
        ),
        (
            # Chưa có ngày nên xếp cuối
            {"event_type": "engagement", "host_side": "groom"},
            [
                ("events[1].event_date", "required"),
                ("events[1].start_time", "required"),
                ("events[1].address", "required"),
            ],
        ),
        (
            # Ngày sớm hơn nên xếp đầu
            {**READY_EVENT, "event_date": "2026-12-18", "start_time": None},
            [("events[0].start_time", "required")],
        ),
    ],
)
async def test_create_incomplete_event_on_published_is_rejected(
    client: AsyncClient, templates, auth, revalidated, body: dict, expected: list
) -> None:
    inv = await _published(client, auth)
    events = await _events(client, auth, inv)
    revalidated.clear()

    resp = await _post_event(client, auth, inv, body)
    assert _error(resp, "breaks_published_invitation") == expected
    assert "etag" not in resp.headers
    assert await _events(client, auth, inv) == events
    assert await _get(client, auth, inv) == inv
    assert revalidated == []


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"start_time": None}, [("events[0].start_time", "required")]),
        ({"address": None}, [("events[0].address", "required")]),
        ({"address": "  "}, [("events[0].address", "required")]),
        # Xoá ngày thì sự kiện xếp cuối: đường dẫn theo thứ tự sau khi sửa
        ({"event_date": None}, [("events[1].event_date", "required")]),
    ],
)
async def test_patch_event_breaking_published_is_rejected(
    client: AsyncClient, templates, auth, revalidated, patch: dict, expected: list
) -> None:
    inv = await _published(client, auth)
    await _add_event(client, auth, inv, {**READY_EVENT, "event_date": "2026-12-21"})
    inv = await _get(client, auth, inv)
    events = await _events(client, auth, inv)
    revalidated.clear()

    resp = await _patch_event(client, auth, inv, events[0], patch)
    assert _error(resp, "breaks_published_invitation") == expected
    assert await _events(client, auth, inv) == events
    assert await _get(client, auth, inv) == inv
    assert revalidated == []


async def test_delete_last_event_of_published_is_rejected(
    client: AsyncClient, templates, auth, revalidated
) -> None:
    inv = await _published(client, auth)
    [event] = await _events(client, auth, inv)
    revalidated.clear()

    resp = await _delete_event(client, auth, inv, event)
    assert _error(resp, "breaks_published_invitation") == [("events", "required")]
    assert _messages(resp) == {"events": [MESSAGES["events"]]}
    assert await _events(client, auth, inv) == [event]
    assert await _get(client, auth, inv) == inv
    assert revalidated == []


async def test_published_invitation_accepts_event_writes_keeping_conditions(
    client: AsyncClient, templates, auth, revalidated
) -> None:
    inv = await _published(client, auth, slug="nam-lan")
    revalidated.clear()
    second = await _add_event(
        client, auth, inv, {**READY_EVENT, "event_type": "family_ceremony", "host_side": "bride"}
    )
    patched = await _patch_event(client, auth, inv, second, {"venue_name": "Tư gia nhà gái"})
    assert patched.status_code == 200, patched.text
    first = (await _events(client, auth, inv))[0]
    assert (await _delete_event(client, auth, inv, first)).status_code == 204
    assert revalidated == [("nam-lan",)] * 3
    assert (await _get(client, auth, inv))["status"] == "published"
    assert [e["id"] for e in await _events(client, auth, inv)] == [second["id"]]


async def test_event_limit_comes_before_breaks(client: AsyncClient, templates, auth) -> None:
    inv = await _published(client, auth)
    for _ in range(9):
        await _add_event(client, auth, inv, READY_EVENT)
    resp = await _post_event(client, auth, inv, {"event_type": "other", "host_side": "both"})
    # Lỗi 422 (other bắt buộc có tên) đi trước giới hạn và điều kiện publish
    assert resp.status_code == 422, resp.text
    resp = await _post_event(client, auth, inv, {"event_type": "engagement", "host_side": "both"})
    assert _error(resp, "event_limit") == []


# ---------- Nháp, sau khi unpublish ----------


async def test_draft_accepts_edits_that_would_break_published(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _ready(client, auth)
    [event] = await _events(client, auth, inv)
    resp = await _patch(client, auth, inv, {"content": {"couple": {"bride": {"full_name": None}}}})
    assert resp.status_code == 200, resp.text
    resp = await _patch_event(client, auth, inv, event, {"address": None})
    assert resp.status_code == 200, resp.text
    assert (await _delete_event(client, auth, inv, event)).status_code == 204
    resp = await _post_event(client, auth, inv, {"event_type": "engagement", "host_side": "both"})
    assert resp.status_code == 201, resp.text


async def test_unpublished_invitation_accepts_breaking_edits(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _published(client, auth)
    unpublished = await client.post(f"/invitations/{inv['id']}/unpublish", headers=auth)
    assert unpublished.status_code == 200, unpublished.text
    [event] = await _events(client, auth, inv)
    assert (await _delete_event(client, auth, inv, event)).status_code == 204
    resp = await _patch(client, auth, inv, {"content": {"couple": {"groom": {"full_name": ""}}}})
    assert resp.status_code == 200, resp.text

    # Publish lại thì phải đủ điều kiện
    resp = await _publish(client, auth, inv)
    assert _error(resp, "not_ready_to_publish") == [
        ("content.couple.groom.full_name", "required"),
        ("events", "required"),
    ]


# ---------- Đồng thời ----------


async def test_concurrent_publish_and_delete_last_event(
    client: AsyncClient, templates, auth
) -> None:
    """Publish và xoá sự kiện cuối chạy song song: thiệp không bao giờ đăng mà không có sự kiện."""
    for _ in range(3):
        inv = await _ready(client, auth)
        [event] = await _events(client, auth, inv)
        headers = await _if_match(client, auth, inv)
        published, deleted = await asyncio.gather(
            _publish(client, auth, inv),
            client.delete(_events_url(inv, event), headers=headers),
        )
        state = await _get(client, auth, inv)
        events = await _events(client, auth, inv)
        if published.status_code == 200:
            assert _error(deleted, "breaks_published_invitation") == [("events", "required")]
            assert state["status"] == "published" and len(events) == 1
        else:
            assert deleted.status_code == 204, deleted.text
            assert _error(published, "not_ready_to_publish") == [("events", "required")]
            assert state["status"] == "draft" and events == []
        await client.delete(f"/invitations/{inv['id']}", headers=auth)
