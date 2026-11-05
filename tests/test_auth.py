from datetime import timedelta

from httpx import AsyncClient

from app.modules.auth import service as auth_service
from tests.conftest import register_user


def _refresh_cookie(resp) -> str:
    token = resp.cookies.get("refresh_token")
    assert token, "Thiếu cookie refresh_token"
    return token


async def _refresh_with(client: AsyncClient, token: str):
    client.cookies.clear()
    return await client.post("/auth/refresh", headers={"Cookie": f"refresh_token={token}"})


async def test_register_sets_cookie_and_returns_user(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": "  Nam@Example.com ", "password": "matkhau123", "full_name": "Nam"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == "nam@example.com"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "path=/auth" in set_cookie

    me = await client.get("/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "nam@example.com"


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await register_user(client, email="nam@example.com")
    resp = await client.post(
        "/auth/register",
        json={"email": "NAM@example.com", "password": "matkhau123", "full_name": "Nam 2"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_taken"


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register", json={"email": "a@example.com", "password": "123", "full_name": "A"}
    )
    assert resp.status_code == 422


async def test_login(client: AsyncClient) -> None:
    await register_user(client, email="lan@example.com", password="matkhau123")

    wrong = await client.post(
        "/auth/login", json={"email": "lan@example.com", "password": "saimatkhau"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"

    unknown = await client.post(
        "/auth/login", json={"email": "khongco@example.com", "password": "matkhau123"}
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "invalid_credentials"

    ok = await client.post(
        "/auth/login", json={"email": "LAN@example.com", "password": "matkhau123"}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]


async def test_me_requires_valid_token(client: AsyncClient) -> None:
    assert (await client.get("/me")).status_code == 401
    bad = await client.get("/me", headers={"Authorization": "Bearer khong-hop-le"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_token"


async def test_refresh_rotates_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "matkhau123", "full_name": "A"},
    )
    first = _refresh_cookie(resp)

    refreshed = await _refresh_with(client, first)
    assert refreshed.status_code == 200, refreshed.text
    second = _refresh_cookie(refreshed)
    assert second != first

    # Token cũ dùng lại ngay (trong khoảng ân hạn) chỉ bị từ chối, không thu hồi phiên
    again = await _refresh_with(client, first)
    assert again.status_code == 401
    assert again.json()["error"]["code"] == "refresh_token_rotated"
    assert (await _refresh_with(client, second)).status_code == 200


async def test_refresh_reuse_revokes_all_sessions(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "REUSE_GRACE_PERIOD", timedelta(0))
    resp = await client.post(
        "/auth/register",
        json={"email": "b@example.com", "password": "matkhau123", "full_name": "B"},
    )
    first = _refresh_cookie(resp)
    second = _refresh_cookie(await _refresh_with(client, first))

    reused = await _refresh_with(client, first)
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "refresh_token_reused"
    # Token mới nhất cũng bị thu hồi theo
    assert (await _refresh_with(client, second)).status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": "c@example.com", "password": "matkhau123", "full_name": "C"},
    )
    token = _refresh_cookie(resp)

    client.cookies.clear()
    out = await client.post("/auth/logout", headers={"Cookie": f"refresh_token={token}"})
    assert out.status_code == 204
    assert (await _refresh_with(client, token)).status_code == 401


async def test_refresh_without_cookie(client: AsyncClient) -> None:
    client.cookies.clear()
    resp = await client.post("/auth/refresh")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "missing_refresh_token"
