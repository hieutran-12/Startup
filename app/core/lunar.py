"""Âm lịch Việt Nam (spec 04 › Ngày âm lịch): đổi ngày dương sang ngày âm, tính theo UTC+7.

Thuật toán của Hồ Ngọc Đức ("Thuật toán tính âm lịch"): điểm sóc và kinh độ Mặt Trời tính theo
công thức thiên văn rút gọn của Jean Meeus. Tháng âm bắt đầu từ ngày có điểm sóc (giờ Việt Nam).
Tháng 11 là tháng chứa đông chí. Năm có 13 tháng thì tháng nhuận là tháng đầu tiên sau tháng 11
không chứa trung khí nào. Không dùng thư viện lịch Trung Quốc, vì lịch đó tính theo UTC+8.

UTC+7 dùng cho mọi năm, như spec yêu cầu (lịch miền Bắc trước 1968 dùng UTC+8). Hàm nhận mọi
`date` và không raise. Ngoài khoảng 1800–2199 độ chính xác thiên văn giảm.
"""

import math
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

TIMEZONE_HOURS = 7  # UTC+7

_CAN = ("Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý")
_CHI = ("Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi")

_SYNODIC_MONTH = 29.530588853  # số ngày trung bình của một tháng âm
_NEW_MOON_EPOCH = 2415021.076998695  # điểm sóc đầu tiên sau 1900-01-01 (ngày Julius)
_DR = math.pi / 180
_ORDINAL_TO_JD = 1721425  # date.toordinal() + hằng số = số ngày Julius (lịch Gregory)


@dataclass(frozen=True, slots=True)
class LunarDate:
    day: int  # 1–30
    month: int  # 1–12; tháng nhuận mang số của tháng nó lặp lại
    year: int  # năm âm lịch: năm dương có Tết mở đầu năm âm đó
    is_leap_month: bool
    year_name: str  # can chi của năm, ví dụ "Bính Ngọ"


def year_name(lunar_year: int) -> str:
    """Can chi của năm âm lịch: 1984 là Giáp Tý."""
    return f"{_CAN[(lunar_year + 6) % 10]} {_CHI[(lunar_year + 8) % 12]}"


