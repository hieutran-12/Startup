"""Gán file vào thiệp và dọn tham chiếu khi xoá file (spec 04 › Tham chiếu media, Bước 7).

Tiêu chí nghiệm thu: upload mp3 gán được vào music_media_id, gán ảnh vào music_media_id bị từ
chối; xoá ảnh đang dùng ở love_story thì media_id ở đó về null. Thêm (đề xuất 6, duyệt 2026-11-06):
xoá file khóa dòng thiệp, không cần If-Match, 204 có ETag là revision sau khi xoá; revision chỉ tăng
khi thiệp đang dùng file (ở cột *_media_id hoặc love_story).
"""

import asyncio
from typing import Any

from httpx import AsyncClient, Response

from app.modules.media import router as media_router
from tests.conftest import upload_media

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
    "address": "Nhà hàng ABC, Hà Nội",
}


async def _invitation(client: AsyncClient, auth: dict) -> dict:
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", "content": NAMES}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _get(client: AsyncClient, auth: dict, invitation_id: str) -> Response:
    resp = await client.get(f"/invitations/{invitation_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp


async def _patch(
    client: AsyncClient, auth: dict, invitation_id: str, revision: int, body: Any
) -> Response:
    return await client.patch(
        f"/invitations/{invitation_id}", json=body, headers={**auth, "If-Match": f'"{revision}"'}
    )


async def _patch_ok(client: AsyncClient, auth: dict, inv: dict, body: Any) -> dict:
    resp = await _patch(client, auth, inv["id"], inv["revision"], body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _delete_media(
    client: AsyncClient, auth: dict, invitation_id: str, media_id: str
) -> Response:
    return await client.delete(f"/invitations/{invitation_id}/media/{media_id}", headers=auth)


def _details(resp: Response) -> list[tuple[str, str, str]]:
    assert resp.status_code == 422, resp.text
    return [(d["field"], d["code"], d["message"]) for d in resp.json()["error"]["details"]]


# ---------- Gán file ----------


async def test_uploaded_mp3_can_be_music(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    mp3 = await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg")
    body = await _patch_ok(client, auth, inv, {"music_media_id": mp3["id"]})
    assert body["music_media_id"] == mp3["id"]
    assert body["revision"] == 2

    # File .m4a trình duyệt báo là audio/x-m4a cũng làm nhạc nền được
    other = await _invitation(client, auth)
    m4a = await upload_media(client, auth, fake_storage, other["id"], content_type="audio/x-m4a")
    assert (await _patch_ok(client, auth, other, {"music_media_id": m4a["id"]}))[
        "music_media_id"
    ] == m4a["id"]


async def test_image_cannot_be_music_and_audio_cannot_be_image(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    image = await upload_media(client, auth, fake_storage, inv["id"])
    mp3 = await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg")

    music = await _patch(client, auth, inv["id"], 1, {"music_media_id": image["id"]})
    assert _details(music) == [("music_media_id", "invalid_reference", "Cần một file âm thanh")]
    for column in ("cover_media_id", "groom_photo_media_id", "bride_photo_media_id"):
        resp = await _patch(client, auth, inv["id"], 1, {column: mp3["id"]})
        assert _details(resp) == [(column, "invalid_reference", "Cần một file ảnh")]
    story = {"content": {"love_story": [{"title": "Lần đầu gặp nhau", "media_id": mp3["id"]}]}}
    resp = await _patch(client, auth, inv["id"], 1, story)
    assert _details(resp) == [
        ("content.love_story[0].media_id", "invalid_reference", "Cần một file ảnh")
    ]
    assert (await _get(client, auth, inv["id"])).json() == inv


# ---------- Xoá file ----------


async def test_delete_image_used_in_love_story(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    used = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    other = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    story = [
        {
            "title": "Lần đầu gặp nhau",
            "description": None,
            "year": 2019,
            "month": 3,
            "media_id": used,
        },
        {"title": "Cầu hôn", "description": None, "year": 2024, "month": None, "media_id": other},
        {
            "title": "Ngày cưới",
            "description": "Hà Nội",
            "year": None,
            "month": None,
            "media_id": used,
        },
    ]
    inv = await _patch_ok(client, auth, inv, {"content": {"love_story": story}})
    assert inv["revision"] == 2

    deleted = await _delete_media(client, auth, inv["id"], used)
    assert deleted.status_code == 204
    assert deleted.headers["ETag"] == '"3"'

    fresh = await _get(client, auth, inv["id"])
    assert fresh.headers["ETag"] == '"3"'
    body = fresh.json()
    assert body["revision"] == 3
    # Mốc giữ nguyên, chỉ media_id về null
    assert body["content"]["love_story"] == [
        {**story[0], "media_id": None},
        story[1],
        {**story[2], "media_id": None},
    ]
    assert {k: v for k, v in body["content"].items() if k != "love_story"} == {
        k: v for k, v in inv["content"].items() if k != "love_story"
    }
    assert any(used in key for key in fake_storage.deleted)

    # FE dùng ETag của DELETE để sửa tiếp; revision cũ thì 409
    stale = await _patch(client, auth, inv["id"], 2, {"title": "Mới"})
    assert stale.status_code == 409
    assert (await _patch(client, auth, inv["id"], 3, {"title": "Mới"})).status_code == 200


async def test_delete_media_used_in_columns(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    image = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    keep = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    mp3 = (await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg"))[
        "id"
    ]
    inv = await _patch_ok(
        client,
        auth,
        inv,
        {
            "cover_media_id": image,
            "groom_photo_media_id": image,
            "bride_photo_media_id": keep,
            "music_media_id": mp3,
            "content": {"love_story": [{"title": "Lần đầu gặp nhau", "media_id": image}]},
        },
    )
    assert inv["revision"] == 2

    # Một file ở hai cột và love_story: một lần xoá tăng revision đúng 1
    deleted = await _delete_media(client, auth, inv["id"], image)
    assert deleted.headers["ETag"] == '"3"'
    body = (await _get(client, auth, inv["id"])).json()
    assert (body["cover_media_id"], body["groom_photo_media_id"]) == (None, None)
    assert (body["bride_photo_media_id"], body["music_media_id"]) == (keep, mp3)
    assert body["content"]["love_story"][0]["media_id"] is None
    assert body["revision"] == 3

    deleted = await _delete_media(client, auth, inv["id"], mp3)
    assert deleted.headers["ETag"] == '"4"'
    body = (await _get(client, auth, inv["id"])).json()
    assert body["music_media_id"] is None
    assert body["bride_photo_media_id"] == keep
    assert body["revision"] == 4


async def test_delete_unreferenced_media_keeps_revision(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    used = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    unused = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    ticket = await client.post(
        f"/invitations/{inv['id']}/media/upload-url",
        json={"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 1000},
        headers=auth,
    )
    pending = ticket.json()["media_id"]
    inv = await _patch_ok(client, auth, inv, {"cover_media_id": used})

    for media_id in (unused, pending):
        deleted = await _delete_media(client, auth, inv["id"], media_id)
        assert deleted.status_code == 204
        assert deleted.headers["ETag"] == '"2"'
    assert (await _get(client, auth, inv["id"])).json() == inv  # cả updated_at giữ nguyên


async def test_delete_media_of_another_invitation_is_404(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    sibling = await _invitation(client, auth)
    image = (await upload_media(client, auth, fake_storage, sibling["id"]))["id"]
    resp = await _delete_media(client, auth, inv["id"], image)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "media_not_found"
    listed = await client.get(f"/invitations/{sibling['id']}/media", headers=auth)
    assert [m["id"] for m in listed.json()] == [image]


async def test_delete_media_revalidates_published_invitation(
    client: AsyncClient, templates, auth, fake_storage, monkeypatch
) -> None:
    calls: list[tuple[str, ...]] = []

    async def record(*slugs: str) -> None:
        calls.append(slugs)

    monkeypatch.setattr(media_router, "revalidate_invitation", record)
    inv = await _invitation(client, auth)
    image = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    await _delete_media(client, auth, inv["id"], image)
    assert calls == []  # thiệp còn nháp

    event = await client.post(
        f"/invitations/{inv['id']}/events",
        json=READY_EVENT,
        headers={**auth, "If-Match": f'"{inv["revision"]}"'},
    )
    assert event.status_code == 201, event.text
    assert (await client.post(f"/invitations/{inv['id']}/publish", headers=auth)).status_code == 200
    image = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    calls.clear()
    assert (await _delete_media(client, auth, inv["id"], image)).status_code == 204
    assert calls == [(inv["slug"],)]


async def test_concurrent_patch_and_delete_leave_no_dangling_reference(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    """PATCH gắn file vào love_story cùng lúc với DELETE file đó: cả hai khóa dòng thiệp nên chạy
    lần lượt; kết quả không bao giờ còn media_id trỏ tới file đã xoá."""
    inv = await _invitation(client, auth)
    for _ in range(8):
        image = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
        current = (await _get(client, auth, inv["id"])).json()
        story = {"content": {"love_story": [{"title": "Lần đầu gặp nhau", "media_id": image}]}}
        patched, deleted = await asyncio.gather(
            _patch(client, auth, inv["id"], current["revision"], story),
            _delete_media(client, auth, inv["id"], image),
        )
        assert deleted.status_code == 204
        assert patched.status_code in (200, 422), patched.text
        body = (await _get(client, auth, inv["id"])).json()
        assert [item["media_id"] for item in body["content"]["love_story"]] in ([], [None])
        # PATCH thành công thì DELETE chạy sau nó; nên ETag của DELETE luôn là revision cuối
        assert deleted.headers["ETag"] == f'"{body["revision"]}"'
