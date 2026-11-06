"""Bước 1: kiểu chuẩn hóa trong app/core/types.py và StrictModel.

Validate ở chế độ Python (model_validate) vì FastAPI cũng validate body như vậy.
"""

import json
import unicodedata
import uuid
from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.errors import error_details
from app.core.schemas import StrictModel
from app.core.types import (
    Choice,
    Digits,
    Email,
    HttpUrl,
    IsoDate,
    Latitude,
    LocalTime,
    Longitude,
    MultiLine,
    Password,
    RequiredDigits,
    RequiredMultiLine,
    RequiredSingleLine,
    SingleLine,
    Timezone,
    Uuid,
)


class Side(StrEnum):
    groom = "groom"
    bride = "bride"


class Sample(StrictModel):
    # Trường bắt buộc có default chỉ để mỗi test gửi riêng trường cần kiểm tra
    name: SingleLine(30) = None
    short_name: SingleLine(6) = None
    title: RequiredSingleLine(30) = "Mặc định"
    story: MultiLine(50) = None
    note: RequiredMultiLine(50) = "Mặc định"
    account_number: Digits(6, 19) = None
    bank_bin: RequiredDigits(6, 6) = "970436"
    start_time: LocalTime | None = None
    timezone: Timezone = "Asia/Ho_Chi_Minh"
    media_id: Uuid | None = None
    event_date: IsoDate | None = None
    side: Choice(Side) | None = None
    guest_count: int | None = None
    is_visible: bool = False
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    maps_url: HttpUrl(40) = None


class RequiredOnly(StrictModel):
    title: RequiredSingleLine(30)


class Account(StrictModel):
    email: Email
    password: Password(8, 12)


def parse(**data: Any) -> Sample:
    return Sample.model_validate(data)


def details(data: dict[str, Any], model: type[StrictModel] = Sample) -> list[dict[str, str]]:
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(data)
    return error_details(exc_info.value.errors())


def errors(data: dict[str, Any], model: type[StrictModel] = Sample) -> list[tuple[str, str]]:
    return [(d["field"], d["code"]) for d in details(data, model)]


# ---------- Chuẩn hóa Unicode ----------


def test_single_line_nfd_is_stored_as_nfc() -> None:
    raw = unicodedata.normalize("NFD", "Nguyễn Thị Ánh")
    assert raw != "Nguyễn Thị Ánh"

    result = parse(name=raw).name

    assert result == "Nguyễn Thị Ánh"
    assert unicodedata.is_normalized("NFC", result)


def test_multi_line_nfd_is_stored_as_nfc() -> None:
    raw = unicodedata.normalize("NFD", "Ngày ấy\nchúng mình gặp nhau")

    assert parse(story=raw).story == "Ngày ấy\nchúng mình gặp nhau"


# ---------- Rỗng và bắt buộc ----------


@pytest.mark.parametrize("raw", ["", "   ", " \t\n ", " "])
def test_empty_optional_string_becomes_null(raw: str) -> None:
    sample = parse(name=raw, story=raw, account_number=raw)

    assert sample.name is None
    assert sample.story is None
    assert sample.account_number is None


@pytest.mark.parametrize("raw", ["", "   ", None])
@pytest.mark.parametrize("field", ["title", "note", "bank_bin", "timezone"])
def test_empty_or_null_required_string_is_rejected(field: str, raw: str | None) -> None:
    assert details({field: raw}) == [
        {"field": field, "code": "required", "message": "Không được để trống"}
    ]


def test_missing_required_field_is_rejected() -> None:
    assert errors({}, RequiredOnly) == [("title", "required")]


# ---------- Văn bản một dòng ----------


def test_single_line_trims_and_collapses_spaces() -> None:
    assert parse(name="  Nguyễn   Văn  Nam  ").name == "Nguyễn Văn Nam"


def test_single_line_trims_line_breaks_at_both_ends() -> None:
    assert parse(name="\n Nam \r\n").name == "Nam"


@pytest.mark.parametrize(
    "raw", ["Nam\nLan", "Nam\r\nLan", "Nam\tLan", "Nam\x00", "Nam\x1b[0m", "Nam Lan"]
)
def test_single_line_rejects_line_breaks_and_control_characters(raw: str) -> None:
    assert errors({"name": raw}) == [("name", "invalid_characters")]


def test_length_is_counted_after_normalization() -> None:
    nfd = unicodedata.normalize("NFD", "Nguyễn")
    assert len(nfd) > 6

    assert parse(short_name=nfd).short_name == "Nguyễn"
    assert parse(short_name="  Ng    ễn  ").short_name == "Ng ễn"


def test_single_line_too_long() -> None:
    assert details({"short_name": "Nguyễnn"}) == [
        {"field": "short_name", "code": "too_long", "message": "Tối đa 6 ký tự"}
    ]


