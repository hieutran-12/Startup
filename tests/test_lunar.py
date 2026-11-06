"""Bước 9: âm lịch Việt Nam (app/core/lunar.py), múi giờ UTC+7.

Spec: 04 › Ngày âm lịch; 07 › Nguồn. 7 đề xuất được duyệt 2026-11-06 (docs/modules/lunar.md):
thuật toán Hồ Ngọc Đức, `to_lunar(date) -> LunarDate`, tháng nhuận là số tháng lặp lại kèm
`is_leap_month`, "Tỵ", "Kỷ", tính cho mọi `date` không raise, UTC+7 cho mọi năm.

Ngày đối chiếu tra ngày 2026-11-06 trên xemlicham.com (/am-lich/nam/YYYY/thang/M/ngay/D) và
lichvannien365.com (/xem-ngay-tot-xau-ngay-D-M-YYYY). Hai trang khớp nhau ở mọi ngày. Dấu nhuận
chỉ xemlicham ghi; lichvannien365 xác nhận gián tiếp (hai tháng liền nhau cùng số tháng).
"""

import unicodedata
from datetime import date, timedelta

import pytest

from app.core.lunar import LunarDate, to_lunar, year_name

# (ngày dương, ngày âm, tháng âm, nhuận, năm âm, tên năm)
REFERENCE_DATES = [
    # Spec 04: mùng 1 Tết Ất Sửu theo lịch Việt Nam; Tết Trung Quốc năm đó là 20/02/1985
    (date(1985, 1, 21), 1, 1, False, 1985, "Ất Sửu"),
    (date(1985, 2, 20), 1, 2, False, 1985, "Ất Sửu"),
    # Tết Đinh Hợi lệch một ngày so với Trung Quốc (18/02/2007)
    (date(2007, 2, 17), 1, 1, False, 2007, "Đinh Hợi"),
    (date(2007, 2, 18), 2, 1, False, 2007, "Đinh Hợi"),
    # Tết Mậu Thân, năm miền Bắc chuyển sang UTC+7
    (date(1968, 1, 29), 1, 1, False, 1968, "Mậu Thân"),
    # Giao thừa thuộc năm âm lịch cũ
    (date(2026, 2, 16), 29, 12, False, 2025, "Ất Tỵ"),
    (date(2026, 2, 17), 1, 1, False, 2026, "Bính Ngọ"),
    # Năm 2025 nhuận tháng 6: tháng 6 thường bắt đầu 25/06, tháng 6 nhuận 25/07–22/08
    (date(2025, 6, 25), 1, 6, False, 2025, "Ất Tỵ"),
    (date(2025, 7, 25), 1, 6, True, 2025, "Ất Tỵ"),
    (date(2025, 8, 22), 29, 6, True, 2025, "Ất Tỵ"),
    (date(2025, 8, 23), 1, 7, False, 2025, "Ất Tỵ"),
    # Năm 2020 nhuận tháng 4
    (date(2020, 4, 23), 1, 4, False, 2020, "Canh Tý"),
    (date(2020, 5, 23), 1, 4, True, 2020, "Canh Tý"),
    # Mùa cưới cuối năm 2026
    (date(2026, 12, 20), 12, 11, False, 2026, "Bính Ngọ"),
    (date(2026, 12, 31), 23, 11, False, 2026, "Bính Ngọ"),
]


@pytest.mark.parametrize(
    ("solar", "day", "month", "is_leap_month", "year", "name"),
    REFERENCE_DATES,
    ids=[str(row[0]) for row in REFERENCE_DATES],
)
def test_reference_dates_match_vietnamese_calendar(
    solar: date, day: int, month: int, is_leap_month: bool, year: int, name: str
) -> None:
    assert to_lunar(solar) == LunarDate(
        day=day, month=month, year=year, is_leap_month=is_leap_month, year_name=name
    )


