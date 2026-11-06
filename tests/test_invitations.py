"""Thiệp: tạo, sửa (Merge Patch, revision, ETag, If-Match), đổi template, tham chiếu media.

Spec Bước 4: 04 › Tạo thiệp, Sửa thiệp, Đổi template, Tham chiếu media; 05 (response thiệp,
mã lỗi); 03 › invitations; 02 › NULL, rỗng và mặc định. 9 quy tắc phụ được duyệt 2026-11-06
(docs/modules/invitations.md). Fixture: classic_01 = make_manifest(), minimal_01 =
make_minimal_manifest() (tests/conftest.py).
"""

import asyncio
import copy
import json
import uuid
from datetime import date, time
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.modules.events.models import Event
from app.modules.media.models import Media
from tests.conftest import empty_content

CLASSIC_DEFAULT_SECTIONS = ["cover", "couple", "events"]

NAMES = {
    "couple": {
        "groom": {"full_name": "Nguyễn Văn Nam", "display_name": "Nam"},
        "bride": {"full_name": "Lê Thị Lan", "display_name": "Lan"},
    }
}

RESPONSE_FIELDS = {
    "id",
    "slug",
    "title",
    "status",
    "template_key",
    "content_schema_version",
    "revision",
    "content",
    "cover_media_id",
    "groom_photo_media_id",
    "bride_photo_media_id",
    "music_media_id",
    "primary_event_date",
    "published_at",
    "created_at",
    "updated_at",
}

GIFT = {
    "recipient_side": "groom",
    "bank_bin": "970436",
    "account_number": "0123456789",
    "account_holder": "NGUYEN VAN NAM",
}


# ---------- Helper ----------


async def _create(client: AsyncClient, auth: dict, **payload: Any) -> dict:
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", **payload}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _patch(
    client: AsyncClient, auth: dict, inv: dict, body: Any, *, revision: int | None = None
) -> Response:
    """PATCH với If-Match là revision của `inv` (hoặc `revision` nếu truyền vào)."""
    if_match = f'"{inv["revision"] if revision is None else revision}"'
    return await client.patch(
        f"/invitations/{inv['id']}", json=body, headers={**auth, "If-Match": if_match}
    )


