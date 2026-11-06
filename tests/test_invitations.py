from httpx import AsyncClient

CONTENT = {
    "couple": {
        "groom": {"full_name": "Nguyễn Văn Nam", "short_name": "Nam"},
        "bride": {"full_name": "Trần Thị Lan", "short_name": "Lan"},
    },
    "events": [
        {
            "kind": "reception",
            "title": "Tiệc cưới",
            "starts_at": "2026-12-20T11:00:00+07:00",
            "venue_name": "Trung tâm tiệc cưới Hoa Sen",
            "address": "123 Đường Láng, Hà Nội",
        }
    ],
    "custom_field_of_template": {"anything": True},
}


async def _create(client: AsyncClient, auth: dict, **overrides) -> dict:
    payload = {"template_key": "classic_01", "content": CONTENT, **overrides}
    resp = await client.post("/invitations", json=payload, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_list_templates_hides_inactive(client: AsyncClient, templates) -> None:
    resp = await client.get("/templates")
    assert resp.status_code == 200
    keys = {t["key"] for t in resp.json()}
    assert keys == {"classic_01", "minimal_01", "vintage_01"}

    assert (await client.get("/templates/old_01")).status_code == 404
    classic = await client.get("/templates?category=classic")
    assert [t["key"] for t in classic.json()] == ["classic_01"]


async def test_create_generates_slug_and_title(
    client: AsyncClient, templates, auth
) -> None:
    first = await _create(client, auth)
    assert first["slug"] == "nam-lan"
    assert first["title"] == "Nam & Lan"
    assert first["status"] == "draft"
    assert first["template_key"] == "classic_01"
    assert first["content"]["custom_field_of_template"] == {"anything": True}

    second = await _create(client, auth)
    assert second["slug"].startswith("nam-lan-")
    assert second["slug"] != first["slug"]


async def test_create_with_custom_slug(client: AsyncClient, templates, auth, other_auth) -> None:
    created = await _create(client, auth, slug="  Nam-Lan-2026 ")
    assert created["slug"] == "nam-lan-2026"

    taken = await client.post(
        "/invitations",
        json={"template_key": "classic_01", "slug": "nam-lan-2026"},
        headers=other_auth,
    )
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "slug_taken"

    for bad in ["dashboard", "có-dấu", "a", "nam--lan"]:
        resp = await client.post(
            "/invitations", json={"template_key": "classic_01", "slug": bad}, headers=auth
        )
        assert resp.status_code == 422, bad


async def test_slug_availability(client: AsyncClient, templates, auth) -> None:
    await _create(client, auth)
    taken = await client.get("/invitations/slug-availability?slug=nam-lan", headers=auth)
    assert taken.json() == {
        "slug": "nam-lan",
        "available": False,
        "reason": "Đường dẫn đã có người dùng",
    }
    free = await client.get("/invitations/slug-availability?slug=hung-mai", headers=auth)
    assert free.json()["available"] is True
    reserved = await client.get("/invitations/slug-availability?slug=admin", headers=auth)
    assert reserved.json()["available"] is False


async def test_create_rejects_premium_and_unknown_template(
    client: AsyncClient, templates, auth
) -> None:
    premium = await client.post("/invitations", json={"template_key": "vintage_01"}, headers=auth)
    assert premium.status_code == 400
    assert premium.json()["error"]["code"] == "template_premium"

    unknown = await client.post("/invitations", json={"template_key": "khong-co"}, headers=auth)
    assert unknown.status_code == 404


async def test_invitation_limit(client: AsyncClient, templates, auth, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_invitations_per_user", 1)
    await _create(client, auth)
    resp = await client.post("/invitations", json={"template_key": "classic_01"}, headers=auth)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invitation_limit"


async def test_update_invitation(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    new_content = {**CONTENT, "greeting": "Trân trọng kính mời"}

    resp = await client.patch(
        f"/invitations/{inv['id']}",
        json={"template_key": "minimal_01", "slug": "nam-va-lan", "content": new_content},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["template_key"] == "minimal_01"
    assert body["slug"] == "nam-va-lan"
    assert body["content"]["greeting"] == "Trân trọng kính mời"
    assert body["title"] == "Nam & Lan"  # không gửi thì giữ nguyên

    premium = await client.patch(
        f"/invitations/{inv['id']}", json={"template_key": "vintage_01"}, headers=auth
    )
    assert premium.status_code == 400


async def test_other_user_cannot_access(client: AsyncClient, templates, auth, other_auth) -> None:
    inv = await _create(client, auth)
    url = f"/invitations/{inv['id']}"
    assert (await client.get(url, headers=other_auth)).status_code == 404
    assert (await client.patch(url, json={"title": "X"}, headers=other_auth)).status_code == 404
    assert (await client.delete(url, headers=other_auth)).status_code == 404
    assert (await client.get("/invitations", headers=other_auth)).json() == []
    assert len((await client.get("/invitations", headers=auth)).json()) == 1


async def test_publish_flow_and_public_page(client: AsyncClient, templates, auth) -> None:
    empty = await _create(client, auth, content={}, slug="thiep-trong")
    resp = await client.post(f"/invitations/{empty['id']}/publish", headers=auth)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "missing_couple_names"

    inv = await _create(client, auth)
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
    assert body["content"]["couple"]["groom"]["short_name"] == "Nam"
    assert body["albums"] == [] and body["media"] == []
    assert "owner_id" not in body

    unpublished = await client.post(f"/invitations/{inv['id']}/unpublish", headers=auth)
    assert unpublished.json()["status"] == "draft"
    assert (await client.get("/public/invitations/nam-lan")).status_code == 404


async def test_delete_invitation(client: AsyncClient, templates, auth) -> None:
    inv = await _create(client, auth)
    assert (await client.delete(f"/invitations/{inv['id']}", headers=auth)).status_code == 204
    assert (await client.get(f"/invitations/{inv['id']}", headers=auth)).status_code == 404