def test_text_rejects_non_string() -> None:
    assert errors({"name": 123}) == [("name", "invalid_format")]


# ---------- Văn bản nhiều dòng ----------


def test_multi_line_normalizes_line_endings() -> None:
    assert parse(story="Dòng 1\r\nDòng 2\rDòng 3\nDòng 4").story == "Dòng 1\nDòng 2\nDòng 3\nDòng 4"


def test_multi_line_trims_both_ends() -> None:
    assert parse(story="\r\n\n  Xin chào  \n\n").story == "Xin chào"


def test_multi_line_keeps_at_most_two_blank_lines() -> None:
    assert parse(story="A\n\nB").story == "A\n\nB"
    assert parse(story="A\n\n\nB").story == "A\n\n\nB"
    assert parse(story="A\n\n\n\n\n\nB").story == "A\n\n\nB"
    assert parse(story="A\r\n\r\n\r\n\r\nB").story == "A\n\n\nB"
    # Dòng chỉ có khoảng trắng cũng là dòng trống
    assert parse(story="A\n  \n\n\t\n\nB").story == "A\n  \n\nB"


def test_multi_line_allows_tab() -> None:
    assert parse(story="Thơ:\n\tcâu một").story == "Thơ:\n\tcâu một"


@pytest.mark.parametrize("raw", ["A\x00B", "A\x07B", "A\x0bB", "A B", "A\u0085B"])
def test_multi_line_rejects_other_control_characters(raw: str) -> None:
    assert errors({"story": raw}) == [("story", "invalid_characters")]


def test_multi_line_too_long() -> None:
    assert errors({"story": "a" * 51}) == [("story", "too_long")]
    assert parse(story="a" * 50 + "\n\n\n\n").story == "a" * 50


# ---------- Chuỗi chữ số ----------


def test_digits_keep_leading_zero_as_string() -> None:
    sample = parse(account_number=" 0123456789 ", bank_bin="970436")

    assert sample.account_number == "0123456789"
    assert sample.bank_bin == "970436"


@pytest.mark.parametrize(
    "raw", ["0123 456", "01234a6", "12345", "1" * 20, "０１２３４５６", "-123456", 1234567]
)
def test_digits_reject_non_digits_and_wrong_length(raw: Any) -> None:
    assert errors({"account_number": raw}) == [("account_number", "invalid_format")]


@pytest.mark.parametrize("raw", ["97043", "9704366"])
def test_fixed_length_digits(raw: str) -> None:
    assert details({"bank_bin": raw}) == [
        {"field": "bank_bin", "code": "invalid_format", "message": "Phải gồm đúng 6 chữ số"}
    ]


# ---------- Giờ HH:MM ----------


@pytest.mark.parametrize(
    ("raw", "expected"), [("09:30", time(9, 30)), ("00:00", time(0, 0)), ("23:59", time(23, 59))]
)
def test_local_time_accepts_hh_mm(raw: str, expected: time) -> None:
    sample = parse(start_time=raw)

    assert sample.start_time == expected
    assert sample.model_dump(mode="json")["start_time"] == raw


@pytest.mark.parametrize(
    "raw", ["9:30", "24:00", "09:60", "09:30:00", "11h", "09h30", " 09:30", "", 930]
)
def test_local_time_rejects_other_formats(raw: Any) -> None:
    assert details({"start_time": raw}) == [
        {"field": "start_time", "code": "invalid_format", "message": "Giờ phải có dạng HH:MM"}
    ]


# ---------- Múi giờ ----------


@pytest.mark.parametrize("raw", ["Asia/Ho_Chi_Minh", " Asia/Ho_Chi_Minh ", "Europe/Paris", "UTC"])
def test_timezone_accepts_iana_name(raw: str) -> None:
    assert parse(timezone=raw).timezone == raw.strip()


@pytest.mark.parametrize("raw", ["asia/ho_chi_minh", "Asia/Hanoi", "UTC+7", "GMT+07:00"])
def test_timezone_rejects_unknown_name(raw: str) -> None:
    assert errors({"timezone": raw}) == [("timezone", "invalid_choice")]


# ---------- Tọa độ ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (21.028511, Decimal("21.028511")),
        (21, Decimal("21")),
        (0, Decimal("0")),
        (-90, Decimal("-90")),
        (90.0, Decimal("90.0")),
        (-0.000001, Decimal("-0.000001")),
    ],
)
def test_latitude_accepts_json_number(raw: Any, expected: Decimal) -> None:
    sample = parse(latitude=raw)

    assert isinstance(sample.latitude, Decimal)
    assert sample.latitude == expected
    # Trả ra JSON là số, không phải chuỗi
    assert json.loads(sample.model_dump_json())["latitude"] == float(expected)