async def _patch_ok(client: AsyncClient, auth: dict, inv: dict, body: Any) -> dict:
    resp = await _patch(client, auth, inv, body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _get(client: AsyncClient, auth: dict, inv: dict) -> dict:
    resp = await client.get(f"/invitations/{inv['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _details(resp: Response, status_code: int = 422) -> list[tuple[str, str]]:
    assert resp.status_code == status_code, resp.text
    return [(d["field"], d["code"]) for d in resp.json()["error"]["details"]]


def _error_code(resp: Response) -> str:
    return resp.json()["error"]["code"]


async def _add_media(
    session_maker: async_sessionmaker,
    invitation_id: str,
    *,
    kind: str = "image",
    status: str = "ready",
) -> str:
    """Ghi thẳng một file vào DB (upload âm thanh thuộc Bước 7)."""
    media_id = uuid.uuid4()
    async with session_maker() as db:
        db.add(
            Media(
                id=media_id,
                invitation_id=uuid.UUID(invitation_id),
                kind=kind,
                storage_key=f"invitations/{invitation_id}/{media_id}",
                mime_type="image/jpeg" if kind == "image" else "audio/mpeg",
                size_bytes=1000,
                status=status,
            )
        )
        await db.commit()
    return str(media_id)


async def _set_media_status(session_maker: async_sessionmaker, media_id: str, status: str) -> None:
    async with session_maker() as db:
        await db.execute(update(Media).where(Media.id == uuid.UUID(media_id)).values(status=status))
        await db.commit()


async def _add_ready_event(session_maker: async_sessionmaker, invitation_id: str) -> None:
    """Ghi thẳng một sự kiện đủ điều kiện publish vào DB (không tăng revision của thiệp)."""
    async with session_maker() as db:
        db.add(
            Event(
                invitation_id=uuid.UUID(invitation_id),
                event_type="reception",
                host_side="both",
                event_date=date(2026, 12, 20),
                start_time=time(11, 0),
                address="Nhà hàng ABC, Hà Nội",
            )
        )
        await db.commit()


# ---------- Template ----------


async def test_list_templates_hides_inactive(client: AsyncClient, templates) -> None:
    resp = await client.get("/templates")
    assert resp.status_code == 200
    keys = {t["key"] for t in resp.json()}
    assert keys == {"classic_01", "minimal_01", "vintage_01"}

    assert (await client.get("/templates/old_01")).status_code == 404
    classic = await client.get("/templates?category=classic")
    assert [t["key"] for t in classic.json()] == ["classic_01"]


# ---------- Tạo thiệp ----------


async def test_create_builds_full_default_content(client: AsyncClient, templates, auth) -> None:
    resp = await client.post("/invitations", json={"template_key": "classic_01"}, headers=auth)
    assert resp.status_code == 201, resp.text
    assert resp.headers["etag"] == '"1"'
    body = resp.json()
    assert set(body) == RESPONSE_FIELDS
    assert body["content"] == empty_content(CLASSIC_DEFAULT_SECTIONS)
    assert body["content_schema_version"] == 1
    assert body["revision"] == 1
    assert body["status"] == "draft"
    assert body["published_at"] is None
    assert body["primary_event_date"] is None
    assert body["template_key"] == "classic_01"
    for column in ("cover_media_id", "groom_photo_media_id", "bride_photo_media_id"):
        assert body[column] is None
    assert body["music_media_id"] is None
    assert body["slug"] == "thiep-cuoi"
    assert body["title"] == "Thiệp cưới của tôi"


async def test_create_merges_partial_content_onto_default(
    client: AsyncClient, templates, auth
) -> None:
    content = {**NAMES, "appearance": {"palette_key": "burgundy"}}
    body = await _create(client, auth, content=content)
    expected = empty_content(CLASSIC_DEFAULT_SECTIONS)
    expected["couple"]["groom"] = {
        **expected["couple"]["groom"],
        "full_name": "Nguyễn Văn Nam",
        "display_name": "Nam",
    }
    expected["couple"]["bride"] = {
        **expected["couple"]["bride"],
        "full_name": "Lê Thị Lan",
        "display_name": "Lan",
    }
    expected["appearance"]["palette_key"] = "burgundy"
    assert body["content"] == expected


async def test_create_can_choose_sections(client: AsyncClient, templates, auth) -> None:
    body = await _create(client, auth, content={"appearance": {"sections": ["events", "cover"]}})
    assert body["content"]["appearance"]["sections"] == ["events", "cover"]


async def test_create_generates_slug_and_title_from_names(
    client: AsyncClient, templates, auth
) -> None:
    first = await _create(client, auth, content=NAMES)
    assert first["slug"] == "nam-lan"
    assert first["title"] == "Nam & Lan"

    second = await _create(client, auth, content=NAMES)
    assert second["slug"].startswith("nam-lan-")
    assert second["slug"] != first["slug"]

    # Không có display_name thì dùng full_name
    full_names = {
        "couple": {"groom": {"full_name": "Trần Văn Hùng"}, "bride": {"full_name": "Đỗ Thị Mai"}}
    }
    third = await _create(client, auth, content=full_names)
    assert third["slug"] == "tran-van-hung-do-thi-mai"
    assert third["title"] == "Trần Văn Hùng & Đỗ Thị Mai"


async def test_create_with_custom_slug(client: AsyncClient, templates, auth, other_auth) -> None:
    created = await _create(client, auth, slug="  Nam-Lan-2026 ")
    assert created["slug"] == "nam-lan-2026"

    taken = await client.post(
        "/invitations",
        json={"template_key": "classic_01", "slug": "nam-lan-2026"},
        headers=other_auth,
    )
    assert taken.status_code == 409
    assert _error_code(taken) == "slug_taken"

    for bad in ["dashboard", "có-dấu", "a", "nam--lan", 123]:
        resp = await client.post(
            "/invitations", json={"template_key": "classic_01", "slug": bad}, headers=auth
        )
        assert _details(resp) == [("slug", "invalid_format")], bad

    # Bỏ trống (rỗng sau trim hoặc null) thì tự sinh
    blank = await _create(client, auth, slug="   ", content=NAMES)
    assert blank["slug"] == "nam-lan"
    assert (await _create(client, auth, slug=None))["slug"] == "thiep-cuoi"


async def test_create_title_is_single_line(client: AsyncClient, templates, auth) -> None:
    assert (await _create(client, auth, title="  Đám cưới   Nam ", content=NAMES))[
        "title"
    ] == "Đám cưới Nam"
    assert (await _create(client, auth, title="", content=NAMES))["title"] == "Nam & Lan"
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", "title": "a" * 121}, headers=auth
    )
    assert _details(resp) == [("title", "too_long")]


async def test_create_rejects_invalid_content(client: AsyncClient, templates, auth) -> None:
    cases = [
        (
            {"couple": {"groom": {"short_name": "Nam"}}},
            ("content.couple.groom.short_name", "unknown_field"),
        ),
        (
            {"appearance": {"palette_key": "walnut"}},
            ("content.appearance.palette_key", "invalid_choice"),
        ),
        (
            {"appearance": {"sections": ["gifts"]}},
            ("content.appearance.sections[0]", "invalid_choice"),
        ),
        ({"love_story": [{"month": 3}]}, ("content.love_story[0].title", "required")),
        (None, ("content", "required")),
        ([], ("content", "invalid_format")),
    ]
    for content, detail in cases:
        resp = await client.post(
            "/invitations", json={"template_key": "classic_01", "content": content}, headers=auth
        )
        assert _details(resp) == [detail], content
    assert (await client.get("/invitations", headers=auth)).json() == []


async def test_create_rejects_love_story_media(client: AsyncClient, templates, auth) -> None:
    # Thiệp mới chưa có file nào, nên mọi media_id đều không hợp lệ
    content = {"love_story": [{"title": "Lần đầu gặp nhau", "media_id": str(uuid.uuid4())}]}
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", "content": content}, headers=auth
    )
    assert _details(resp) == [("content.love_story[0].media_id", "invalid_reference")]


