# lunar

## Mục đích
Đổi ngày dương sang ngày âm lịch Việt Nam (UTC+7) cho `lunar_date` của sự kiện ở trang public. Chỉ tính khi trả về, không lưu (Bước 9; Bước 10 đưa vào response public).

## File code chính
- `app/core/lunar.py`: `LunarDate`, `to_lunar`, `year_name`; hằng `TIMEZONE_HOURS = 7`

## API công khai
- `to_lunar(solar: date) -> LunarDate`: nhận mọi `date` (`date.min`…`date.max`), không raise
- `LunarDate`: frozen dataclass `day` (1–30), `month` (1–12), `year` (năm âm: năm dương có Tết mở đầu năm âm đó), `is_leap_month`, `year_name`. Tháng nhuận mang số của tháng nó lặp lại (`month: 6, is_leap_month: true`)
- `year_name(lunar_year) -> str`: `"<Can> <Chi>"`, 1984 là "Giáp Tý"

## Phụ thuộc
- Dùng: thư viện chuẩn (`math`, `datetime`, `functools`), không thêm dependency
- Được dùng bởi: events (`PublicEventResponse.lunar_date`, `computed_field`), trả ở trang public của invitations (Bước 10)

## Quy tắc spec đang áp dụng
- Lịch Việt Nam UTC+7, không dùng thư viện lịch Trung Quốc; 21/01/1985 là mùng 1 Tết Ất Sửu → `docs/spec/04-nghiep-vu.md` › Ngày âm lịch; nguồn ở 07 › Nguồn
- Tính khi trả về, không lưu → 02 › nguyên tắc 6

## Quy tắc phụ chốt ở Bước 9 (người dùng duyệt 7 đề xuất, 2026-11-06)
1. Tự cài đặt thuật toán Hồ Ngọc Đức (điểm sóc, kinh độ Mặt Trời theo công thức rút gọn của Meeus), Python thuần.
2. `to_lunar(date) -> LunarDate` (frozen dataclass, đúng 5 trường của spec); response ở Bước 10 (`events.schemas.LunarDateResponse`, cùng 5 trường).
3. Cách viết can chi: Giáp, Ất, Bính, Đinh, Mậu, Kỷ, Canh, Tân, Nhâm, Quý; Tý, Sửu, Dần, Mão, Thìn, Tỵ, Ngọ, Mùi, Thân, Dậu, Tuất, Hợi.
4. Tính cho mọi ngày, không raise, không trả null. Ngoài khoảng 1800–2199 độ chính xác thiên văn giảm.
5. UTC+7 cho mọi năm (lịch miền Bắc trước 1968 dùng UTC+8: kết quả các năm đó có thể khác lịch in thời ấy).

## Cài đặt
- Số ngày Julius lấy từ `date.toordinal() + 1721425` (lịch Gregory kéo dài về trước, như `date` của Python). `_jd_from_date` nhận cả năm 0 và năm 10000, nên `date.min`, `date.max` tính được tháng 11 của năm liền trước và liền sau.
- Khác bản gốc: `_month_start_index` dò lại k sau khi ước lượng theo tháng trung bình. Khi điểm sóc rơi vào hôm sau, ước lượng lệch một tháng và bản gốc trả ngày 0. Trong 1800–2199 có 4 ngày như vậy: 13/04/1877, 16/03/1885, 07/05/2054, 09/04/2062. Bản này trả ngày 30 của tháng trước (có test). Mọi ngày khác trong 1800–2199 (146.097 ngày) giống bản gốc, đã so bằng script ngày 2026-11-06.
- `lru_cache(512)` cho tháng 11 theo năm và vị trí tháng nhuận; đi qua 73.000 ngày (1900–2100) mất khoảng 0,8 giây.

## Ngày đối chiếu (tra ngày 2026-11-06)
Nguồn: xemlicham.com (`/am-lich/nam/YYYY/thang/M/ngay/D`) và lichvannien365.com (`/xem-ngay-tot-xau-ngay-D-M-YYYY`). Hai trang khớp nhau về ngày, tháng, can chi ở cả 15 ngày trong `tests/test_lunar.py`. Dấu nhuận chỉ xemlicham ghi. Ở lichvannien365, tháng nhuận được xác nhận gián tiếp: 25/06/2025 và 25/07/2025 đều là mùng 1 tháng 6; 23/04/2020 và 23/05/2020 đều là mùng 1 tháng 4. Trang Hồ Ngọc Đức (informatik.uni-leipzig.de/~duc/amlich/) trả 404.
- Đổi `TIMEZONE_HOURS` sang 8 thì ra đúng Tết Trung Quốc (20/02/1985, 18/02/2007, 30/01/1968), nên test đối chiếu phân biệt được hai loại lịch.

## Lưu ý
- Test (`tests/test_lunar.py`): 15 ngày đối chiếu, cách viết can chi, đi qua từng ngày 1900–2100 (ngày, tháng nối tiếp, mỗi năm tối đa 1 tháng nhuận, Tết trong 21/01–20/02, tên năm chỉ đổi lúc Tết), ngày cực trị không raise.