def test_coordinate_accepts_decimal_from_database() -> None:
    assert parse(longitude=Decimal("105.804817")).longitude == Decimal("105.804817")


@pytest.mark.parametrize("raw", [-180, 180, 105.804817])
def test_longitude_accepts_full_range(raw: Any) -> None:
    assert parse(longitude=raw).longitude == Decimal(str(raw))


@pytest.mark.parametrize(
    "raw", ["21.028511", "21", "", True, False, float("nan"), float("inf"), [21], {"lat": 21}]
)
def test_coordinate_rejects_non_numbers(raw: Any) -> None:
    assert details({"latitude": raw}) == [
        {"field": "latitude", "code": "invalid_format", "message": "Tọa độ phải là số"}
    ]


@pytest.mark.parametrize("raw", [21.0285111, 0.0000001, Decimal("21.0285111")])
def test_coordinate_rejects_more_than_six_decimal_places(raw: Any) -> None:
    assert details({"latitude": raw}) == [
        {
            "field": "latitude",
            "code": "invalid_format",
            "message": "Tối đa 6 chữ số sau dấu thập phân",
        }
    ]


@pytest.mark.parametrize(
    ("field", "raw", "message"),
    [
        ("latitude", 90.000001, "Vĩ độ phải trong khoảng -90 đến 90"),
        ("latitude", -91, "Vĩ độ phải trong khoảng -90 đến 90"),
        ("latitude", 1e300, "Vĩ độ phải trong khoảng -90 đến 90"),
        ("longitude", 180.5, "Kinh độ phải trong khoảng -180 đến 180"),
        ("longitude", -181, "Kinh độ phải trong khoảng -180 đến 180"),
    ],
)
def test_coordinate_out_of_range(field: str, raw: Any, message: str) -> None:
    assert details({field: raw}) == [{"field": field, "code": "out_of_range", "message": message}]


def test_coordinate_null_is_allowed() -> None:
    assert parse(latitude=None).latitude is None


# ---------- URL ----------


@pytest.mark.parametrize(
    "raw",
    [
        "https://maps.app.goo.gl/abc",
        "http://example.com",
        "HTTPS://Example.com/a?b=c#d",
        "https://maps.google.com/?q=Hà_Nội",
        "https://[::1]:8080/x",
    ],
)
def test_http_url_is_kept_as_sent(raw: str) -> None:
    assert parse(maps_url=raw).maps_url == raw


def test_http_url_is_trimmed_and_nfc() -> None:
    raw = unicodedata.normalize("NFD", "  https://x.vn/Hà  ")
    assert parse(maps_url=raw).maps_url == "https://x.vn/Hà"


@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_http_url_becomes_null(raw: str) -> None:
    assert parse(maps_url=raw).maps_url is None


@pytest.mark.parametrize(
    "raw",
    [
        "maps.google.com",
        "ftp://example.com",
        "javascript:alert(1)",
        "mailto:nam@example.com",
        "https:example.com",
        "//example.com",
        "https://",
        "https:///path",
        "http://exa mple.com",
        "https://example.com/a\nb",
        "https://example.com/\u00a0x",
        "https://[::1/x",
        123,
    ],
)
def test_http_url_rejects_other_values(raw: Any) -> None:
    assert errors({"maps_url": raw}) == [("maps_url", "invalid_format")]


def test_http_url_too_long() -> None:
    assert details({"maps_url": "https://example.com/" + "a" * 21}) == [
        {"field": "maps_url", "code": "too_long", "message": "Tối đa 40 ký tự"}
    ]


# ---------- UUID, ngày, enum ----------


def test_uuid_accepts_lowercase_canonical_string() -> None:
    value = uuid.uuid4()
    sample = parse(media_id=str(value))

    assert sample.media_id == value
    assert sample.model_dump(mode="json")["media_id"] == str(value)


@pytest.mark.parametrize(
    "raw",
    [
        "6F1E2B1A-0C3D-4C1E-9A77-1C2B3D4E5F60",
        "6f1e2b1a0c3d4c1e9a771c2b3d4e5f60",
        "{6f1e2b1a-0c3d-4c1e-9a77-1c2b3d4e5f60}",
        "urn:uuid:6f1e2b1a-0c3d-4c1e-9a77-1c2b3d4e5f60",
        "abc",
        123,
    ],
)
def test_uuid_rejects_other_formats(raw: Any) -> None:
    assert errors({"media_id": raw}) == [("media_id", "invalid_format")]


def test_iso_date_accepts_yyyy_mm_dd() -> None:
    sample = parse(event_date="2026-12-20")

    assert sample.event_date == date(2026, 12, 20)
    assert sample.model_dump(mode="json")["event_date"] == "2026-12-20"


