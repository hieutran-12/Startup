"""Ảnh, file âm thanh và album: upload 3 bước, loại file, giới hạn, thứ tự, album.

Spec Bước 7: 03 › media (kind, loại file cho phép, giới hạn số lượng), 05 (upload-url suy ra kind
từ content_type). 9 đề xuất được duyệt 2026-11-06 (docs/modules/media.md). Gán file vào thiệp và
dọn tham chiếu khi xoá file: tests/test_media_references.py.
"""

import asyncio
import unicodedata
import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.modules.media.models import Media
from tests.conftest import upload_media

MB = 1024 * 1024

CONTENT = {
    "couple": {
        "groom": {"full_name": "Trần Văn Hùng", "display_name": "Hùng"},
        "bride": {"full_name": "Đỗ Thị Mai", "display_name": "Mai"},
    }
}

IMAGE_TYPES = [
    ("image/jpeg", "jpg"),
    ("image/png", "png"),
    ("image/webp", "webp"),
    ("image/avif", "avif"),
]
# audio/mp3 và audio/x-m4a: loại trình duyệt hay báo cho .mp3 và .m4a (spec 03 › media)
AUDIO_TYPES = [
    ("audio/mpeg", "mp3"),
    ("audio/mp3", "mp3"),
    ("audio/mp4", "m4a"),
    ("audio/x-m4a", "m4a"),
]

MEDIA_FIELDS = {
    "id",
    "kind",
    "album_id",
    "url",
    "original_filename",
    "mime_type",
    "size_bytes",
    "width",
    "height",
    "status",
    "position",
    "created_at",
}


# ---------- Helper ----------


async def _invitation(client: AsyncClient, auth: dict) -> dict:
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", "content": CONTENT}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _request_upload(client: AsyncClient, auth: dict, invitation_id: str, **body) -> Response:
    """Chỉ bước 1 (xin link upload). Mặc định là ảnh JPEG 1000 byte."""
    payload = {"filename": "tep", "content_type": "image/jpeg", "size_bytes": 1000, **body}
    return await client.post(
        f"/invitations/{invitation_id}/media/upload-url", json=payload, headers=auth
    )


async def _complete(client: AsyncClient, auth: dict, invitation_id: str, media_id: str, body: dict):
    return await client.post(
        f"/invitations/{invitation_id}/media/{media_id}/complete", json=body, headers=auth
    )


