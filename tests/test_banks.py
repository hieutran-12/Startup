"""Bước 8: danh sách ngân hàng (file tĩnh), GET /banks, kiểm tra gifts.

Spec: 03 › Nội dung thiệp (gifts); 05 › Endpoint mới (GET /banks); 02 › Mã định danh toàn chữ số.
9 đề xuất được duyệt 2026-11-06 (docs/modules/banks.md): đủ 76 mục của VietQR, chỉ bin, short_name,
name, giữ thứ tự nguồn; GET /banks không cần đăng nhập; BIN lạ → 422 invalid_choice, kiểm tra mỗi
lần content được kiểm tra theo request; đọc content đã lưu thì không kiểm tra.
"""

import json
import unicodedata
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.banks.service import (
    BANKS_FILE,
    BankListError,
    is_known_bin,
    list_banks,
    load_banks,
)
from app.modules.invitations.models import Invitation

RAW_BANKS: list[dict[str, Any]] = json.loads(BANKS_FILE.read_text(encoding="utf-8"))

UNKNOWN_BIN = "123456"  # 6 chữ số nhưng không có trong danh sách
UNKNOWN_BIN_MESSAGE = "Không có ngân hàng với mã BIN này"

GIFT = {
    "recipient_side": "groom",
    "bank_bin": "970436",
    "account_number": "0123456789",
    "account_holder": "NGUYEN VAN NAM",
}

VCB = {"bin": "970436", "short_name": "Vietcombank", "name": "Ngân hàng TMCP Ngoại Thương Việt Nam"}
VCB_NFD = {**VCB, "name": unicodedata.normalize("NFD", VCB["name"])}


# ---------- Helper ----------


async def _create(client: AsyncClient, auth: dict, **payload: Any) -> Response:
    return await client.post(
        "/invitations", json={"template_key": "classic_01", **payload}, headers=auth
    )