@pytest.mark.parametrize(
    "raw",
    ["20/12/2026", "2026-2-3", "2026-02-30", "2026-12-20T00:00:00", " 2026-12-20", 1700000000],
)
def test_iso_date_rejects_other_formats(raw: Any) -> None:
    assert details({"event_date": raw}) == [
        {"field": "event_date", "code": "invalid_format", "message": "Ngày phải có dạng YYYY-MM-DD"}
    ]


def test_choice_accepts_enum_value() -> None:
    assert parse(side="groom").side is Side.groom


@pytest.mark.parametrize("raw", ["Groom", "both", ""])
def test_choice_rejects_other_values(raw: str) -> None:
    assert errors({"side": raw}) == [("side", "invalid_choice")]


# ---------- Số và boolean chặt ----------


@pytest.mark.parametrize("raw", ["2", "02", "2 người", 2.0, 2.5, True])
def test_integer_field_rejects_non_integers(raw: Any) -> None:
    assert details({"guest_count": raw}) == [
        {"field": "guest_count", "code": "invalid_format", "message": "Phải là số nguyên"}
    ]


@pytest.mark.parametrize("raw", ["true", "1", 1, 0])
def test_boolean_field_rejects_non_booleans(raw: Any) -> None:
    assert errors({"is_visible": raw}) == [("is_visible", "invalid_format")]


def test_boolean_null_is_rejected() -> None:
    assert errors({"is_visible": None}) == [("is_visible", "required")]


def test_unknown_field_is_rejected() -> None:
    assert details({"nickname": "Nam"}) == [
        {"field": "nickname", "code": "unknown_field", "message": "Trường không được hỗ trợ"}
    ]
    # Gửi null cho trường lạ vẫn là trường lạ, không phải required
    assert errors({"nickname": None}) == [("nickname", "unknown_field")]


# ---------- Email, mật khẩu ----------


def _account(**data: Any) -> Account:
    return Account.model_validate({"email": "nam@example.com", "password": "matkhau1", **data})


def test_email_is_trimmed_lowercased_and_nfc() -> None:
    raw = unicodedata.normalize("NFD", "  Nguyễn.Nam@Example.COM ")

    result = _account(email=raw).email

    assert result == "nguyễn.nam@example.com"
    assert unicodedata.is_normalized("NFC", result)


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_email_empty_or_null_is_required(raw: Any) -> None:
    assert errors({"email": raw, "password": "matkhau1"}, Account) == [("email", "required")]


def test_email_missing_is_required() -> None:
    assert errors({"password": "matkhau1"}, Account) == [("email", "required")]


@pytest.mark.parametrize(
    "raw", ["nam", "nam@", "@example.com", "nam @example.com", "nam@example", "nam@@example.com"]
)
def test_email_invalid_format(raw: str) -> None:
    assert details({"email": raw, "password": "matkhau1"}, Account) == [
        {"field": "email", "code": "invalid_format", "message": "Email không hợp lệ"}
    ]


@pytest.mark.parametrize("raw", [123, True, ["nam@example.com"]])
def test_email_rejects_non_strings(raw: Any) -> None:
    assert errors({"email": raw, "password": "matkhau1"}, Account) == [("email", "invalid_format")]


def test_email_longer_than_320_is_too_long() -> None:
    raw = "a" * 64 + "@" + ".".join(["b" * 63] * 4) + ".vn"
    assert len(raw) > 320

    assert details({"email": raw, "password": "matkhau1"}, Account) == [
        {"field": "email", "code": "too_long", "message": "Tối đa 320 ký tự"}
    ]


def test_password_is_nfc_but_not_trimmed() -> None:
    raw = unicodedata.normalize("NFD", " mật khẩu ")

    result = _account(password=raw).password

    assert result == " mật khẩu "
    assert unicodedata.is_normalized("NFC", result)


def test_password_length_is_counted_after_nfc() -> None:
    # 8 ký tự NFC, 12 code point khi ở dạng NFD
    raw = unicodedata.normalize("NFD", "mậtkhẩuu")
    assert len(raw) > 8

    assert _account(password=raw).password == "mậtkhẩuu"


@pytest.mark.parametrize(
    ("raw", "code", "message"),
    [
        ("matkhau", "out_of_range", "Tối thiểu 8 ký tự"),
        ("matkhau123456", "too_long", "Tối đa 12 ký tự"),
        ("", "required", "Không được để trống"),
        (None, "required", "Không được để trống"),
        (12345678, "invalid_format", "Phải là chuỗi"),
    ],
)
def test_password_rejects_invalid_values(raw: Any, code: str, message: str) -> None:
    assert details({"email": "nam@example.com", "password": raw}, Account) == [
        {"field": "password", "code": code, "message": message}
    ]