def _jd_from_date(day: int, month: int, year: int) -> int:
    """Số ngày Julius của một ngày theo lịch Gregory (nhận cả năm 0 và năm 10000)."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _new_moon(k: int) -> float:
    """Thời điểm (ngày Julius, UTC) của điểm sóc thứ k tính từ điểm sóc 1900-01-01."""
    t = k / 1236.85  # thế kỷ Julius tính từ 1900-01-01
    t2 = t * t
    t3 = t2 * t
    jd = 2415020.75933 + 29.53058868 * k + 0.0001178 * t2 - 0.000000155 * t3
    jd += 0.00033 * math.sin((166.56 + 132.87 * t - 0.009173 * t2) * _DR)
    m = (359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3) * _DR  # Mặt Trời
    mpr = (306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3) * _DR  # Mặt Trăng
    f = (21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3) * _DR
    correction = (
        (0.1734 - 0.000393 * t) * math.sin(m)
        + 0.0021 * math.sin(2 * m)
        - 0.4068 * math.sin(mpr)
        + 0.0161 * math.sin(2 * mpr)
        - 0.0004 * math.sin(3 * mpr)
        + 0.0104 * math.sin(2 * f)
        - 0.0051 * math.sin(m + mpr)
        - 0.0074 * math.sin(m - mpr)
        + 0.0004 * math.sin(2 * f + m)
        - 0.0004 * math.sin(2 * f - m)
        - 0.0006 * math.sin(2 * f + mpr)
        + 0.0010 * math.sin(2 * f - mpr)
        + 0.0005 * math.sin(2 * mpr + m)
    )
    if t < -11:
        delta_t = 0.001 + 0.000839 * t + 0.0002261 * t2 - 0.00000845 * t3 - 0.000000081 * t * t3
    else:
        delta_t = -0.000278 + 0.000265 * t + 0.000262 * t2
    return jd + correction - delta_t


def _new_moon_day(k: int) -> int:
    """Số ngày Julius của ngày (giờ Việt Nam) có điểm sóc thứ k."""
    return math.floor(_new_moon(k) + 0.5 + TIMEZONE_HOURS / 24)


def _sun_longitude_sector(jd: int) -> int:
    """Kinh độ Mặt Trời lúc 0 giờ (giờ Việt Nam) của ngày `jd`, chia thành 12 cung 30° (0–11)."""
    t = (jd - 0.5 - TIMEZONE_HOURS / 24 - 2451545.0) / 36525  # thế kỷ Julius tính từ J2000
    t2 = t * t
    m = (357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t * t2) * _DR
    l0 = 280.46645 + 36000.76983 * t + 0.0003032 * t2
    dl = (
        (1.914600 - 0.004817 * t - 0.000014 * t2) * math.sin(m)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m)
        + 0.000290 * math.sin(3 * m)
    )
    longitude = ((l0 + dl) * _DR) % (2 * math.pi)
    return min(math.floor(longitude / math.pi * 6), 11)


def _month_start_index(jd: int) -> int:
    """Chỉ số k của điểm sóc mở đầu tháng âm chứa ngày `jd`."""
    k = math.floor((jd - _NEW_MOON_EPOCH) / _SYNODIC_MONTH)
    # Ước lượng theo tháng trung bình có thể lệch một tháng ở các năm rất xa 1900
    while _new_moon_day(k) > jd:
        k -= 1
    while _new_moon_day(k + 1) <= jd:
        k += 1
    return k


@lru_cache(maxsize=512)
def _month_11_start(year: int) -> int:
    """Ngày bắt đầu (số ngày Julius) của tháng 11 âm lịch, tháng chứa đông chí năm `year`."""
    k = _month_start_index(_jd_from_date(31, 12, year))
    start = _new_moon_day(k)
    if _sun_longitude_sector(start) >= 9:  # tháng bắt đầu sau đông chí: lùi về tháng trước
        start = _new_moon_day(k - 1)
    return start


@lru_cache(maxsize=512)
def _leap_month_offset(month_11_start: int) -> int:
    """Năm 13 tháng: vị trí (tính từ tháng 11) của tháng đầu tiên không chứa trung khí."""
    k = math.floor((month_11_start - _NEW_MOON_EPOCH) / _SYNODIC_MONTH + 0.5)
    offset = 1
    sector = _sun_longitude_sector(_new_moon_day(k + offset))
    while True:
        previous = sector
        offset += 1
        sector = _sun_longitude_sector(_new_moon_day(k + offset))
        if sector == previous or offset >= 14:
            return offset - 1


def to_lunar(solar: date) -> LunarDate:
    """Ngày âm lịch Việt Nam của một ngày dương. Không lưu; tính khi trả về (nguyên tắc 6)."""
    jd = solar.toordinal() + _ORDINAL_TO_JD
    month_start = _new_moon_day(_month_start_index(jd))

    year = solar.year
    a11 = _month_11_start(year)
    if a11 >= month_start:
        lunar_year = year
        b11 = a11
        a11 = _month_11_start(year - 1)
    else:
        lunar_year = year + 1
        b11 = _month_11_start(year + 1)

    diff = (month_start - a11) // 29  # số tháng tính từ tháng 11
    month = diff + 11
    is_leap_month = False
    if b11 - a11 > 365:  # năm âm có 13 tháng
        leap_offset = _leap_month_offset(a11)
        if diff >= leap_offset:
            month = diff + 10
            is_leap_month = diff == leap_offset
    if month > 12:
        month -= 12
    if month >= 11 and diff < 4:
        lunar_year -= 1

    return LunarDate(
        day=jd - month_start + 1,
        month=month,
        year=lunar_year,
        is_leap_month=is_leap_month,
        year_name=year_name(lunar_year),
    )
