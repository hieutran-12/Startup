# events

## Mục đích
Sự kiện của thiệp (bảng `events`), mỗi sự kiện có `host_side`. Bước 2 mới có model; CRUD, tên mặc định, thứ tự, giới hạn 10, If-Match làm ở Bước 5.

## File code chính
- `app/modules/events/models.py`: `Event`, `EventType`, `HostSide`, `DEFAULT_TIMEZONE`

## API công khai
- Chưa có service, router hay schema.

## Phụ thuộc
- Dùng: core (`Base`, `enum_check`), FK tới invitations
- Được dùng bởi: chưa có

## Quy tắc spec đang áp dụng
- Cột, kiểu, NULL, DEFAULT → `docs/spec/03-mo-hinh-du-lieu.md` › events
- `invitation_id` FK `ON DELETE CASCADE`; index `ix_events_invitation_position (invitation_id, position)`
- `start_time`, `end_time` là `TIME(0)` (giờ địa phương); `timezone` VARCHAR(64) NOT NULL DEFAULT `'Asia/Ho_Chi_Minh'`
- `latitude`, `longitude` NUMERIC(9,6) (`Decimal` ở Python)
- CHECK:
  - `ck_events_event_type_valid`, `ck_events_host_side_valid`
  - `ck_events_family_ceremony_single_side`: lễ gia tiên không nhận `both`
  - `ck_events_other_has_name`: `other` bắt buộc có `event_name`
  - `ck_events_end_time_after_start_time`: có `end_time` thì phải có `start_time` và lớn hơn (không qua nửa đêm)
  - `ck_events_coordinates_paired`, `ck_events_latitude_range`, `ck_events_longitude_range`

## Lưu ý
- Các CHECK đã có test ở tầng database (`tests/test_db_schema.py`); Bước 5 thêm test qua API.
- Database không kiểm tra `timezone` có trong IANA: tầng API dùng `Timezone` của core.
- Strict ở chế độ Python không nhận số JSON cho `Decimal`: cần kiểu riêng cho tọa độ (xem `core.md` › Lưu ý).
