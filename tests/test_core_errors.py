"""Bước 1: định dạng lỗi chung (spec 05 › Định dạng lỗi), kể cả lỗi 422."""

import unicodedata
from collections.abc import AsyncIterator
from enum import StrEnum

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import Field

from app.core.errors import AppError, bad_request, register_error_handlers
from app.core.schemas import StrictModel
from app.core.types import Choice, MultiLine, RequiredSingleLine, SingleLine


class Side(StrEnum):
    groom = "groom"
    bride = "bride"


class LoveStoryItem(StrictModel):
    title: RequiredSingleLine(100)
    body: MultiLine(2000) = None


class SampleContent(StrictModel):
    greeting: MultiLine(2000) = None
    love_story: list[LoveStoryItem] = Field(default_factory=list, max_length=3)


class SampleCreate(StrictModel):
    name: SingleLine(50) = None
    guest_count: int = Field(default=0, ge=0)
    content: SampleContent = Field(default_factory=SampleContent)


def build_app() -> FastAPI:
    """App riêng cho test: không thêm endpoint thật vào app chính."""
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/samples")
    async def create_sample(payload: SampleCreate) -> dict:
        return payload.model_dump(mode="json")

    @app.get("/samples")
    async def list_samples(side: Choice(Side) | None = None) -> dict:
        return {"side": side}

    @app.get("/business-error")
    async def business_error() -> None:
        raise bad_request("missing_couple_names", "Cần nhập tên cô dâu và chú rể")

    @app.get("/business-error-with-details")
    async def business_error_with_details() -> None:
        raise AppError(
            400,
            "not_ready_to_publish",
            "Thiệp chưa đủ điều kiện để đăng",
            details=[
                {
                    "field": "content.couple.groom.full_name",
                    "code": "required",
                    "message": "Không được để trống",
                }
            ],
        )

    return app


@pytest.fixture
async def sample_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=build_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def validation_body(*details: dict[str, str]) -> dict:
    return {
        "error": {
            "code": "validation_error",
            "message": "Dữ liệu không hợp lệ",
            "details": list(details),
        }
    }


# ---------- Lỗi 422 ----------


async def test_validation_error_has_common_format_and_list_path(
    sample_client: AsyncClient,
) -> None:
    resp = await sample_client.post(
        "/samples", json={"content": {"love_story": [{"title": "Gặp nhau"}, {"title": "  "}]}}
    )

    assert resp.status_code == 422
    assert resp.json() == validation_body(
        {
            "field": "content.love_story[1].title",
            "code": "required",
            "message": "Không được để trống",
        }
    )


async def test_validation_error_lists_every_field(sample_client: AsyncClient) -> None:
    resp = await sample_client.post(
        "/samples",
        json={
            "name": "Nam\nLan",
            "guest_count": "2",
            "slug": "nam-lan",
            "content": {"theme": {}, "love_story": [{"title": "T", "photo_url": "x"}]},
        },
    )

    assert resp.status_code == 422
    found = resp.json()["error"]["details"]
    assert {(d["field"], d["code"]) for d in found} == {
        ("name", "invalid_characters"),
        ("guest_count", "invalid_format"),
        ("slug", "unknown_field"),
        ("content.theme", "unknown_field"),
        ("content.love_story[0].photo_url", "unknown_field"),
    }
    assert all(isinstance(d["message"], str) and d["message"] for d in found)


async def test_string_number_is_rejected(sample_client: AsyncClient) -> None:
    resp = await sample_client.post("/samples", json={"guest_count": "2"})

    assert resp.status_code == 422
    assert resp.json() == validation_body(
        {"field": "guest_count", "code": "invalid_format", "message": "Phải là số nguyên"}
    )


async def test_limits_use_out_of_range_and_too_long(sample_client: AsyncClient) -> None:
    resp = await sample_client.post(
        "/samples",
        json={"guest_count": -1, "content": {"love_story": [{"title": "T"}] * 4}},
    )

    assert resp.status_code == 422
    assert resp.json() == validation_body(
        {
            "field": "guest_count",
            "code": "out_of_range",
            "message": "Phải lớn hơn hoặc bằng 0",
        },
        {"field": "content.love_story", "code": "too_long", "message": "Tối đa 3 phần tử"},
    )


