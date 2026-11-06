# events

## Mục đích
Sự kiện của thiệp (bảng `events`), mỗi sự kiện có `host_side`. Bước 2: model. Bước 5: CRUD, tên mặc định, thứ tự hiển thị, giới hạn 10, If-Match và revision dùng chung với thiệp.

## File code chính
- `models.py`: `Event`, `EventType`, `HostSide`, `DEFAULT_TIMEZONE`, các CHECK (Bước 2)
- `schemas.py`: `EventCreate` (kèm `rule_errors`: quy tắc nhiều cột), `EventUpdate`, `EventResponse`, `EVENT_FIELDS`
- `service.py`: `default_event_name`, `display_name`, `display_order`, `to_response`, `list_for_invitation`, `create`, `update`, `delete`
- `router.py`: `/invitations/{invitation_id}/events`

## API công khai
- `GET /invitations/{id}/events`: danh sách theo thứ tự hiển thị, header `ETag` là revision hiện tại của thiệp
- `POST /invitations/{id}/events` → 201; `PATCH .../events/{event_id}` (Merge Patch) → 200; `DELETE .../events/{event_id}` → 204. Cả ba bắt buộc `If-Match`, response có `ETag` là revision mới
- `EventResponse`: mọi cột trừ `invitation_id`, thêm `display_name`. Chưa có `lunar_date` (Bước 9/10)
- `default_event_name(event_type, host_side)` → tên theo bảng ở spec 04 › Sự kiện, hoặc None (`family_ceremony` + `both`, `other`). Bước 10 dùng lại cho trang public cùng `display_order()`

## Phụ thuộc
- Dùng: core (`StrictModel`, `types`, `revision`, `errors`), invitations (`service.get_owned(for_update=True)`, `Invitation.revision`, `is_published`), auth (`User`)
- Được dùng bởi: invitations (`primary_event_date` = `MIN(event_date)`); Bước 6 publish, Bước 10 trang public

## Quy tắc spec đang áp dụng
- Cột, CHECK → 03 › events. Giới hạn, thứ tự, timezone, tên mặc định → 04 › Sự kiện. If-Match, revision → 04 › Sửa thiệp. Endpoint, mã lỗi → 05

## Quy tắc phụ chốt ở Bước 5 (người dùng duyệt 11 đề xuất, 2026-11-06)
1. `EventResponse` = mọi cột trừ `invitation_id`, + `display_name`.
2. `position` do server quản lý (gửi lên → `unknown_field`): sự kiện mới nhận `position` = số sự kiện hiện có; xoá thì đánh số lại 0..n-1 theo thứ tự cũ.
3. Thứ tự: `event_date NULLS LAST, start_time NULLS LAST, position, created_at, id`.
4. Tọa độ (`Latitude`/`Longitude` của core): chỉ số JSON; quá 6 chữ số thập phân → `invalid_format`, không làm tròn; response là số JSON.
5. `maps_url` (`HttpUrl(2048)` của core): http/https, có host, không khoảng trắng; không chuẩn hóa gì ngoài NFC + trim.
6. Quy tắc nhiều cột → 422, gắn vào trường phụ thuộc: `family_ceremony` + `both` → `host_side` `invalid_choice`; `other` không tên → `event_name` `required`; `end_time` không có `start_time` → `start_time` `required`; `end_time <= start_time` → `end_time` `out_of_range`; thiếu một tọa độ → trường thiếu `required`. PATCH kiểm tra trên bản đã gộp.
7. Vượt giới hạn → 400 `event_limit` (`settings.max_events_per_invitation = 10`).
8. ETag ở cả GET danh sách và DELETE 204.
9. POST/DELETE luôn tăng revision; PATCH không đổi giá trị nào → 200, không ghi.
10. Thiệp đã publish: mỗi lần ghi có thay đổi gửi webhook revalidate.
11. Sự kiện không có hoặc thuộc thiệp khác → 404 `event_not_found`.
- Suy ra từ spec 02: POST bắt buộc `event_type`, `host_side`; `timezone` không gửi → `Asia/Ho_Chi_Minh`, null/rỗng → `required`. PATCH null cho `event_type`, `host_side`, `timezone` → `required`.

## Thứ tự kiểm tra
401 → 428 thiếu If-Match → 422 body (POST: cả quy tắc nhiều cột) → 404 thiệp → 409 revision (sau `SELECT … FOR UPDATE` dòng thiệp) → 404 sự kiện → 400 giới hạn → 422 quy tắc nhiều cột của PATCH → ghi, tăng revision.

## Lưu ý
- Khóa dòng thiệp giữ cả giới hạn 10 khi có request đồng thời; test đồng thời đã được thử bỏ khóa: fail như mong đợi.
- PATCH: `_merge` gộp giá trị đã lưu (kiểu Python: `date`, `time`, `Decimal`) với patch rồi validate lại bằng `EventCreate`; các kiểu core nhận cả giá trị Python này.
- Chưa có: thiệp đã publish mà xoá sự kiện cuối hoặc xoá ngày, giờ, địa chỉ vẫn được (Bước 6: `breaks_published_invitation`); `lunar_date`, lọc theo side (Bước 9, 10).
- Các CHECK có test ở cả tầng database (`tests/test_db_schema.py`) và tầng API (`tests/test_events.py`).
