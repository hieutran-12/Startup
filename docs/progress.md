# Tiến độ

Cập nhật sau mỗi bước. Giữ dưới 60 dòng; khi dài thì gộp các mục cũ.

## Kế hoạch (`docs/spec/06-ke-hoach.md`)

| Bước | Việc | Trạng thái |
| --- | --- | --- |
| 0 | Chạy khung hiện tại | Xong 2026-11-05: 28/28 test qua, ruff sạch, `/docs` mở được; chỉ sửa `alembic.ini` |
| 1 | Tầng chuẩn hóa, base model, lỗi 422 | Xong 2026-11-05, đã duyệt: 143/143 test qua (115 mới), ruff sạch; `docs/modules/core.md` |
| 2 | Model và migration 0001 | Xong 2026-11-05, chờ duyệt: 195/195 test qua (52 mới), ruff sạch; `alembic check` sạch trên PG 16.15 |
| 3 | Manifest template, seed | Chưa bắt đầu |
| 4 | Content v1, tạo/sửa thiệp, revision | Chưa bắt đầu |
| 5 | Module events | Chưa bắt đầu |
| 6 | Publish, breaks_published_invitation | Chưa bắt đầu |
| 7 | Media: kind, âm thanh, dọn tham chiếu | Chưa bắt đầu |
| 8 | Danh sách ngân hàng, GET /banks | Chưa bắt đầu |
| 9 | Âm lịch | Chưa bắt đầu |
| 10 | Response public mới | Chưa bắt đầu |
| 11 | README, xoá code cũ | Chưa bắt đầu |

## Đã xong ngoài kế hoạch, ghi chú Bước 0

- 2026-11-05: Tách `docs/spec-v1.md` thành `docs/spec/01`–`07` (giữ nguyên chữ, CRLF → LF); tạo `CLAUDE.md`, `docs/modules/`, `docs/progress.md`. Commit đầu `83b3822` là khung nguyên trạng; `thiepcuoi-backend.zip` để ngoài git (`.git/info/exclude`).
- Bước 0: lỗi duy nhất là Alembic đọc `alembic.ini` bằng cp1252 (đã viết chú thích không dấu). Script in tiếng Việt hỏng khi chạy qua pipe, không sửa code. Danh sách module: `docs/modules/README.md`.

## Ghi chú Bước 1

- FastAPI 0.162 validate body ở chế độ Python: `strict=True` từ chối UUID, ngày, enum dạng chuỗi, nên `types.py` thêm `Uuid`, `IsoDate`, `Choice` (ngoài danh sách của bước, cần để bật strict).
- Thêm dependency `tzdata`: Windows không có dữ liệu múi giờ, `zoneinfo.available_timezones()` trả rỗng.
- Handler `StarletteHTTPException` (404 route lạ, 405) cũng trả dạng lỗi chung.

## Ghi chú Bước 2

- Test dựng schema bằng `alembic upgrade head` (không còn `create_all`); `env.py` nhận connection truyền vào, bật `compare_server_default`.
- Sửa tối thiểu code cũ cho test qua: bỏ `event_date` khỏi API thiệp; `TemplateOut.manifest`, seed ghi dữ liệu cũ vào `manifest`; `create_upload` ghi `kind = image`.
- Kiểm tra trên DB tạm (đã xoá): upgrade, downgrade về base, upgrade lại, seed 2 lần; `revision --autogenerate` chỉ sinh `pass`.
- DB dev `thiepcuoi` đã dựng lại theo migration mới (người dùng chạy), seed 4 mẫu; `alembic check` sạch.

## Quyết định mới

- 2026-11-05 (Bước 2, người dùng duyệt theo đề xuất):
  - Giữ index của khung spec không nhắc tới (`ix_templates_category`, `ix_invitations_template_id`, `ix_albums_invitation_id`, `ix_media_album_id`, `ix_media_invitation_position`).
  - Không thêm CHECK/DEFAULT ngoài spec: không CHECK snake_case cho `templates.key`, `revision > 0`, `position >= 0`, `size_bytes > 0`; không unique index "1 file âm thanh"; `media.kind` không DEFAULT.
  - Tên constraint: xem `docs/modules/{invitations,media,events,templates}.md`.

- 2026-11-05 (Bước 1, người dùng duyệt theo đề xuất):
  - Ngắn hơn tối thiểu → `out_of_range` (không thêm `too_short`). Ký tự điều khiển: văn bản một dòng chặn mọi Cc (kể cả tab); nhiều dòng chỉ cho `\n`, `\t`. U+2028/U+2029 bị chặn ở cả hai.
  - Lỗi không gắn với trường → `field: ""`. Schema cũ chuyển sang `StrictModel` theo bước của từng module.
  - Mặc định: null/thiếu → `required`; sai kiểu → `invalid_format`; `Digits` sai → `invalid_format`; giờ/ngày/UUID không trim; UUID chỉ nhận chữ thường.
  - Chốt khi nghiệm thu: múi giờ sai (phân biệt hoa thường) → `invalid_choice`; dòng trống chỉ có khoảng trắng được giữ nguyên nội dung khi gộp.

## Việc còn treo

- Spec còn trỏ tới `docs/spec-v1.md` (01 › Mục đích và cách dùng; 06 › Mẫu câu giao việc). Chờ quyết định có sửa spec không.
- Schema request của auth (`RegisterRequest`, `LoginRequest`) chưa chuyển sang `StrictModel`/`SingleLine`, và kế hoạch không có bước nào cho auth. Chờ quyết định làm ở bước nào.
- Bản xuất spec mất định dạng: bảng bị trải mỗi ô một dòng; mất sơ đồ quan hệ bảng (03 › "Mũi tên đi từ…") và link "(nguồn)" ở 04 › Ngày âm lịch.