async def _list(client: AsyncClient, auth: dict, invitation_id: str, **params) -> list[dict]:
    resp = await client.get(f"/invitations/{invitation_id}/media", params=params, headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _album(client: AsyncClient, auth: dict, invitation_id: str, title: str = "A") -> str:
    resp = await client.post(
        f"/invitations/{invitation_id}/albums", json={"title": title}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _details(resp: Response, status_code: int = 422) -> list[tuple[str, str]]:
    assert resp.status_code == status_code, resp.text
    return [(d["field"], d["code"]) for d in resp.json()["error"]["details"]]


def _messages(resp: Response) -> list[str]:
    return [d["message"] for d in resp.json()["error"]["details"]]


def _error_code(resp: Response) -> str:
    return resp.json()["error"]["code"]


async def _media_count(session_maker: async_sessionmaker, invitation_id: str, kind: str) -> int:
    async with session_maker() as db:
        return await db.scalar(
            select(func.count(Media.id)).where(
                Media.invitation_id == uuid.UUID(invitation_id), Media.kind == kind
            )
        )


async def _add_images(
    session_maker: async_sessionmaker, invitation_id: str, count: int, *, status: str = "ready"
) -> None:
    """Ghi thẳng `count` ảnh vào DB (nhanh hơn đi qua luồng upload)."""
    async with session_maker() as db:
        for position in range(count):
            media_id = uuid.uuid4()
            db.add(
                Media(
                    id=media_id,
                    invitation_id=uuid.UUID(invitation_id),
                    kind="image",
                    storage_key=f"invitations/{invitation_id}/{media_id}.jpg",
                    mime_type="image/jpeg",
                    size_bytes=1000,
                    status=status,
                    position=position,
                )
            )
        await db.commit()


# ---------- Luồng upload ----------


async def test_full_upload_flow(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    album_id = await _album(client, auth, inv["id"], "Pre-wedding")

    media = await upload_media(
        client, auth, fake_storage, inv["id"], album_id=album_id, filename="anh-cuoi.jpg"
    )
    assert set(media) == MEDIA_FIELDS
    assert media["kind"] == "image"
    assert media["status"] == "ready"
    assert media["album_id"] == album_id
    assert media["width"] == 1600
    assert media["original_filename"] == "anh-cuoi.jpg"
    assert media["url"].startswith(f"https://cdn.test/invitations/{inv['id']}/")
    assert media["url"].endswith(".jpg")

    assert [m["id"] for m in await _list(client, auth, inv["id"])] == [media["id"]]

    albums = await client.get(f"/invitations/{inv['id']}/albums", headers=auth)
    assert albums.json()[0]["media_count"] == 1

    # Gọi /complete lần nữa vẫn trả về ảnh, không lỗi
    again = await _complete(client, auth, inv["id"], media["id"], {})
    assert again.status_code == 200

    # Upload ảnh không đổi revision; publish cần một sự kiện đủ ngày, giờ, địa chỉ
    event = await client.post(
        f"/invitations/{inv['id']}/events",
        json={
            "event_type": "reception",
            "host_side": "both",
            "event_date": "2026-12-20",
            "start_time": "11:00",
            "address": "Nhà hàng ABC, Hà Nội",
        },
        headers={**auth, "If-Match": f'"{inv["revision"]}"'},
    )
    assert event.status_code == 201, event.text
    published = await client.post(f"/invitations/{inv['id']}/publish", headers=auth)
    assert published.status_code == 200, published.text
    public = (await client.get(f"/public/invitations/{inv['slug']}")).json()
    assert public["albums"][0]["title"] == "Pre-wedding"
    assert public["gallery"] == [{"media_id": media["id"], "album_id": album_id}]
    assert public["media_by_id"][media["id"]]["url"] == media["url"]


@pytest.mark.parametrize(("content_type", "extension"), IMAGE_TYPES + AUDIO_TYPES)
async def test_upload_ticket_signs_content_type(
    client: AsyncClient, templates, auth, content_type: str, extension: str
) -> None:
    inv = await _invitation(client, auth)
    resp = await _request_upload(client, auth, inv["id"], content_type=content_type)
    assert resp.status_code == 200, resp.text
    ticket = resp.json()
    assert set(ticket) == {"media_id", "upload_url", "method", "headers", "expires_in"}
    assert ticket["method"] == "PUT"
    # FE phải PUT đúng Content-Type đã ký: loại client gửi, không đổi sang loại chuẩn
    assert ticket["headers"] == {"Content-Type": content_type}
    assert f"/invitations/{inv['id']}/{ticket['media_id']}.{extension}?" in ticket["upload_url"]


@pytest.mark.parametrize(("content_type", "extension"), AUDIO_TYPES)
async def test_upload_audio_file(
    client: AsyncClient, templates, auth, fake_storage, content_type: str, extension: str
) -> None:
    inv = await _invitation(client, auth)
    media = await upload_media(
        client,
        auth,
        fake_storage,
        inv["id"],
        content_type=content_type,
        size_bytes=4 * MB,
        filename="nhac-nen",
    )
    assert set(media) == MEDIA_FIELDS
    assert media["kind"] == "audio"
    assert media["mime_type"] == content_type
    assert media["status"] == "ready"
    assert (media["width"], media["height"], media["album_id"]) == (None, None, None)
    assert media["size_bytes"] == 4 * MB
    assert media["url"].endswith(f".{extension}")
    assert await _list(client, auth, inv["id"]) == [media]


async def test_content_type_must_be_listed_exactly(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _invitation(client, auth)
    rejected = [
        "application/pdf",
        "image/gif",
        "image/heic",
        "audio/wav",
        "audio/ogg",
        "audio/m4a",
        "video/mp4",
        "IMAGE/JPEG",  # so khớp nguyên văn, không tự đổi chữ thường
        "Audio/MPEG",
        " image/jpeg",
        "image/jpeg; charset=binary",
        "",
    ]
    for content_type in rejected:
        resp = await _request_upload(client, auth, inv["id"], content_type=content_type)
        assert _details(resp) == [("content_type", "invalid_choice")], content_type
    missing = await _request_upload(client, auth, inv["id"], content_type=None)
    assert _details(missing) == [("content_type", "required")]
    assert await _media_count(session_maker, inv["id"], "image") == 0
    assert await _media_count(session_maker, inv["id"], "audio") == 0


async def test_size_limits_follow_spec() -> None:
    assert settings.max_image_bytes == 15 * MB
    assert settings.max_audio_bytes == 10 * MB
    assert settings.max_images_per_invitation == 200
    assert settings.max_audio_per_invitation == 1


@pytest.mark.parametrize(
    ("content_type", "limit_bytes", "message"),
    [
        ("image/jpeg", 15 * MB, "Ảnh tối đa 15 MB"),
        ("image/avif", 15 * MB, "Ảnh tối đa 15 MB"),
        ("audio/mpeg", 10 * MB, "File âm thanh tối đa 10 MB"),
        ("audio/x-m4a", 10 * MB, "File âm thanh tối đa 10 MB"),
    ],
)
async def test_size_limit_depends_on_kind(
    client: AsyncClient, templates, auth, content_type: str, limit_bytes: int, message: str
) -> None:
    inv = await _invitation(client, auth)
    over = await _request_upload(
        client, auth, inv["id"], content_type=content_type, size_bytes=limit_bytes + 1
    )
    assert _details(over) == [("size_bytes", "out_of_range")]
    assert _messages(over) == [message]
    exact = await _request_upload(
        client, auth, inv["id"], content_type=content_type, size_bytes=limit_bytes
    )
    assert exact.status_code == 200, exact.text


async def test_audio_limit_is_below_image_limit(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    eleven_mb = 11 * MB
    audio = await _request_upload(
        client, auth, inv["id"], content_type="audio/mp4", size_bytes=eleven_mb
    )
    assert _details(audio) == [("size_bytes", "out_of_range")]
    image = await _request_upload(
        client, auth, inv["id"], content_type="image/png", size_bytes=eleven_mb
    )
    assert image.status_code == 200, image.text


async def test_size_bytes_is_strict_positive_integer(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    cases = [
        (0, "out_of_range"),
        (-1, "out_of_range"),
        ("1000", "invalid_format"),
        (1000.5, "invalid_format"),
        (True, "invalid_format"),
        (None, "required"),
    ]
    for value, code in cases:
        resp = await _request_upload(client, auth, inv["id"], size_bytes=value)
        assert _details(resp) == [("size_bytes", code)], value


async def test_upload_validation(client: AsyncClient, templates, auth) -> None:
    """Hai lỗi của khung đổi từ 400 sang 422 gắn trường (đề xuất 2, Bước 7)."""
    inv = await _invitation(client, auth)
    pdf = await _request_upload(
        client, auth, inv["id"], filename="a.pdf", content_type="application/pdf"
    )
    assert _details(pdf) == [("content_type", "invalid_choice")]

    huge = await _request_upload(client, auth, inv["id"], size_bytes=999_999_999)
    assert _details(huge) == [("size_bytes", "out_of_range")]


async def test_upload_request_is_strict_and_normalized(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    unknown = await _request_upload(client, auth, inv["id"], kind="audio")
    assert _details(unknown) == [("kind", "unknown_field")]

    for filename, code in [
        ("a\nb.jpg", "invalid_characters"),
        ("   ", "required"),
        (None, "required"),
        ("x" * 256, "too_long"),
    ]:
        resp = await _request_upload(client, auth, inv["id"], filename=filename)
        assert _details(resp) == [("filename", code)], filename

    album_id = await _album(client, auth, inv["id"])
    upper = await _request_upload(client, auth, inv["id"], album_id=album_id.upper())
    assert _details(upper) == [("album_id", "invalid_format")]
    missing_album = await _request_upload(client, auth, inv["id"], album_id=str(uuid.uuid4()))
    assert missing_album.status_code == 404
    assert _error_code(missing_album) == "album_not_found"

    nfd = unicodedata.normalize("NFD", "Ảnh cưới.jpg")
    media = await upload_media(client, auth, fake_storage, inv["id"], filename=f"  {nfd}   2026 ")
    assert media["original_filename"] == "Ảnh cưới.jpg 2026"


async def test_complete_requires_uploaded_file(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    ticket = await _request_upload(client, auth, inv["id"], content_type="image/png")
    resp = await _complete(client, auth, inv["id"], ticket.json()["media_id"], {})
    assert resp.status_code == 400
    assert _error_code(resp) == "upload_not_found"

    # Ảnh chưa xác nhận không hiện trong danh sách
    assert await _list(client, auth, inv["id"]) == []


async def test_complete_rejects_oversized_file(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    ticket = (await _request_upload(client, auth, inv["id"])).json()
    # Khai báo 1KB nhưng thực tế PUT lên 100MB
    key = fake_storage.simulate_upload(ticket["upload_url"], 100 * MB, "image/jpeg")

    resp = await _complete(client, auth, inv["id"], ticket["media_id"], {})
    assert resp.status_code == 400
    assert _error_code(resp) == "invalid_upload"
    assert key in fake_storage.deleted


async def test_complete_rechecks_real_size_by_kind(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    # Âm thanh khai báo 1 KB nhưng PUT lên 10 MB + 1 byte: quá giới hạn âm thanh dù dưới 15 MB
    ticket = (await _request_upload(client, auth, inv["id"], content_type="audio/mpeg")).json()
    key = fake_storage.simulate_upload(ticket["upload_url"], 10 * MB + 1, "audio/mpeg")
    resp = await _complete(client, auth, inv["id"], ticket["media_id"], {})
    assert resp.status_code == 400
    assert _error_code(resp) == "invalid_upload"
    assert key in fake_storage.deleted

    # Bản ghi hỏng đã bị xoá nên upload âm thanh mới được; đúng bằng giới hạn thì qua
    audio = await upload_media(
        client, auth, fake_storage, inv["id"], content_type="audio/mpeg", size_bytes=10 * MB
    )
    assert audio["size_bytes"] == 10 * MB
    image = await upload_media(client, auth, fake_storage, inv["id"], size_bytes=15 * MB)
    assert image["size_bytes"] == 15 * MB


async def test_complete_rejects_other_content_type(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    """mime_type lưu đúng loại client gửi: file PUT lên với loại khác bị từ chối."""
    inv = await _invitation(client, auth)
    ticket = (await _request_upload(client, auth, inv["id"], content_type="audio/x-m4a")).json()
    fake_storage.simulate_upload(ticket["upload_url"], 1000, "audio/mp4")
    resp = await _complete(client, auth, inv["id"], ticket["media_id"], {})
    assert resp.status_code == 400
    assert _error_code(resp) == "invalid_upload"


async def test_complete_body_is_strict(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    ticket = (await _request_upload(client, auth, inv["id"])).json()
    fake_storage.simulate_upload(ticket["upload_url"], 1000, "image/jpeg")
    for body, expected in [
        ({"width": "1600"}, [("width", "invalid_format")]),
        ({"width": 0}, [("width", "out_of_range")]),
        ({"height": 20001}, [("height", "out_of_range")]),
        ({"depth": 1}, [("depth", "unknown_field")]),
    ]:
        resp = await _complete(client, auth, inv["id"], ticket["media_id"], body)
        assert _details(resp) == expected, body


# ---------- File âm thanh: không album, không kích thước ----------


async def test_audio_has_no_album(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    album_id = await _album(client, auth, inv["id"])
    for target in (album_id, str(uuid.uuid4())):  # lỗi 422 của body đi trước 404 album
        resp = await _request_upload(
            client, auth, inv["id"], content_type="audio/mpeg", album_id=target
        )
        assert _details(resp) == [("album_id", "invalid_reference")]
        assert _messages(resp) == ["File âm thanh không nằm trong album"]

    audio = await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg")
    url = f"/invitations/{inv['id']}/media/{audio['id']}"
    moved = await client.patch(url, json={"album_id": album_id}, headers=auth)
    assert _details(moved) == [("album_id", "invalid_reference")]
    out = await client.patch(url, json={"album_id": None}, headers=auth)
    assert out.status_code == 200, out.text
    assert out.json()["album_id"] is None


async def test_audio_complete_rejects_image_size(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    ticket = (await _request_upload(client, auth, inv["id"], content_type="audio/mpeg")).json()
    fake_storage.simulate_upload(ticket["upload_url"], 1000, "audio/mpeg")
    media_id = ticket["media_id"]

    both = await _complete(client, auth, inv["id"], media_id, {"width": 1600, "height": 900})
    assert _details(both) == [("width", "invalid_format"), ("height", "invalid_format")]
    assert _messages(both) == ["File âm thanh không có kích thước ảnh"] * 2
    height = await _complete(client, auth, inv["id"], media_id, {"height": 900})
    assert _details(height) == [("height", "invalid_format")]
    assert await _list(client, auth, inv["id"]) == []  # vẫn pending

    done = await _complete(client, auth, inv["id"], media_id, {"width": None, "height": None})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "ready"
    # Đã ready: gửi kích thước vẫn bị từ chối, không gửi thì trả file như cũ
    again = await _complete(client, auth, inv["id"], media_id, {"width": 1})
    assert _details(again) == [("width", "invalid_format")]
    assert (await _complete(client, auth, inv["id"], media_id, {})).json() == done.json()


# ---------- Giới hạn số lượng ----------


async def test_one_audio_file_per_invitation(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    audio = await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg")

    second = await _request_upload(client, auth, inv["id"], content_type="audio/x-m4a")
    assert second.status_code == 400
    assert _error_code(second) == "media_limit"
    assert second.json()["error"]["message"] == "Mỗi thiệp tối đa 1 file âm thanh"

    # Giới hạn âm thanh không chặn ảnh
    await upload_media(client, auth, fake_storage, inv["id"])

    # Đổi nhạc: xoá file cũ rồi upload file mới
    url = f"/invitations/{inv['id']}/media/{audio['id']}"
    assert (await client.delete(url, headers=auth)).status_code == 204
    await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/x-m4a")


async def test_pending_audio_counts_toward_limit(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    # Đã xin link nhưng chưa PUT, chưa xác nhận
    ticket = (await _request_upload(client, auth, inv["id"], content_type="audio/mpeg")).json()
    second = await _request_upload(client, auth, inv["id"], content_type="audio/mpeg")
    assert second.status_code == 400
    assert _error_code(second) == "media_limit"

    # FE xoá bản pending bằng media_id đã nhận thì xin link mới được
    url = f"/invitations/{inv['id']}/media/{ticket['media_id']}"
    assert (await client.delete(url, headers=auth)).status_code == 204
    third = await _request_upload(client, auth, inv["id"], content_type="audio/mpeg")
    assert third.status_code == 200, third.text


async def test_image_limit_counts_images_only(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _invitation(client, auth)
    await _add_images(session_maker, inv["id"], 199)
    await _add_images(session_maker, inv["id"], 1, status="pending")  # pending cũng tính

    resp = await _request_upload(client, auth, inv["id"])
    assert resp.status_code == 400
    assert _error_code(resp) == "media_limit"
    assert resp.json()["error"]["message"] == "Mỗi thiệp tối đa 200 ảnh"

    audio = await _request_upload(client, auth, inv["id"], content_type="audio/mpeg")
    assert audio.status_code == 200, audio.text


async def test_concurrent_audio_requests_do_not_exceed_limit(
    client: AsyncClient, templates, auth, session_maker
) -> None:
    inv = await _invitation(client, auth)
    responses = await asyncio.gather(
        *(_request_upload(client, auth, inv["id"], content_type="audio/mpeg") for _ in range(4))
    )
    assert sorted(r.status_code for r in responses) == [200, 400, 400, 400]
    assert {_error_code(r) for r in responses if r.status_code == 400} == {"media_limit"}
    assert await _media_count(session_maker, inv["id"], "audio") == 1


# ---------- Danh sách, thứ tự ----------


async def test_listing_and_positions_include_audio(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    album_id = await _album(client, auth, inv["id"])
    first = await upload_media(client, auth, fake_storage, inv["id"], album_id=album_id)
    audio = await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mp3")
    second = await upload_media(client, auth, fake_storage, inv["id"])

    # Ảnh đánh số riêng trong các ảnh; âm thanh luôn ở vị trí 0
    assert (first["position"], audio["position"], second["position"]) == (0, 0, 1)
    listed = await _list(client, auth, inv["id"])
    assert [(m["id"], m["kind"]) for m in listed] == [
        (first["id"], "image"),
        (audio["id"], "audio"),
        (second["id"], "image"),
    ]
    assert [m["id"] for m in await _list(client, auth, inv["id"], album_id=album_id)] == [
        first["id"]
    ]


async def test_reorder_and_delete(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    ids = [(await upload_media(client, auth, fake_storage, inv["id"]))["id"] for _ in range(3)]

    reordered = await client.put(
        f"/invitations/{inv['id']}/media/order", json={"media_ids": ids[::-1]}, headers=auth
    )
    assert reordered.status_code == 200, reordered.text
    assert [m["id"] for m in await _list(client, auth, inv["id"])] == ids[::-1]

    invalid = await client.put(
        f"/invitations/{inv['id']}/media/order",
        json={"media_ids": [ids[0], "00000000-0000-0000-0000-000000000000"]},
        headers=auth,
    )
    assert invalid.status_code == 400

    deleted = await client.delete(f"/invitations/{inv['id']}/media/{ids[0]}", headers=auth)
    assert deleted.status_code == 204
    assert any(ids[0] in key for key in fake_storage.deleted)
    assert len(await _list(client, auth, inv["id"])) == 2


async def test_reorder_accepts_only_images(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    first = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    second = (await upload_media(client, auth, fake_storage, inv["id"]))["id"]
    audio = (await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg"))[
        "id"
    ]
    url = f"/invitations/{inv['id']}/media/order"

    resp = await client.put(url, json={"media_ids": [second, audio, first]}, headers=auth)
    assert resp.status_code == 400
    assert _error_code(resp) == "invalid_media_ids"
    assert [m["id"] for m in await _list(client, auth, inv["id"])] == [first, audio, second]

    ok = await client.put(url, json={"media_ids": [second, first]}, headers=auth)
    assert [(m["id"], m["position"]) for m in ok.json()] == [(second, 0), (first, 1)]


async def test_reorder_and_update_bodies_are_strict(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    media = await upload_media(client, auth, fake_storage, inv["id"])
    order_url = f"/invitations/{inv['id']}/media/order"
    for body, expected in [
        ({"media_ids": []}, [("media_ids", "out_of_range")]),
        ({"media_ids": [media["id"].upper()]}, [("media_ids[0]", "invalid_format")]),
        ({"media_ids": None}, [("media_ids", "required")]),
        ({"media_ids": [media["id"]], "x": 1}, [("x", "unknown_field")]),
    ]:
        assert _details(await client.put(order_url, json=body, headers=auth)) == expected, body

    media_url = f"/invitations/{inv['id']}/media/{media['id']}"
    for body, expected in [
        ({"album_id": "khong-phai-uuid"}, [("album_id", "invalid_format")]),
        ({"position": 1}, [("position", "unknown_field")]),
    ]:
        assert _details(await client.patch(media_url, json=body, headers=auth)) == expected, body


# ---------- Album ----------


async def test_album_schemas_are_strict_and_normalized(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _invitation(client, auth)
    url = f"/invitations/{inv['id']}/albums"
    for body, expected in [
        ({"title": ""}, [("title", "required")]),
        ({"title": None}, [("title", "required")]),
        ({}, [("title", "required")]),
        ({"title": "a\nb"}, [("title", "invalid_characters")]),
        ({"title": "x" * 121}, [("title", "too_long")]),
        ({"title": "A", "position": 1}, [("position", "unknown_field")]),
    ]:
        assert _details(await client.post(url, json=body, headers=auth)) == expected, body

    nfd = unicodedata.normalize("NFD", "  Ngày   cưới ")
    created = await client.post(url, json={"title": nfd}, headers=auth)
    assert created.status_code == 201, created.text
    album = created.json()
    assert set(album) == {"id", "title", "position", "media_count", "created_at"}
    assert album["title"] == "Ngày cưới"

    album_url = f"{url}/{album['id']}"
    for body, expected in [
        ({"title": None}, [("title", "required")]),
        ({"title": " "}, [("title", "required")]),
        ({"position": None}, [("position", "required")]),
        ({"position": "1"}, [("position", "invalid_format")]),
        ({"position": -1}, [("position", "out_of_range")]),
    ]:
        resp = await client.patch(album_url, json=body, headers=auth)
        assert _details(resp) == expected, body

    unchanged = await client.patch(album_url, json={}, headers=auth)
    assert unchanged.json() == album
    renamed = await client.patch(album_url, json={"title": " Mới "}, headers=auth)
    assert (renamed.json()["title"], renamed.json()["position"]) == ("Mới", album["position"])


async def test_delete_album_keeps_media(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    album_id = await _album(client, auth, inv["id"], "Ngày cưới")
    media = await upload_media(client, auth, fake_storage, inv["id"], album_id=album_id)

    resp = await client.delete(f"/invitations/{inv['id']}/albums/{album_id}", headers=auth)
    assert resp.status_code == 204
    listed = await _list(client, auth, inv["id"])
    assert listed[0]["id"] == media["id"]
    assert listed[0]["album_id"] is None


async def test_move_media_between_albums(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    album_id = await _album(client, auth, inv["id"])
    media = await upload_media(client, auth, fake_storage, inv["id"])

    url = f"/invitations/{inv['id']}/media/{media['id']}"
    moved = await client.patch(url, json={"album_id": album_id}, headers=auth)
    assert moved.json()["album_id"] == album_id
    out = await client.patch(url, json={"album_id": None}, headers=auth)
    assert out.json()["album_id"] is None


# ---------- Khác ----------


async def test_public_gallery_has_only_images(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    """Trang public: `gallery` chỉ có ảnh; `media_by_id` có cả âm thanh (tests/test_public.py)."""
    inv = await _invitation(client, auth)
    image = await upload_media(client, auth, fake_storage, inv["id"])
    audio = await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg")
    event = await client.post(
        f"/invitations/{inv['id']}/events",
        json={
            "event_type": "reception",
            "host_side": "both",
            "event_date": "2026-12-20",
            "start_time": "11:00",
            "address": "Nhà hàng ABC, Hà Nội",
        },
        headers={**auth, "If-Match": f'"{inv["revision"]}"'},
    )
    assert event.status_code == 201, event.text
    assert (await client.post(f"/invitations/{inv['id']}/publish", headers=auth)).status_code == 200
    public = (await client.get(f"/public/invitations/{inv['slug']}")).json()
    assert [item["media_id"] for item in public["gallery"]] == [image["id"]]
    assert {key: value["kind"] for key, value in public["media_by_id"].items()} == {
        image["id"]: "image",
        audio["id"]: "audio",
    }


async def test_delete_invitation_cleans_storage(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    image = await upload_media(client, auth, fake_storage, inv["id"])
    audio = await upload_media(client, auth, fake_storage, inv["id"], content_type="audio/mpeg")
    assert (await client.delete(f"/invitations/{inv['id']}", headers=auth)).status_code == 204
    assert any(image["id"] in key for key in fake_storage.deleted)
    assert any(audio["id"] in key for key in fake_storage.deleted)


async def test_other_user_cannot_upload(client: AsyncClient, templates, auth, other_auth) -> None:
    inv = await _invitation(client, auth)
    resp = await _request_upload(client, other_auth, inv["id"])
    assert resp.status_code == 404
    # Thiệp được nạp bằng dependency OwnedInvitation, chạy trước khi validate body: 404 trước 422
    invalid = await _request_upload(client, other_auth, inv["id"], content_type="image/gif")
    assert invalid.status_code == 404
    assert _error_code(invalid) == "invitation_not_found"