def test_new_moon_on_next_day_gives_day_30_not_day_0() -> None:
    # Điểm sóc rơi vào hôm sau nên ước lượng k theo tháng trung bình bị lệch một tháng: bản gốc
    # của thuật toán trả ngày 0 ở 07/05/2054 (và 13/04/1877, 16/03/1885, 09/04/2062).
    # Không tra lịch vạn niên: kỳ vọng suy ra từ ngày kế tiếp là mùng 1.
    assert to_lunar(date(2054, 5, 7)) == LunarDate(30, 3, 2054, False, "Giáp Tuất")
    assert to_lunar(date(2054, 5, 8)) == LunarDate(1, 4, 2054, False, "Giáp Tuất")
    for solar in (date(1877, 4, 13), date(1885, 3, 16), date(2062, 4, 9)):
        assert to_lunar(solar).day == 30
        assert to_lunar(solar + timedelta(days=1)).day == 1


def test_year_names_use_approved_spelling() -> None:
    # Một vòng 12 con giáp bắt đầu từ Giáp Tý 1984; cách viết đã duyệt: "Tỵ", "Kỷ", "Mão", "Quý"
    assert [year_name(year) for year in range(1984, 1996)] == [
        "Giáp Tý",
        "Ất Sửu",
        "Bính Dần",
        "Đinh Mão",
        "Mậu Thìn",
        "Kỷ Tỵ",
        "Canh Ngọ",
        "Tân Mùi",
        "Nhâm Thân",
        "Quý Dậu",
        "Giáp Tuất",
        "Ất Hợi",
    ]
    assert year_name(2026) == "Bính Ngọ"  # ví dụ của spec 04
    names = [year_name(year) for year in range(1984, 2044)]
    assert len(set(names)) == 60
    assert year_name(1984 + 60) == year_name(1984)
    assert all(unicodedata.is_normalized("NFC", name) for name in names)


def test_lunar_date_is_frozen() -> None:
    lunar = to_lunar(date(1985, 1, 21))
    with pytest.raises(AttributeError):
        lunar.day = 2  # type: ignore[misc]


def test_every_day_1900_to_2100_follows_calendar_rules() -> None:
    """Đi qua từng ngày: ngày âm tăng liên tục, tháng nối đúng thứ tự, mỗi năm tối đa 1 tháng
    nhuận, Tết rơi vào 21/01–20/02, tên năm chỉ đổi lúc Tết."""
    day = date(1900, 1, 1)
    previous = to_lunar(day)
    leap_months: dict[int, list[int]] = {}
    tet_dates: list[date] = []
    while day < date(2100, 12, 31):
        day += timedelta(days=1)
        current = to_lunar(day)
        assert 1 <= current.day <= 30, day
        assert 1 <= current.month <= 12, day
        if current.day != 1:
            assert (current.month, current.is_leap_month, current.year) == (
                previous.month,
                previous.is_leap_month,
                previous.year,
            ), day
            assert current.day == previous.day + 1, day
        else:
            assert previous.day in (29, 30), day
            if current.is_leap_month:
                assert (current.month, current.year) == (previous.month, previous.year), day
                assert not previous.is_leap_month, day
                leap_months.setdefault(current.year, []).append(current.month)
            else:
                assert current.month == previous.month % 12 + 1, day
                if current.month == 1:
                    assert current.year == previous.year + 1, day
                    tet_dates.append(day)
                else:
                    assert current.year == previous.year, day
        if current.year == previous.year:
            assert current.year_name == previous.year_name, day
        else:
            assert current.year_name != previous.year_name, day
        previous = current

    assert all(len(months) == 1 for months in leap_months.values())
    assert leap_months[2025] == [6]
    assert leap_months[2020] == [4]
    assert len(tet_dates) == 2100 - 1900 + 1  # Tết 1900 (31/01/1900) đến 2100
    for tet in tet_dates:
        assert date(tet.year, 1, 21) <= tet <= date(tet.year, 2, 20), tet


@pytest.mark.parametrize("solar", [date.min, date(1, 12, 31), date(9999, 1, 1), date.max])
def test_extreme_dates_do_not_raise(solar: date) -> None:
    lunar = to_lunar(solar)
    assert 1 <= lunar.day <= 30
    assert 1 <= lunar.month <= 12
    assert solar.year - 1 <= lunar.year <= solar.year
    assert lunar.year_name == year_name(lunar.year)