async def test_request_body_is_normalized(sample_client: AsyncClient) -> None:
    resp = await sample_client.post(
        "/samples",
        json={
            "name": unicodedata.normalize("NFD", "  Trần   Thị Lan "),
            "content": {"greeting": "   ", "love_story": [{"title": "Gặp nhau", "body": ""}]},
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Trần Thị Lan"
    assert unicodedata.is_normalized("NFC", body["name"])
    assert body["content"]["greeting"] is None
    assert body["content"]["love_story"] == [{"title": "Gặp nhau", "body": None}]


async def test_malformed_json_has_root_field(sample_client: AsyncClient) -> None:
    resp = await sample_client.post(
        "/samples", content=b'{"name": ', headers={"content-type": "application/json"}
    )

    assert resp.status_code == 422
    assert resp.json() == validation_body(
        {"field": "", "code": "invalid_format", "message": "JSON không hợp lệ"}
    )


async def test_body_not_object_has_root_field(sample_client: AsyncClient) -> None:
    resp = await sample_client.post("/samples", json=[1, 2])

    assert resp.status_code == 422
    assert resp.json() == validation_body(
        {"field": "", "code": "invalid_format", "message": "Phải là object"}
    )


async def test_missing_body_has_root_field(sample_client: AsyncClient) -> None:
    resp = await sample_client.post("/samples")

    assert resp.status_code == 422
    assert resp.json() == validation_body(
        {"field": "", "code": "required", "message": "Không được để trống"}
    )


async def test_query_param_error_uses_param_name(sample_client: AsyncClient) -> None:
    ok = await sample_client.get("/samples", params={"side": "bride"})
    assert ok.json() == {"side": "bride"}

    resp = await sample_client.get("/samples", params={"side": "both"})

    assert resp.status_code == 422
    [detail] = resp.json()["error"]["details"]
    assert detail["field"] == "side"
    assert detail["code"] == "invalid_choice"


async def test_main_app_uses_validation_format(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "123", "full_name": "A"},
    )

    assert resp.status_code == 422
    assert resp.json() == validation_body(
        {"field": "password", "code": "out_of_range", "message": "Tối thiểu 8 ký tự"}
    )


# ---------- Lỗi khác dùng chung định dạng ----------


async def test_app_error_has_empty_details(sample_client: AsyncClient) -> None:
    resp = await sample_client.get("/business-error")

    assert resp.status_code == 400
    assert resp.json() == {
        "error": {
            "code": "missing_couple_names",
            "message": "Cần nhập tên cô dâu và chú rể",
            "details": [],
        }
    }


async def test_app_error_keeps_details(sample_client: AsyncClient) -> None:
    resp = await sample_client.get("/business-error-with-details")

    assert resp.status_code == 400
    assert resp.json()["error"]["details"] == [
        {
            "field": "content.couple.groom.full_name",
            "code": "required",
            "message": "Không được để trống",
        }
    ]


async def test_unknown_route_uses_common_format(sample_client: AsyncClient) -> None:
    resp = await sample_client.get("/khong-co")

    assert resp.status_code == 404
    assert resp.json() == {
        "error": {"code": "not_found", "message": "Không tìm thấy", "details": []}
    }


async def test_wrong_method_uses_common_format(sample_client: AsyncClient) -> None:
    resp = await sample_client.delete("/business-error")

    assert resp.status_code == 405
    assert resp.json() == {
        "error": {
            "code": "method_not_allowed",
            "message": "Phương thức không được hỗ trợ",
            "details": [],
        }
    }
    assert resp.headers["allow"] == "GET"


def test_openapi_shows_text_limits() -> None:
    schemas = build_app().openapi()["components"]["schemas"]

    name = schemas["SampleCreate"]["properties"]["name"]
    assert {"type": "string", "maxLength": 50} in name["anyOf"]
    assert schemas["LoveStoryItem"]["properties"]["title"]["maxLength"] == 100
