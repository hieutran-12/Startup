"""Trang public `GET /public/invitations/{slug}` (Bước 10).

Spec: 05 › Response của trang public; 04 › Link theo bên, Sự kiện, Ngày âm lịch; 03. 4 đề xuất
được duyệt 2026-11-06 (docs/modules/invitations.md): `side` chỉ nhận đúng `groom`/`bride`, sai thì
422 `invalid_choice` trước khi tìm slug; `gallery` là mọi ảnh ready theo `position, created_at`,
không loại ảnh đang dùng, không cắt theo `max_gallery_images`; `albums` gồm cả album rỗng;
`content` có kiểu `InvitationContent`, đọc không context.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Template
from app.modules.events.models import Event
from tests.conftest import FakeStorage, make_manifest, upload_media

SLUG = "nam-lan"

NAMES = {
    "groom": {"full_name": "Nguyễn Văn Nam", "display_name": "Nam"},
    "bride": {"full_name": "Lê Thị Lan", "display_name": "Lan"},
}

GROOM_GIFT = {
    "recipient_side": "groom",
    "bank_bin": "970436",
    "account_number": "0123456789",
    "account_holder": "NGUYEN VAN NAM",
}
BRIDE_GIFT = {
    "recipient_side": "bride",
    "bank_bin": "970415",
    "account_number": "9876543210",
    "account_holder": "LE THI LAN",
}
GROOM_GIFT_2 = {
    "recipient_side": "groom",
    "bank_bin": "970418",
    "account_number": "111122223333",
    "account_holder": "NGUYEN VAN HUNG",
}

# Tạo theo thứ tự này (không phải thứ tự hiển thị) để kiểm tra sắp xếp
RECEPTION = {
    "event_type": "reception",
    "host_side": "both",
    "event_name": "Tiệc cưới tại Hà Nội",
    "event_date": "2026-12-20",
    "start_time": "11:00",
    "end_time": "14:00",
    "venue_name": "Nhà hàng ABC",
    "address": "12 Láng Hạ, Đống Đa, Hà Nội",
    "latitude": 21.016,
    "longitude": 105.8189,
    "maps_url": "https://maps.app.goo.gl/abc",
}
THANH_HON = {
    "event_type": "family_ceremony",
    "host_side": "groom",
    "event_date": "2026-12-20",
    "start_time": "08:00",
    "address": "Số 12 ngõ 34 Láng Hạ, Hà Nội",
}
VU_QUY = {
    "event_type": "family_ceremony",
    "host_side": "bride",
    "event_date": "2026-12-19",
    "start_time": "08:00",
    "address": "Số 5 Trần Phú, Nam Định",
}
AN_HOI = {
    "event_type": "engagement",
    "host_side": "bride",
    "event_date": "2025-07-25",
    "start_time": "09:00",
    "address": "Số 5 Trần Phú, Nam Định",
}

# Thứ tự hiển thị: ngày, rồi giờ bắt đầu
ALL_NAMES = ["Lễ ăn hỏi", "Lễ vu quy", "Lễ thành hôn", "Tiệc cưới tại Hà Nội"]
BRIDE_NAMES = ["Lễ ăn hỏi", "Lễ vu quy", "Tiệc cưới tại Hà Nội"]
GROOM_NAMES = ["Lễ thành hôn", "Tiệc cưới tại Hà Nội"]

# Đối chiếu ở tests/test_lunar.py (xemlicham.com, lichvannien365.com)
LUNAR = {
    "2025-07-25": {"day": 1, "month": 6, "year": 2025, "is_leap_month": True, "year_name": "Ất Tỵ"},
    "2026-12-19": {
        "day": 11,
        "month": 11,
        "year": 2026,
        "is_leap_month": False,
        "year_name": "Bính Ngọ",
    },
    "2026-12-20": {
        "day": 12,
        "month": 11,
        "year": 2026,
        "is_leap_month": False,
        "year_name": "Bính Ngọ",
    },
}

PUBLIC_FIELDS = {
    "slug",
    "template_key",
    "side",
    "content_schema_version",
    "content",
    "cover_media_id",
    "groom_photo_media_id",
    "bride_photo_media_id",
    "music_media_id",
    "events",
    "albums",
    "gallery",
    "media_by_id",
    "published_at",
    "updated_at",
}

# Mọi cột của bảng events trừ invitation_id, position; thêm display_name, lunar_date
PUBLIC_EVENT_FIELDS = {
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
    "lunar_date",
    "created_at",
    "updated_at",
}

CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"


# ---------- Helper ----------


async def _if_match(client: AsyncClient, auth: dict, invitation_id: str) -> dict:
    resp = await client.get(f"/invitations/{invitation_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return {**auth, "If-Match": resp.headers["ETag"]}


async def _public(client: AsyncClient, side: str | None = None, slug: str = SLUG) -> Response:
    params = {} if side is None else {"side": side}
    return await client.get(f"/public/invitations/{slug}", params=params)


async def _public_ok(client: AsyncClient, side: str | None = None) -> dict[str, Any]:
    resp = await _public(client, side)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _names(body: dict) -> list[str]:
    return [event["display_name"] for event in body["events"]]


@pytest.fixture
async def published(
    client: AsyncClient, templates, auth, fake_storage: FakeStorage
) -> dict[str, Any]:
    """Thiệp đã publish: 4 sự kiện của hai bên, 3 tài khoản, 2 album (1 rỗng), 2 ảnh, 1 nhạc,
    1 file pending. Ảnh A trong album, làm ảnh bìa; ảnh B ngoài album, làm chân dung chú rể và
    ảnh love_story; thư viện xếp lại thành B, A."""
    content = {
        "couple": NAMES,
        "messages": {"greeting": "Cảm ơn bạn đã là một phần trong câu chuyện của chúng mình."},
        "gifts": [GROOM_GIFT, BRIDE_GIFT, GROOM_GIFT_2],
    }
    resp = await client.post(
        "/invitations",
        json={"template_key": "classic_01", "slug": SLUG, "content": content},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    inv_id = resp.json()["id"]
    base = f"/invitations/{inv_id}"

    albums = []
    for title in ("Pre-wedding", "Trống"):
        album = await client.post(f"{base}/albums", json={"title": title}, headers=auth)
        assert album.status_code == 201, album.text
        albums.append(album.json())

    image_a = await upload_media(
        client, auth, fake_storage, inv_id, filename="a", album_id=albums[0]["id"]
    )
    image_b = await upload_media(
        client, auth, fake_storage, inv_id, filename="b", complete={"width": 800, "height": 1200}
    )
    audio = await upload_media(client, auth, fake_storage, inv_id, content_type="audio/mpeg")
    pending = await client.post(
        f"{base}/media/upload-url",
        json={"filename": "p", "content_type": "image/jpeg", "size_bytes": 1000},
        headers=auth,
    )
    assert pending.status_code == 200, pending.text

    order = await client.put(
        f"{base}/media/order", json={"media_ids": [image_b["id"], image_a["id"]]}, headers=auth
    )
    assert order.status_code == 200, order.text

    patch = {
        "cover_media_id": image_a["id"],
        "groom_photo_media_id": image_b["id"],
        "music_media_id": audio["id"],
        "content": {
            "love_story": [
                {"title": "Lần đầu gặp nhau", "year": 2019, "month": 3, "media_id": image_b["id"]}
            ]
        },
    }
    patched = await client.patch(base, json=patch, headers=await _if_match(client, auth, inv_id))
    assert patched.status_code == 200, patched.text

    for event in (RECEPTION, THANH_HON, VU_QUY, AN_HOI):
        created = await client.post(
            f"{base}/events", json=event, headers=await _if_match(client, auth, inv_id)
        )
        assert created.status_code == 201, created.text

    published = await client.post(f"{base}/publish", headers=auth)
    assert published.status_code == 200, published.text

    events = await client.get(f"{base}/events", headers=auth)
    return {
        "invitation": published.json(),
        "events": events.json(),
        "albums": albums,
        "image_a": image_a,
        "image_b": image_b,
        "audio": audio,
        "pending_id": pending.json()["media_id"],
    }


# ---------- Lọc theo side (tiêu chí nghiệm thu) ----------


async def test_side_bride_hides_groom_events_and_gifts(
    client: AsyncClient, auth, published
) -> None:
    resp = await _public(client, "bride")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["side"] == "bride"
    assert _names(body) == BRIDE_NAMES
    assert {event["host_side"] for event in body["events"]} == {"bride", "both"}
    assert body["content"]["gifts"] == [BRIDE_GIFT]

    # Không có owner_id, kể cả dưới dạng giá trị ở bất kỳ đâu trong response
    assert "owner_id" not in body
    owner_id = (await client.get("/me", headers=auth)).json()["id"]
    assert owner_id not in resp.text


async def test_side_groom_hides_bride_events_and_gifts(client: AsyncClient, published) -> None:
    body = await _public_ok(client, "groom")
    assert body["side"] == "groom"
    assert _names(body) == GROOM_NAMES
    assert {event["host_side"] for event in body["events"]} == {"groom", "both"}
    assert body["content"]["gifts"] == [GROOM_GIFT, GROOM_GIFT_2]


async def test_without_side_returns_every_event_and_gift(client: AsyncClient, published) -> None:
    body = await _public_ok(client)
    assert body["side"] is None
    assert _names(body) == ALL_NAMES
    assert body["content"]["gifts"] == [GROOM_GIFT, BRIDE_GIFT, GROOM_GIFT_2]


async def test_side_without_gifts_of_that_side(
    client: AsyncClient, auth, published
) -> None:
    inv = published["invitation"]
    patched = await client.patch(
        f"/invitations/{inv['id']}",
        json={"content": {"gifts": [GROOM_GIFT]}},
        headers=await _if_match(client, auth, inv["id"]),
    )
    assert patched.status_code == 200, patched.text
    assert (await _public_ok(client, "bride"))["content"]["gifts"] == []
    assert (await _public_ok(client, "groom"))["content"]["gifts"] == [GROOM_GIFT]


@pytest.mark.parametrize("side", ["both", "Groom", "BRIDE", "", " groom", "nha-trai"])
async def test_invalid_side_is_422(client: AsyncClient, published, side: str) -> None:
    for slug in (SLUG, "khong-co-thiep-nay"):  # kiểm tra side trước khi tìm slug
        resp = await _public(client, side, slug=slug)
        assert resp.status_code == 422, resp.text
        error = resp.json()["error"]
        assert error["code"] == "validation_error"
        assert [(d["field"], d["code"]) for d in error["details"]] == [("side", "invalid_choice")]


# ---------- Cấu trúc response ----------


async def test_response_fields(client: AsyncClient, published) -> None:
    inv = published["invitation"]
    for side in (None, "groom", "bride"):
        body = await _public_ok(client, side)
        assert set(body) == PUBLIC_FIELDS
        assert body["slug"] == SLUG
        assert body["template_key"] == "classic_01"
        assert body["content_schema_version"] == 1
        assert body["published_at"] == inv["published_at"]
        assert body["updated_at"] == inv["updated_at"]
        for event in body["events"]:
            assert set(event) == PUBLIC_EVENT_FIELDS
        for album in body["albums"]:
            assert set(album) == {"id", "title", "position"}
        for item in body["gallery"]:
            assert set(item) == {"media_id", "album_id"}
        for media in body["media_by_id"].values():
            assert set(media) == {"kind", "url", "width", "height"}


async def test_cache_control_and_draft(client: AsyncClient, auth, published) -> None:
    for side in (None, "groom", "bride"):
        resp = await _public(client, side)
        assert resp.headers["cache-control"] == CACHE_CONTROL
    # Slug hạ chữ thường như khung
    assert (await client.get(f"/public/invitations/{SLUG.upper()}")).status_code == 200

    inv = published["invitation"]
    unpublished = await client.post(f"/invitations/{inv['id']}/unpublish", headers=auth)
    assert unpublished.status_code == 200, unpublished.text
    for side in (None, "groom", "bride"):
        resp = await _public(client, side)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "invitation_not_found"


# ---------- Sự kiện ----------


async def test_events_have_columns_display_name_and_lunar_date(
    client: AsyncClient, published
) -> None:
    """Mỗi sự kiện = EventResponse của dashboard bỏ `position`, thêm `lunar_date`."""
    owner_events = {event["id"]: event for event in published["events"]}
    body = await _public_ok(client)
    assert [event["id"] for event in body["events"]] == [e["id"] for e in published["events"]]
    for event in body["events"]:
        expected = {k: v for k, v in owner_events[event["id"]].items() if k != "position"}
        expected["lunar_date"] = LUNAR[event["event_date"]]
        assert event == expected

    reception = body["events"][-1]
    assert reception["display_name"] == "Tiệc cưới tại Hà Nội"
    assert reception["start_time"] == "11:00" and reception["end_time"] == "14:00"
    assert reception["latitude"] == 21.016 and reception["longitude"] == 105.8189
    assert reception["timezone"] == "Asia/Ho_Chi_Minh"
    # Tên mặc định theo loại lễ và bên khi event_name là null
    assert [(e["event_name"], e["display_name"]) for e in body["events"][:3]] == [
        (None, "Lễ ăn hỏi"),
        (None, "Lễ vu quy"),
        (None, "Lễ thành hôn"),
    ]
    assert body["events"][0]["lunar_date"]["is_leap_month"] is True


async def test_lunar_date_is_null_without_event_date(
    client: AsyncClient, published, session_maker: async_sessionmaker
) -> None:
    """Thiệp đã publish luôn có ngày ở mọi sự kiện; ghi thẳng DB để thử nhánh không có ngày."""
    async with session_maker() as db:
        db.add(
            Event(
                invitation_id=uuid.UUID(published["invitation"]["id"]),
                event_type="other",
                host_side="bride",
                event_name="Lễ lại mặt",
            )
        )
        await db.commit()
    body = await _public_ok(client, "bride")
    last = body["events"][-1]  # chưa có ngày thì xếp cuối
    assert last["display_name"] == "Lễ lại mặt"
    assert last["event_date"] is None and last["lunar_date"] is None
    assert _names(await _public_ok(client, "groom")) == GROOM_NAMES


# ---------- Content ----------


async def test_content_is_stored_content_except_gifts(
    client: AsyncClient, auth, published
) -> None:
    inv_id = published["invitation"]["id"]
    stored = (await client.get(f"/invitations/{inv_id}", headers=auth)).json()["content"]
    assert (await _public_ok(client))["content"] == stored
    for side in ("groom", "bride"):
        expected = {
            **stored,
            "gifts": [gift for gift in stored["gifts"] if gift["recipient_side"] == side],
        }
        assert (await _public_ok(client, side))["content"] == expected


# ---------- Media ----------


async def test_media_columns_and_media_by_id(client: AsyncClient, published) -> None:
    image_a, image_b, audio = published["image_a"], published["image_b"], published["audio"]
    body = await _public_ok(client)
    assert body["cover_media_id"] == image_a["id"]
    assert body["groom_photo_media_id"] == image_b["id"]
    assert body["bride_photo_media_id"] is None
    assert body["music_media_id"] == audio["id"]
    assert body["content"]["love_story"][0]["media_id"] == image_b["id"]

    # Mọi file ready (ảnh và âm thanh), không có file pending
    assert body["media_by_id"] == {
        image_a["id"]: {"kind": "image", "url": image_a["url"], "width": 1600, "height": 1067},
        image_b["id"]: {"kind": "image", "url": image_b["url"], "width": 800, "height": 1200},
        audio["id"]: {"kind": "audio", "url": audio["url"], "width": None, "height": None},
    }
    assert published["pending_id"] not in body["media_by_id"]
    assert body["media_by_id"] == (await _public_ok(client, "bride"))["media_by_id"]


async def test_gallery_and_albums(client: AsyncClient, published) -> None:
    image_a, image_b = published["image_a"], published["image_b"]
    pre_wedding, empty = published["albums"]
    body = await _public_ok(client)
    # Thứ tự theo PUT /media/order; gồm cả ảnh đang làm ảnh bìa, chân dung; không có âm thanh
    assert body["gallery"] == [
        {"media_id": image_b["id"], "album_id": None},
        {"media_id": image_a["id"], "album_id": pre_wedding["id"]},
    ]
    # Mọi album, kể cả album rỗng
    assert body["albums"] == [
        {"id": pre_wedding["id"], "title": "Pre-wedding", "position": 0},
        {"id": empty["id"], "title": "Trống", "position": 1},
    ]


async def test_gallery_is_not_cut_by_max_gallery_images(
    client: AsyncClient, published, session_maker: async_sessionmaker
) -> None:
    async with session_maker() as db:
        await db.execute(
            update(Template)
            .where(Template.key == "classic_01")
            .values(manifest=make_manifest(max_gallery_images=1))
        )
        await db.commit()
    assert len((await _public_ok(client))["gallery"]) == 2


async def test_gallery_follows_reorder(
    client: AsyncClient, auth, published
) -> None:
    image_a, image_b = published["image_a"], published["image_b"]
    inv_id = published["invitation"]["id"]
    order = await client.put(
        f"/invitations/{inv_id}/media/order",
        json={"media_ids": [image_a["id"], image_b["id"]]},
        headers=auth,
    )
    assert order.status_code == 200, order.text
    gallery = (await _public_ok(client))["gallery"]
    assert [item["media_id"] for item in gallery] == [image_a["id"], image_b["id"]]
