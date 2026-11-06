# Tiến độ

Cập nhật sau mỗi bước. Giữ dưới 60 dòng; khi dài thì gộp các mục cũ.

## Kế hoạch (`docs/spec/06-ke-hoach.md`)

| Bước | Việc | Trạng thái |
| --- | --- | --- |
| 0 | Chạy khung hiện tại | Xong 2026-11-05: 28/28 test qua, ruff sạch, `/docs` mở được; chỉ sửa `alembic.ini` |
| 1 | Tầng chuẩn hóa, base model, lỗi 422 | Xong 2026-11-05, đã duyệt: 143/143 test qua (115 mới), ruff sạch; `docs/modules/core.md` |
| 2 | Model và migration 0001 | Xong 2026-11-05, đã duyệt: 195/195 test qua (52 mới), ruff sạch; `alembic check` sạch trên PG 16.15 |
| 3 | Manifest template, seed | Xong 2026-11-06, chờ nghiệm thu: 275/275 test qua (80 mới), ruff sạch; `docs/modules/templates.md` |
| 4 | Content v1, tạo/sửa thiệp, revision | Chưa bắt đầu |
| 5 | Module events | Chưa bắt đầu |
| 6 | Publish, breaks_published_invitation | Chưa bắt đầu |
| 7 | Media: kind, âm thanh, dọn tham chiếu | Chưa bắt đầu |
| 8 | Danh sách ngân hàng, GET /banks | Chưa bắt đầu |
| 9 | Âm lịch | Chưa bắt đầu |
| 10 | Response public mới | Chưa bắt đầu |
| 11 | README, xoá code cũ | Chưa bắt đầu |

## Ghi chú Bước 0–2 (đã gộp; chi tiết trong `docs/modules/`)

- 2026-11-05: Tách `docs/spec-v1.md` thành `docs/spec/01`–`07` (giữ nguyên chữ, CRLF → LF); tạo `CLAUDE.md`, `docs/modules/`, `docs/progress.md`. Commit đầu `83b3822` là khung nguyên trạng; `thiepcuoi-backend.zip` để ngoài git (`.git/info/exclude`). Bước 0 chỉ sửa `alembic.ini` (Alembic đọc bằng cp1252).
- Bước 1: thêm `Uuid`, `IsoDate`, `Choice` (FastAPI validate ở chế độ Python, strict từ chối chuỗi), dependency `tzdata` (Windows), handler `StarletteHTTPException` (`core.md`).
- Bước 2: test dựng schema bằng `alembic upgrade head`; sửa tối thiểu code cũ (bỏ `event_date` khỏi API thiệp, `create_upload` ghi `kind = image`); upgrade/downgrade đã thử trên DB tạm; DB dev dựng lại (người dùng chạy).

## Ghi chú Bước 3

- Không đổi model, migration. `TemplateOut` đổi tên thành `TemplateResponse`. Key test đổi sang snake_case (`classic_01`…).
- DB dev: đã xoá 4 dòng key cũ (`classic-01`…, không có thiệp nào trỏ tới), seed mới chạy 2 lần; `alembic check` sạch.
- Docker Desktop chưa chạy thì `uv run pytest` không báo lỗi ngay mà chạy rất lâu (mỗi test chờ kết nối): khởi động Docker Desktop, `docker compose up -d` trước.

## Quyết định mới

- 2026-11-06 (Bước 3, người dùng duyệt theo đề xuất): quy tắc phụ của manifest và dòng seed (không trùng, tối thiểu 1 phần tử, dạng key, màu, mã lỗi trùng `invalid_format` / ngoài danh sách `invalid_choice`, `position` 0–3, dữ liệu seed nháp): xem `docs/modules/templates.md`. Bước 4 dùng cùng mã lỗi cho `appearance.sections`.

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