async def _create_ok(client: AsyncClient, auth: dict, **payload: Any) -> dict:
    resp = await _create(client, auth, **payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _patch(client: AsyncClient, auth: dict, inv: dict, body: Any) -> Response:
    headers = {**auth, "If-Match": f'"{inv["revision"]}"'}
    return await client.patch(f"/invitations/{inv['id']}", json=body, headers=headers)


async def _patch_ok(client: AsyncClient, auth: dict, inv: dict, body: Any) -> dict:
    resp = await _patch(client, auth, inv, body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _get(client: AsyncClient, auth: dict, inv: dict) -> dict:
    resp = await client.get(f"/invitations/{inv['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _details(resp: Response) -> list[tuple[str, str]]:
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"
    return [(d["field"], d["code"]) for d in resp.json()["error"]["details"]]


def _write(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "banks.json"
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path


# ---------- File tĩnh ----------


def test_bank_file_rows_have_three_normalized_fields() -> None:
    assert isinstance(RAW_BANKS, list)
    assert RAW_BANKS
    for row in RAW_BANKS:
        assert set(row) == {"bin", "short_name", "name"}, row
        bin_ = row["bin"]
        assert isinstance(bin_, str), row
        assert len(bin_) == 6, row
        assert bin_.isascii(), row
        assert bin_.isdigit(), row
        for field in ("short_name", "name"):
            value = row[field]
            assert isinstance(value, str), row
            assert value, row
            # Đã chuẩn hóa như SingleLine: NFC, trim, không có khoảng trắng liền nhau
            assert value == " ".join(unicodedata.normalize("NFC", value).split()), (bin_, field)
    bins = [row["bin"] for row in RAW_BANKS]
    assert len(bins) == len(set(bins))


def test_bank_file_is_the_whole_vietqr_list_in_source_order() -> None:
    by_bin = {row["bin"]: row for row in RAW_BANKS}
    assert len(RAW_BANKS) == 76  # api.vietqr.io/v2/banks ngày 2026-11-06
    assert [row["short_name"] for row in RAW_BANKS[:4]] == [
        "VietinBank",
        "Vietcombank",
        "BIDV",
        "Agribank",
    ]
    assert by_bin["970436"] == VCB  # tên ở nguồn là NFD, file lưu NFC
    # Không lọc theo cờ transferSupported: ví điện tử và ngân hàng có cờ 0 vẫn có mặt
    assert {"971025", "971101", "458761", "533948"} <= set(by_bin)  # MoMo, ZaloPay, HSBC, Citibank
    # short_name giữ đúng cách viết của nguồn
    assert by_bin["970454"]["short_name"] == "VietCapitalBank"
    # Nguồn có khoảng trắng thừa trong tên MAFC
    assert by_bin["977777"]["name"] == "Công ty Tài chính TNHH MTV Mirae Asset (Việt Nam)"


def test_list_banks_returns_file_rows_in_order() -> None:
    assert [bank.model_dump() for bank in list_banks()] == RAW_BANKS
    assert is_known_bin("970436")
    assert is_known_bin("971025")
    assert not is_known_bin(UNKNOWN_BIN)


def test_load_banks_accepts_valid_file(tmp_path: Path) -> None:
    other = {"bin": "970418", "short_name": "BIDV", "name": "Ngân hàng TMCP Đầu tư và Phát triển"}
    banks = load_banks(_write(tmp_path, [VCB, other]))
    assert [bank.model_dump() for bank in banks] == [VCB, other]


def _without(field: str) -> dict[str, Any]:
    return {key: value for key, value in VCB.items() if key != field}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("[{", [(None, "", "invalid_format")]),
        ({"banks": [VCB]}, [(None, "", "invalid_format")]),
        ([], [(None, "", "out_of_range")]),
        (["970436"], [(0, "", "invalid_format")]),
        ([_without("name")], [(0, "name", "required")]),
        ([{**VCB, "logo": "https://cdn.test/vcb.png"}], [(0, "logo", "unknown_field")]),
        ([{**VCB, "bin": "97043"}], [(0, "bin", "invalid_format")]),
        ([{**VCB, "bin": 970436}], [(0, "bin", "invalid_format")]),
        ([{**VCB, "short_name": "  "}], [(0, "short_name", "required")]),
        ([VCB_NFD], [(0, "name", "invalid_format")]),
        ([{**VCB, "name": VCB["name"] + " "}], [(0, "name", "invalid_format")]),
        ([{**VCB, "short_name": "Vietcom  bank"}], [(0, "short_name", "invalid_format")]),
        ([VCB, {**VCB, "short_name": "VCB"}], [(1, "bin", "invalid_format")]),
    ],
)
def test_load_banks_rejects_broken_file(
    tmp_path: Path, data: Any, expected: list[tuple[int | None, str, str]]
) -> None:
    with pytest.raises(BankListError) as exc:
        load_banks(_write(tmp_path, data))
    assert [(e["index"], e["field"], e["code"]) for e in exc.value.errors] == expected


# ---------- GET /banks ----------


async def test_get_banks_needs_no_login(client: AsyncClient) -> None:
    resp = await client.get("/banks")
    assert resp.status_code == 200, resp.text
    assert resp.json() == RAW_BANKS


# ---------- Kiểm tra gifts.bank_bin ----------


async def test_create_rejects_bank_bin_not_in_list(client: AsyncClient, templates, auth) -> None:
    resp = await _create(client, auth, content={"gifts": [{**GIFT, "bank_bin": UNKNOWN_BIN}]})
    assert _details(resp) == [("content.gifts[0].bank_bin", "invalid_choice")]
    assert resp.json()["error"]["details"][0]["message"] == UNKNOWN_BIN_MESSAGE
    listed = await client.get("/invitations", headers=auth)
    assert listed.json() == []


async def test_patch_rejects_bank_bin_not_in_list(client: AsyncClient, templates, auth) -> None:
    inv = await _create_ok(client, auth)
    gifts = [GIFT, {**GIFT, "recipient_side": "bride", "bank_bin": UNKNOWN_BIN}]
    resp = await _patch(client, auth, inv, {"content": {"gifts": gifts}})
    assert _details(resp) == [("content.gifts[1].bank_bin", "invalid_choice")]
    after = await _get(client, auth, inv)
    assert after["revision"] == 1
    assert after["content"]["gifts"] == []


async def test_bank_bin_error_comes_with_other_content_errors(
    client: AsyncClient, templates, auth
) -> None:
    inv = await _create_ok(client, auth)
    patch = {
        "content": {
            "couple": {"groom": {"birth_order": "truong_nam"}},
            "love_story": [{"title": "A", "month": 3}],
            "gifts": [{**GIFT, "bank_bin": UNKNOWN_BIN, "account_number": "0123 456"}],
        }
    }
    assert sorted(_details(await _patch(client, auth, inv, patch))) == [
        ("content.couple.groom.birth_order", "invalid_choice"),
        ("content.gifts[0].account_number", "invalid_format"),
        ("content.gifts[0].bank_bin", "invalid_choice"),
        ("content.love_story[0].year", "required"),
    ]


@pytest.mark.parametrize("bank_bin", ["97043a", "97043", "9704361", "９７０４３６"])
async def test_bank_bin_with_wrong_format_only_reports_format(
    client: AsyncClient, templates, auth, bank_bin: str
) -> None:
    inv = await _create_ok(client, auth)
    resp = await _patch(client, auth, inv, {"content": {"gifts": [{**GIFT, "bank_bin": bank_bin}]}})
    assert _details(resp) == [("content.gifts[0].bank_bin", "invalid_format")]


async def test_every_bin_in_list_is_accepted(client: AsyncClient, templates, auth) -> None:
    # MoMo, ZaloPay (ví điện tử), HSBC, Citibank (cờ transferSupported = 0 ở VietQR)
    bins = ["971025", "971101", "458761", "533948"]
    gifts = [{**GIFT, "bank_bin": bank_bin} for bank_bin in bins]
    inv = await _create_ok(client, auth, content={"gifts": gifts})
    assert [gift["bank_bin"] for gift in inv["content"]["gifts"]] == bins


async def test_stored_unknown_bin_is_checked_on_next_content_validation(
    client: AsyncClient, templates, auth, session_maker: async_sessionmaker
) -> None:
    """BIN bị bỏ khỏi file sau khi đã lưu: thiệp vẫn đọc được, lần sửa content kế tiếp bị 422."""
    inv = await _create_ok(client, auth, content={"gifts": [GIFT]})
    stored = {**inv["content"], "gifts": [{**GIFT, "bank_bin": UNKNOWN_BIN}]}
    async with session_maker() as db:
        await db.execute(
            update(Invitation).where(Invitation.id == uuid.UUID(inv["id"])).values(content=stored)
        )
        await db.commit()

    current = await _get(client, auth, inv)
    assert current["content"]["gifts"][0]["bank_bin"] == UNKNOWN_BIN

    # Không đụng tới content: không kiểm tra
    current = await _patch_ok(client, auth, current, {"title": "Thiệp mới"})

    expected = [("content.gifts[0].bank_bin", "invalid_choice")]
    greeting = {"content": {"messages": {"greeting": "Chào bạn"}}}
    assert _details(await _patch(client, auth, current, greeting)) == expected
    assert _details(await _patch(client, auth, current, {"template_key": "minimal_01"})) == expected

    fixed = await _patch_ok(client, auth, current, {"content": {"gifts": [GIFT]}})
    assert fixed["content"]["gifts"] == [GIFT]


# ---------- Số tài khoản (spec 02 › Mã định danh toàn chữ số) ----------


@pytest.mark.parametrize(
    "account_number",
    [
        "01234abc89",  # chữ cái
        "0123 456789",  # dấu cách ở giữa
        "0123 456789",  # NBSP
        "0123\t456789",
        "0123.456789",  # giao diện phải bỏ dấu chấm trước khi gửi
        "0123-456789",
        "０１２３４５６７８９",  # chữ số full-width
    ],
)
async def test_account_number_with_letters_or_spaces_is_rejected(
    client: AsyncClient, templates, auth, account_number: str
) -> None:
    gift = {**GIFT, "account_number": account_number}
    resp = await _create(client, auth, content={"gifts": [gift]})
    assert _details(resp) == [("content.gifts[0].account_number", "invalid_format")]


async def test_account_number_is_trimmed_and_keeps_leading_zero(
    client: AsyncClient, templates, auth
) -> None:
    gift = {**GIFT, "account_number": " 000123456789 "}
    inv = await _create_ok(client, auth, content={"gifts": [gift]})
    assert inv["content"]["gifts"][0]["account_number"] == "000123456789"