async def test_create_rejects_unknown_fields(client: AsyncClient, templates, auth) -> None:
    for field, value in [
        ("status", "published"),
        ("revision", 3),
        ("cover_media_id", str(uuid.uuid4())),
        ("event_date", "2026-12-20"),
    ]:
        resp = await client.post(
            "/invitations", json={"template_key": "classic_01", field: value}, headers=auth
        )
        assert _details(resp) == [(field, "unknown_field")]


async def test_create_rejects_premium_and_unknown_template(
    client: AsyncClient, templates, auth
) -> None:
    premium = await client.post("/invitations", json={"template_key": "vintage_01"}, headers=auth)
    assert premium.status_code == 400
    assert _error_code(premium) == "template_premium"

    for key in ["khong_co", "old_01"]:
        resp = await client.post("/invitations", json={"template_key": key}, headers=auth)
        assert resp.status_code == 404
        assert _error_code(resp) == "template_not_found"

    kebab = await client.post("/invitations", json={"template_key": "classic-01"}, headers=auth)
    assert _details(kebab) == [("template_key", "invalid_format")]
    missing = await client.post("/invitations", json={}, headers=auth)
    assert _details(missing) == [("template_key", "required")]


async def test_invitation_limit(client: AsyncClient, templates, auth, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_invitations_per_user", 1)
    await _create(client, auth)
    resp = await client.post("/invitations", json={"template_key": "classic_01"}, headers=auth)
    assert resp.status_code == 400
    assert _error_code(resp) == "invitation_limit"


async def test_concurrent_creates_do_not_exceed_limit(client: AsyncClient, templates, auth) -> None:
    assert settings.max_invitations_per_user == 5
    for _ in range(3):
        await _create(client, auth)

    responses = await asyncio.gather(
        *(
            client.post("/invitations", json={"template_key": "classic_01"}, headers=auth)
            for _ in range(5)
        )
    )
    assert sorted(r.status_code for r in responses) == [201, 201, 400, 400, 400]
    assert {_error_code(r) for r in responses if r.status_code == 400} == {"invitation_limit"}
    assert len((await client.get("/invitations", headers=auth)).json()) == 5


# ---------- ETag, If-Match ----------


async def test_single_invitation_responses_have_etag(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _create(client, auth, content=NAMES)
    await _add_ready_event(session_maker, inv["id"])
    url = f"/invitations/{inv['id']}"
    assert (await client.get(url, headers=auth)).headers["etag"] == '"1"'

    patched = await _patch(client, auth, inv, {"title": "Mới"})
    assert patched.headers["etag"] == '"2"'

    # publish/unpublish không đổi revision
    published = await client.post(f"{url}/publish", headers=auth)
    assert published.headers["etag"] == '"2"'
    assert published.json()["revision"] == 2
    unpublished = await client.post(f"{url}/unpublish", headers=auth)
    assert unpublished.headers["etag"] == '"2"'

    listed = await client.get("/invitations", headers=auth)
    assert "etag" not in listed.headers
    assert set(listed.json()[0]) == RESPONSE_FIELDS


async def test_cors_exposes_etag(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    origin = settings.cors_origins[0]
    resp = await client.get(f"/invitations/{inv['id']}", headers={**auth, "Origin": origin})
    assert "etag" in resp.headers["access-control-expose-headers"].lower()


async def test_patch_without_if_match_is_428(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    resp = await client.patch(f"/invitations/{inv['id']}", json={"title": "Mới"}, headers=auth)
    assert resp.status_code == 428
    assert resp.json()["error"] == {
        "code": "revision_required",
        "message": resp.json()["error"]["message"],
        "details": [],
    }
    assert (await _get(client, auth, inv))["title"] == inv["title"]

    # Chưa đăng nhập thì 401 trước; thiếu If-Match thì 428 trước lỗi body
    anonymous = await client.patch(f"/invitations/{inv['id']}", json={"title": "Mới"})
    assert anonymous.status_code == 401
    bad_body = await client.patch(f"/invitations/{inv['id']}", json={"x": 1}, headers=auth)
    assert bad_body.status_code == 428


async def test_patch_with_stale_revision_is_409(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    await _patch_ok(client, auth, inv, {"title": "Lần 1"})

    stale = await _patch(client, auth, inv, {"title": "Lần 2"}, revision=1)
    assert stale.status_code == 409
    assert _error_code(stale) == "revision_conflict"
    assert stale.headers["etag"] == '"2"'
    current = await _get(client, auth, inv)
    assert (current["title"], current["revision"]) == ("Lần 1", 2)


async def test_malformed_if_match_is_409(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    for value in ["1", "*", 'W/"1"', '"1", "2"', '""', "", '"01"']:
        resp = await client.patch(
            f"/invitations/{inv['id']}", json={"title": "Mới"}, headers={**auth, "If-Match": value}
        )
        assert resp.status_code == 409, value
        assert resp.headers["etag"] == '"1"'


async def test_revision_is_checked_before_content(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    await _patch_ok(client, auth, inv, {"title": "Mới"})
    resp = await _patch(client, auth, inv, {"content": {"theme": {}}}, revision=1)
    assert resp.status_code == 409


async def test_concurrent_patches_with_same_revision(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    responses = await asyncio.gather(
        _patch(client, auth, inv, {"title": "Máy A"}), _patch(client, auth, inv, {"title": "Máy B"})
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (await _get(client, auth, inv))["revision"] == 2


# ---------- Merge Patch ----------


async def _full_invitation(client: AsyncClient, auth: dict) -> dict:
    content = {
        **NAMES,
        "messages": {"greeting": "Cảm ơn bạn đã đến", "guest_notes": "Có chỗ gửi xe"},
        "love_story": [{"title": "Lần đầu gặp nhau", "year": 2019}, {"title": "Cầu hôn"}],
        "gifts": [GIFT],
        "appearance": {"palette_key": "burgundy", "sections": ["cover", "couple", "events"]},
    }
    return await _create(client, auth, content=content)


async def test_patch_keeps_fields_not_sent(client: AsyncClient, templates, auth) -> None:
    inv = await _full_invitation(client, auth)
    body = await _patch_ok(client, auth, inv, {"content": {"couple": {"groom": {"bio": "Kỹ sư"}}}})

    expected = copy.deepcopy(inv["content"])
    expected["couple"]["groom"]["bio"] = "Kỹ sư"
    assert body["content"] == expected
    assert (body["title"], body["slug"], body["template_key"]) == (
        inv["title"],
        inv["slug"],
        inv["template_key"],
    )


async def test_patch_null_clears_value(client: AsyncClient, templates, auth) -> None:
    inv = await _full_invitation(client, auth)
    patch = {
        "content": {
            "couple": {"groom": {"display_name": None}},
            "messages": {"greeting": None},
            "appearance": {"palette_key": None},
        }
    }
    content = (await _patch_ok(client, auth, inv, patch))["content"]
    assert content["couple"]["groom"]["display_name"] is None
    assert content["couple"]["groom"]["full_name"] == "Nguyễn Văn Nam"
    assert content["messages"] == {
        "greeting": None,
        "invitation_message": None,
        "guest_notes": "Có chỗ gửi xe",
    }
    assert content["appearance"]["palette_key"] is None


async def test_patch_replaces_lists(client: AsyncClient, templates, auth) -> None:
    inv = await _full_invitation(client, auth)
    body = await _patch_ok(
        client, auth, inv, {"content": {"love_story": [{"title": "Đám cưới", "year": 2026}]}}
    )
    assert body["content"]["love_story"] == [
        {"title": "Đám cưới", "description": None, "year": 2026, "month": None, "media_id": None}
    ]
    assert body["content"]["gifts"] == [GIFT]

    cleared = await _patch_ok(
        client, auth, body, {"content": {"gifts": None, "appearance": {"sections": None}}}
    )
    assert cleared["content"]["gifts"] == []
    assert cleared["content"]["appearance"]["sections"] == []
    assert cleared["content"]["love_story"] == body["content"]["love_story"]


async def test_patch_null_on_boolean_or_group_is_required(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _full_invitation(client, auth)
    cases = [
        (
            {"couple": {"groom": {"father": {"is_deceased": None}}}},
            "content.couple.groom.father.is_deceased",
        ),
        ({"couple": {"bride": None}}, "content.couple.bride"),
        ({"messages": None}, "content.messages"),
        ({"appearance": None}, "content.appearance"),
    ]
    for patch, field in cases:
        assert _details(await _patch(client, auth, inv, {"content": patch})) == [
            (field, "required")
        ]
    assert (await _get(client, auth, inv)) == inv


async def test_patch_null_on_top_level_fields_is_required(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _create(client, auth)
    body = {"title": None, "slug": None, "template_key": None, "content": None}
    assert sorted(_details(await _patch(client, auth, inv, body))) == [
        ("content", "required"),
        ("slug", "required"),
        ("template_key", "required"),
        ("title", "required"),
    ]
    assert _details(await _patch(client, auth, inv, {"title": "   "})) == [("title", "required")]
    assert _details(await _patch(client, auth, inv, {"slug": ""})) == [("slug", "required")]
    assert _details(await _patch(client, auth, inv, {"content": []})) == [
        ("content", "invalid_format")
    ]


async def test_patch_rejects_unknown_fields(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    for field, value in [("status", "published"), ("revision", 5), ("event_date", "2026-12-20")]:
        assert _details(await _patch(client, auth, inv, {field: value})) == [
            (field, "unknown_field")
        ]
    assert _details(await _patch(client, auth, inv, {"content": {"events": []}})) == [
        ("content.events", "unknown_field")
    ]


async def test_patch_validates_whole_content_with_paths(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _create(client, auth)
    patch = {
        "content": {
            "love_story": [{"title": "A"}, {"title": "B", "month": 3}],
            "gifts": [{**GIFT, "bank_bin": "97043", "account_number": "0123 456"}],
            "couple": {"groom": {"birth_order": "truong_nam"}},
        }
    }
    resp = await _patch(client, auth, inv, patch)
    assert sorted(_details(resp)) == [
        ("content.couple.groom.birth_order", "invalid_choice"),
        ("content.gifts[0].account_number", "invalid_format"),
        ("content.gifts[0].bank_bin", "invalid_format"),
        ("content.love_story[1].year", "required"),
    ]
    assert resp.json()["error"]["code"] == "validation_error"
    assert (await _get(client, auth, inv))["revision"] == 1


async def test_patch_title_and_slug(client: AsyncClient, templates, auth, other_auth) -> None:
    other = await _create(client, other_auth, slug="hung-mai")
    inv = await _create(client, auth)
    body = await _patch_ok(client, auth, inv, {"title": "  Thiệp   mới ", "slug": " Nam-Va-Lan "})
    assert (body["title"], body["slug"]) == ("Thiệp mới", "nam-va-lan")

    taken = await _patch(client, auth, body, {"slug": other["slug"]})
    assert taken.status_code == 409
    assert _error_code(taken) == "slug_taken"
    assert _details(await _patch(client, auth, body, {"slug": "admin"})) == [
        ("slug", "invalid_format")
    ]
    assert _details(await _patch(client, auth, body, {"title": "a" * 121})) == [
        ("title", "too_long")
    ]


async def test_patch_accepts_merge_patch_content_type(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    resp = await client.patch(
        f"/invitations/{inv['id']}",
        content=json.dumps({"content": {"messages": {"greeting": "Xin chào"}}}),
        headers={**auth, "If-Match": '"1"', "Content-Type": "application/merge-patch+json"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["content"]["messages"]["greeting"] == "Xin chào"


# ---------- revision ----------


async def test_revision_increments_on_each_change(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _create(client, auth)
    cover = await _add_media(session_maker, inv["id"])
    patches = [
        {"title": "Mới"},
        {"slug": "nam-lan-moi"},
        {"content": {"messages": {"greeting": "Xin chào"}}},
        {"template_key": "minimal_01"},
        {"cover_media_id": cover},
        {"cover_media_id": None},
    ]
    for expected, patch in enumerate(patches, start=2):
        resp = await _patch(client, auth, inv, patch)
        assert resp.status_code == 200, (patch, resp.text)
        inv = resp.json()
        assert inv["revision"] == expected
        assert resp.headers["etag"] == f'"{expected}"'


async def test_patch_without_real_change_keeps_revision(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _full_invitation(client, auth)
    unchanged = [
        {},
        {"title": inv["title"]},
        {"slug": inv["slug"].upper()},
        {"template_key": "classic_01"},
        {"content": {}},
        {"content": {"couple": {"groom": {"full_name": " Nguyễn  Văn Nam "}}}},
        {"content": {"gifts": [GIFT]}},
        {"cover_media_id": None},
    ]
    for patch in unchanged:
        resp = await _patch(client, auth, inv, patch)
        assert resp.status_code == 200, (patch, resp.text)
        assert resp.json() == inv, patch
        assert resp.headers["etag"] == '"1"'


# ---------- Đổi template ----------


async def _classic_with_appearance(client: AsyncClient, auth: dict, sections: list[str]) -> dict:
    appearance = {
        "palette_key": "burgundy",
        "font_key": "playfair_display",
        "background_key": "paper",
        "sections": sections,
    }
    return await _create(client, auth, content={**NAMES, "appearance": appearance})


async def test_change_template_adjusts_appearance(client: AsyncClient, templates, auth) -> None:
    inv = await _classic_with_appearance(
        client, auth, ["gallery", "cover", "greeting", "couple", "events"]
    )
    body = await _patch_ok(client, auth, inv, {"template_key": "minimal_01"})
    assert body["template_key"] == "minimal_01"
    assert body["revision"] == 2
    # burgundy, plain/cover/events/gallery có ở minimal_01; playfair_display, paper thì không
    assert body["content"]["appearance"] == {
        "palette_key": "burgundy",
        "font_key": None,
        "background_key": None,
        "sections": ["gallery", "cover", "events"],
    }
    assert body["content"]["couple"] == inv["content"]["couple"]


async def test_change_template_without_any_section_left_uses_default_sections(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _classic_with_appearance(client, auth, ["greeting", "couple"])
    body = await _patch_ok(client, auth, inv, {"template_key": "minimal_01"})
    assert body["content"]["appearance"]["sections"] == ["cover", "events"]

    empty = await _classic_with_appearance(client, auth, [])
    body = await _patch_ok(client, auth, empty, {"template_key": "minimal_01"})
    assert body["content"]["appearance"]["sections"] == ["cover", "events"]


async def test_change_template_with_explicit_appearance_is_strict(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _classic_with_appearance(client, auth, ["cover", "events"])
    invalid = {
        "template_key": "minimal_01",
        "content": {"appearance": {"font_key": "playfair_display"}},
    }
    assert _details(await _patch(client, auth, inv, invalid)) == [
        ("content.appearance.font_key", "invalid_choice")
    ]
    assert (await _get(client, auth, inv))["template_key"] == "classic_01"

    valid = {
        "template_key": "minimal_01",
        "content": {"appearance": {"palette_key": "charcoal", "sections": ["gifts", "cover"]}},
    }
    body = await _patch_ok(client, auth, inv, valid)
    assert body["content"]["appearance"] == {
        "palette_key": "charcoal",
        "font_key": None,
        "background_key": None,
        "sections": ["gifts", "cover"],
    }


async def test_content_follows_manifest_of_current_template(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _create(client, auth)
    inv = await _patch_ok(client, auth, inv, {"template_key": "minimal_01"})
    for appearance, field in [
        ({"palette_key": "ivory_gold"}, "content.appearance.palette_key"),
        ({"sections": ["greeting"]}, "content.appearance.sections[0]"),
    ]:
        resp = await _patch(client, auth, inv, {"content": {"appearance": appearance}})
        assert _details(resp) == [(field, "invalid_choice")]


async def test_change_to_unusable_template(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    premium = await _patch(client, auth, inv, {"template_key": "vintage_01"})
    assert premium.status_code == 400
    assert _error_code(premium) == "template_premium"
    for key in ["khong_co", "old_01"]:
        resp = await _patch(client, auth, inv, {"template_key": key})
        assert resp.status_code == 404
        assert _error_code(resp) == "template_not_found"
    assert (await _get(client, auth, inv)) == inv


async def test_patch_appearance_is_checked_against_manifest(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _create(client, auth)
    cases = [
        ({"palette_key": "walnut"}, ("content.appearance.palette_key", "invalid_choice")),
        ({"background_key": "kraft"}, ("content.appearance.background_key", "invalid_choice")),
        ({"sections": ["cover", "cover"]}, ("content.appearance.sections[1]", "invalid_format")),
        ({"sections": ["cover", "gifts"]}, ("content.appearance.sections[1]", "invalid_choice")),
    ]
    for appearance, detail in cases:
        resp = await _patch(client, auth, inv, {"content": {"appearance": appearance}})
        assert _details(resp) == [detail], appearance


# ---------- Tham chiếu media ----------


async def test_set_and_clear_media_columns(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _create(client, auth)
    refs = {
        "cover_media_id": await _add_media(session_maker, inv["id"]),
        "groom_photo_media_id": await _add_media(session_maker, inv["id"]),
        "bride_photo_media_id": await _add_media(session_maker, inv["id"]),
        "music_media_id": await _add_media(session_maker, inv["id"], kind="audio"),
    }
    body = await _patch_ok(client, auth, inv, refs)
    assert {column: body[column] for column in refs} == refs
    assert body["revision"] == 2
    assert (await _get(client, auth, inv)) == body

    cleared = await _patch_ok(client, auth, body, {"cover_media_id": None, "music_media_id": None})
    assert cleared["cover_media_id"] is None and cleared["music_media_id"] is None
    assert cleared["groom_photo_media_id"] == refs["groom_photo_media_id"]
    assert cleared["revision"] == 3


async def test_media_column_must_have_right_kind_and_be_ready(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _create(client, auth)
    sibling = await _create(client, auth)  # thiệp khác của cùng chủ
    image = await _add_media(session_maker, inv["id"])
    audio = await _add_media(session_maker, inv["id"], kind="audio")
    pending = await _add_media(session_maker, inv["id"], status="pending")
    sibling_image = await _add_media(session_maker, sibling["id"])
    cases = [
        ("cover_media_id", audio),
        ("groom_photo_media_id", audio),
        ("music_media_id", image),
        ("bride_photo_media_id", pending),
        ("cover_media_id", sibling_image),
        ("cover_media_id", str(uuid.uuid4())),
    ]
    for column, media_id in cases:
        resp = await _patch(client, auth, inv, {column: media_id})
        assert _details(resp) == [(column, "invalid_reference")], (column, media_id)
    assert _details(await _patch(client, auth, inv, {"cover_media_id": image.upper()})) == [
        ("cover_media_id", "invalid_format")
    ]
    assert (await _get(client, auth, inv)) == inv


async def test_love_story_media_must_be_ready_image_of_invitation(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _create(client, auth)
    sibling = await _create(client, auth)
    image = await _add_media(session_maker, inv["id"])
    bad = [
        await _add_media(session_maker, inv["id"], kind="audio"),
        await _add_media(session_maker, inv["id"], status="pending"),
        await _add_media(session_maker, sibling["id"]),
        str(uuid.uuid4()),
    ]
    for media_id in bad:
        story = [{"title": "Có ảnh", "media_id": image}, {"title": "Sai", "media_id": media_id}]
        resp = await _patch(client, auth, inv, {"content": {"love_story": story}})
        assert _details(resp) == [("content.love_story[1].media_id", "invalid_reference")]

    story = [{"title": "Có ảnh", "media_id": image}, {"title": "Không ảnh"}]
    body = await _patch_ok(client, auth, inv, {"content": {"love_story": story}})
    assert [item["media_id"] for item in body["content"]["love_story"]] == [image, None]


async def test_media_is_checked_only_when_sent(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _create(client, auth)
    cover = await _add_media(session_maker, inv["id"])
    photo = await _add_media(session_maker, inv["id"])
    story = [{"title": "Lần đầu gặp nhau", "media_id": photo}]
    inv = await _patch_ok(
        client, auth, inv, {"cover_media_id": cover, "content": {"love_story": story}}
    )
    await _set_media_status(session_maker, cover, "pending")
    await _set_media_status(session_maker, photo, "pending")

    inv = await _patch_ok(client, auth, inv, {"title": "Mới"})
    inv = await _patch_ok(client, auth, inv, {"content": {"messages": {"greeting": "Chào"}}})
    resend_cover = await _patch(client, auth, inv, {"cover_media_id": cover})
    assert _details(resend_cover) == [("cover_media_id", "invalid_reference")]
    resend_story = await _patch(client, auth, inv, {"content": {"love_story": story}})
    assert _details(resend_story) == [("content.love_story[0].media_id", "invalid_reference")]


async def test_content_and_media_errors_are_reported_together(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _create(client, auth)
    patch = {
        "cover_media_id": str(uuid.uuid4()),
        "content": {"appearance": {"palette_key": "walnut"}},
    }
    assert _details(await _patch(client, auth, inv, patch)) == [
        ("content.appearance.palette_key", "invalid_choice"),
        ("cover_media_id", "invalid_reference"),
    ]


# ---------- Ngày chính, quyền, publish, xoá ----------


async def test_primary_event_date_is_earliest_event_date(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _create(client, auth)
    without_events = await _create(client, auth)
    async with session_maker() as db:
        for event_date in [date(2026, 12, 20), date(2026, 12, 18), None]:
            db.add(
                Event(
                    invitation_id=uuid.UUID(inv["id"]),
                    event_type="reception",
                    host_side="both",
                    event_date=event_date,
                )
            )
        await db.commit()

    assert (await _get(client, auth, inv))["primary_event_date"] == "2026-12-18"
    listed = {i["id"]: i for i in (await client.get("/invitations", headers=auth)).json()}
    assert listed[inv["id"]]["primary_event_date"] == "2026-12-18"
    assert listed[without_events["id"]]["primary_event_date"] is None


async def test_other_user_cannot_access(client: AsyncClient, templates, auth, other_auth) -> None:
    inv = await _create(client, auth)
    url = f"/invitations/{inv['id']}"
    assert (await client.get(url, headers=other_auth)).status_code == 404
    assert (await _patch(client, other_auth, inv, {"title": "X"})).status_code == 404
    assert (await client.delete(url, headers=other_auth)).status_code == 404
    assert (await client.get("/invitations", headers=other_auth)).json() == []
    assert len((await client.get("/invitations", headers=auth)).json()) == 1


async def test_publish_flow_and_public_page(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    # Từng điều kiện publish: tests/test_publish.py. display_name không thay được full_name
    display_only = {"couple": {"groom": {"display_name": "Nam"}, "bride": {"display_name": "Lan"}}}
    empty = await _create(client, auth, content=display_only, slug="thiep-trong")
    await _add_ready_event(session_maker, empty["id"])
    resp = await client.post(f"/invitations/{empty['id']}/publish", headers=auth)
    assert _details(resp, 400) == [
        ("content.couple.groom.full_name", "required"),
        ("content.couple.bride.full_name", "required"),
    ]
    assert _error_code(resp) == "not_ready_to_publish"

    inv = await _create(client, auth, content=NAMES)
    await _add_ready_event(session_maker, inv["id"])
    assert (await client.get("/public/invitations/nam-lan")).status_code == 404

    published = await client.post(f"/invitations/{inv['id']}/publish", headers=auth)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published_at"] is not None

    public = await client.get("/public/invitations/NAM-LAN")
    assert public.status_code == 200
    assert "s-maxage" in public.headers["cache-control"]
    body = public.json()
    assert body["template_key"] == "classic_01"
    assert body["content"]["couple"]["groom"]["display_name"] == "Nam"
    assert body["albums"] == [] and body["media"] == []
    assert "owner_id" not in body

    unpublished = await client.post(f"/invitations/{inv['id']}/unpublish", headers=auth)
    assert unpublished.json()["status"] == "draft"
    assert (await client.get("/public/invitations/nam-lan")).status_code == 404


async def test_delete_invitation(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    assert (await client.delete(f"/invitations/{inv['id']}", headers=auth)).status_code == 204
    assert (await client.get(f"/invitations/{inv['id']}", headers=auth)).status_code == 404


async def test_openapi_has_invitation_schemas(client: AsyncClient) -> None:
    schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]
    assert {"InvitationCreate", "InvitationUpdate", "InvitationContent"} <= set(schemas)
    assert any(name.startswith("InvitationResponse") for name in schemas)
    assert not any(name.startswith("InvitationOut") for name in schemas)
    assert set(schemas["InvitationUpdate"]["properties"]) == {
        "title",
        "slug",
        "template_key",
        "content",
        "cover_media_id",
        "groom_photo_media_id",
        "bride_photo_media_id",
        "music_media_id",
    }
