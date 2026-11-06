from httpx import AsyncClient

from tests.conftest import FakeStorage

CONTENT = {"couple": {"groom": {"short_name": "Hùng"}, "bride": {"short_name": "Mai"}}}


async def _invitation(client: AsyncClient, auth: dict) -> dict:
    resp = await client.post(
        "/invitations", json={"template_key": "classic_01", "content": CONTENT}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload(
    client: AsyncClient,
    auth: dict,
    storage: FakeStorage,
    invitation_id: str,
    *,
    album_id: str | None = None,
    size: int = 500_000,
) -> dict:
    """Mô phỏng đủ 3 bước FE sẽ làm: xin link, PUT file, xác nhận."""
    ticket = await client.post(
        f"/invitations/{invitation_id}/media/upload-url",
        json={
            "filename": "anh-cuoi.jpg",
            "content_type": "image/jpeg",
            "size_bytes": size,
            "album_id": album_id,
        },
        headers=auth,
    )
    assert ticket.status_code == 200, ticket.text
    data = ticket.json()
    assert data["method"] == "PUT"
    assert data["headers"] == {"Content-Type": "image/jpeg"}

    storage.simulate_upload(data["upload_url"], size, "image/jpeg")

    done = await client.post(
        f"/invitations/{invitation_id}/media/{data['media_id']}/complete",
        json={"width": 1600, "height": 1067},
        headers=auth,
    )
    assert done.status_code == 200, done.text
    return done.json()


async def test_full_upload_flow(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    album = await client.post(
        f"/invitations/{inv['id']}/albums", json={"title": "Pre-wedding"}, headers=auth
    )
    assert album.status_code == 201
    album_id = album.json()["id"]

    media = await _upload(client, auth, fake_storage, inv["id"], album_id=album_id)
    assert media["status"] == "ready"
    assert media["album_id"] == album_id
    assert media["width"] == 1600
    assert media["url"].startswith(f"https://cdn.test/invitations/{inv['id']}/")
    assert media["url"].endswith(".jpg")

    listed = await client.get(f"/invitations/{inv['id']}/media", headers=auth)
    assert [m["id"] for m in listed.json()] == [media["id"]]

    albums = await client.get(f"/invitations/{inv['id']}/albums", headers=auth)
    assert albums.json()[0]["media_count"] == 1

    # Gọi /complete lần nữa vẫn trả về ảnh, không lỗi
    again = await client.post(
        f"/invitations/{inv['id']}/media/{media['id']}/complete", json={}, headers=auth
    )
    assert again.status_code == 200

    await client.post(f"/invitations/{inv['id']}/publish", headers=auth)
    public = (await client.get(f"/public/invitations/{inv['slug']}")).json()
    assert public["albums"][0]["title"] == "Pre-wedding"
    assert public["media"][0]["url"] == media["url"]
    assert public["media"][0]["album_id"] == album_id


async def test_upload_validation(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    url = f"/invitations/{inv['id']}/media/upload-url"

    pdf = await client.post(
        url,
        json={"filename": "a.pdf", "content_type": "application/pdf", "size_bytes": 100},
        headers=auth,
    )
    assert pdf.status_code == 400
    assert pdf.json()["error"]["code"] == "unsupported_file_type"

    huge = await client.post(
        url,
        json={"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 999_999_999},
        headers=auth,
    )
    assert huge.status_code == 400
    assert huge.json()["error"]["code"] == "file_too_large"


async def test_complete_requires_uploaded_file(client: AsyncClient, templates, auth) -> None:
    inv = await _invitation(client, auth)
    ticket = await client.post(
        f"/invitations/{inv['id']}/media/upload-url",
        json={"filename": "a.png", "content_type": "image/png", "size_bytes": 1000},
        headers=auth,
    )
    media_id = ticket.json()["media_id"]
    resp = await client.post(
        f"/invitations/{inv['id']}/media/{media_id}/complete", json={}, headers=auth
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "upload_not_found"

    # Ảnh chưa xác nhận không hiện trong danh sách
    assert (await client.get(f"/invitations/{inv['id']}/media", headers=auth)).json() == []


async def test_complete_rejects_oversized_file(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    ticket = (
        await client.post(
            f"/invitations/{inv['id']}/media/upload-url",
            json={"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 1000},
            headers=auth,
        )
    ).json()
    # Khai báo 1KB nhưng thực tế PUT lên 100MB
    key = fake_storage.simulate_upload(ticket["upload_url"], 100 * 1024 * 1024, "image/jpeg")

    resp = await client.post(
        f"/invitations/{inv['id']}/media/{ticket['media_id']}/complete", json={}, headers=auth
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_upload"
    assert key in fake_storage.deleted


async def test_reorder_and_delete(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    ids = [(await _upload(client, auth, fake_storage, inv["id"]))["id"] for _ in range(3)]

    reordered = await client.put(
        f"/invitations/{inv['id']}/media/order", json={"media_ids": ids[::-1]}, headers=auth
    )
    assert reordered.status_code == 200, reordered.text
    listed = await client.get(f"/invitations/{inv['id']}/media", headers=auth)
    assert [m["id"] for m in listed.json()] == ids[::-1]

    invalid = await client.put(
        f"/invitations/{inv['id']}/media/order",
        json={"media_ids": [ids[0], "00000000-0000-0000-0000-000000000000"]},
        headers=auth,
    )
    assert invalid.status_code == 400

    deleted = await client.delete(f"/invitations/{inv['id']}/media/{ids[0]}", headers=auth)
    assert deleted.status_code == 204
    assert any(ids[0] in key for key in fake_storage.deleted)
    remaining = await client.get(f"/invitations/{inv['id']}/media", headers=auth)
    assert len(remaining.json()) == 2


async def test_delete_album_keeps_media(client: AsyncClient, templates, auth, fake_storage) -> None:
    inv = await _invitation(client, auth)
    album_id = (
        await client.post(
            f"/invitations/{inv['id']}/albums", json={"title": "Ngày cưới"}, headers=auth
        )
    ).json()["id"]
    media = await _upload(client, auth, fake_storage, inv["id"], album_id=album_id)

    resp = await client.delete(f"/invitations/{inv['id']}/albums/{album_id}", headers=auth)
    assert resp.status_code == 204
    listed = (await client.get(f"/invitations/{inv['id']}/media", headers=auth)).json()
    assert listed[0]["id"] == media["id"]
    assert listed[0]["album_id"] is None


async def test_move_media_between_albums(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    album_id = (
        await client.post(f"/invitations/{inv['id']}/albums", json={"title": "A"}, headers=auth)
    ).json()["id"]
    media = await _upload(client, auth, fake_storage, inv["id"])

    moved = await client.patch(
        f"/invitations/{inv['id']}/media/{media['id']}", json={"album_id": album_id}, headers=auth
    )
    assert moved.json()["album_id"] == album_id
    out = await client.patch(
        f"/invitations/{inv['id']}/media/{media['id']}", json={"album_id": None}, headers=auth
    )
    assert out.json()["album_id"] is None


async def test_delete_invitation_cleans_storage(
    client: AsyncClient, templates, auth, fake_storage
) -> None:
    inv = await _invitation(client, auth)
    media = await _upload(client, auth, fake_storage, inv["id"])
    assert (await client.delete(f"/invitations/{inv['id']}", headers=auth)).status_code == 204
    assert any(media["id"] in key for key in fake_storage.deleted)


async def test_other_user_cannot_upload(client: AsyncClient, templates, auth, other_auth) -> None:
    inv = await _invitation(client, auth)
    resp = await client.post(
        f"/invitations/{inv['id']}/media/upload-url",
        json={"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 100},
        headers=other_auth,
    )
    assert resp.status_code == 404
