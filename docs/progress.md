# Tiến độ

Cập nhật sau mỗi bước. Giữ dưới 60 dòng; khi dài thì gộp các mục cũ.

## Kế hoạch (`docs/spec/06-ke-hoach.md`)

| Bước | Việc | Trạng thái |
| --- | --- | --- |
| 0 | Chạy khung hiện tại | Xong 2026-11-05: 28/28 test qua, ruff sạch, `/docs` mở được; chỉ sửa `alembic.ini` |
| 1 | Tầng chuẩn hóa, base model, lỗi 422 | Xong 2026-11-05, đã duyệt: 143/143 test qua (115 mới), ruff sạch; `docs/modules/core.md` |
| 2 | Model và migration 0001 | Xong 2026-11-05, đã duyệt: 195/195 test qua (52 mới), ruff sạch; `alembic check` sạch trên PG 16.15 |
| 3 | Manifest template, seed | Xong 2026-11-06, đã duyệt: 275/275 test qua (80 mới), ruff sạch; `docs/modules/templates.md` |
| 4 | Content v1, tạo/sửa thiệp, revision | Xong 2026-11-06, đã duyệt: 408/408 test qua (133 mới), ruff sạch; `docs/modules/invitations.md`, `core.md` |
| 5 | Module events | Xong 2026-11-06, đã duyệt: 543/543 test qua (135 mới), ruff sạch; `docs/modules/events.md`, `core.md` |
| 6 | Publish, breaks_published_invitation | Xong 2026-11-06, đã duyệt: 582/582 test qua (39 mới), ruff sạch; `docs/modules/invitations.md`, `events.md` |
| 7 | Media: kind, âm thanh, dọn tham chiếu | Xong 2026-11-06: 625/625 test qua (43 mới), ruff sạch; `docs/modules/media.md`, `invitations.md`, `core.md` |
| 8 | Danh sách ngân hàng, GET /banks | Chưa bắt đầu |
| 9 | Âm lịch | Chưa bắt đầu |
| 10 | Response public mới | Chưa bắt đầu |
| 11 | README, xoá code cũ | Chưa bắt đầu |

## Ghi chú Bước 0–6 (đã gộp; chi tiết trong `docs/modules/`)

- 2026-11-05: Tách `docs/spec-v1.md` thành `docs/spec/01`–`07` (giữ nguyên chữ, CRLF → LF); tạo `CLAUDE.md`, `docs/modules/`, `docs/progress.md`. Commit đầu `83b3822` là khung nguyên trạng; `thiepcuoi-backend.zip` để ngoài git (`.git/info/exclude`). Bước 0 chỉ sửa `alembic.ini` (Alembic đọc bằng cp1252).
- Bước 1: thêm `Uuid`, `IsoDate`, `Choice` (FastAPI validate ở chế độ Python, strict từ chối chuỗi), dependency `tzdata` (Windows), handler `StarletteHTTPException` (`core.md`).
- Bước 2: test dựng schema bằng `alembic upgrade head`; sửa tối thiểu code cũ (bỏ `event_date` khỏi API thiệp, `create_upload` ghi `kind = image`); DB dev dựng lại (người dùng chạy).
- Bước 3: `TemplateOut` → `TemplateResponse`, key snake_case; DB dev đã xoá 4 dòng key cũ và seed lại. Docker Desktop chưa chạy thì `uv run pytest` treo rất lâu thay vì báo lỗi: chạy `docker compose up -d` trước.
- Bước 4: thêm `merge_patch.py`, `revision.py`, `AppError.headers`, CORS expose `ETag`; `InvitationOut` → `InvitationResponse`; response public giữ dạng khung. Không đổi model, migration.
- Bước 5: thêm `Latitude`, `Longitude`, `HttpUrl` (core), `settings.max_events_per_invitation = 10`, router events trong `main.py`. Không đổi model, migration. Test đồng thời đã thử bỏ khóa `FOR UPDATE`: fail như mong đợi.

- Bước 6: không đổi model, migration, endpoint; bỏ mã `missing_couple_names`; `display_order()` chuyển sang `events/models.py`. Test cũ publish thiệp được thêm sự kiện đủ ngày, giờ, địa chỉ. Thiệp đã publish trên DB dev mà chưa đủ điều kiện: mọi lần sửa sẽ 400 tới khi đủ, hoặc unpublish rồi sửa.

## Ghi chú Bước 7

- Không đổi model, migration (DB dev không cần dựng lại). Spec 03 › media sửa theo yêu cầu người dùng: nhận thêm `audio/mp3`, `audio/x-m4a` (loại trình duyệt hay báo cho .mp3, .m4a), `mime_type` lưu đúng loại client gửi.
- Biến môi trường đổi: `MAX_UPLOAD_BYTES`, `MAX_MEDIA_PER_INVITATION` → `MAX_IMAGE_BYTES`, `MAX_AUDIO_BYTES`, `MAX_IMAGES_PER_INVITATION`, `MAX_AUDIO_PER_INVITATION` (`.env.example` đã sửa). `.env` cũ còn tên cũ thì bị bỏ qua, dùng mặc định đúng spec.
- FE cần biết: mã khung `unsupported_file_type`, `file_too_large` không còn (thành 422 tại `content_type`, `size_bytes`); `DELETE /media/{id}` trả `ETag`; `GET /media` có cả file âm thanh (`kind`); file âm thanh upload dở phải DELETE mới upload lại được.
- Test mới: `tests/test_media.py` (viết lại), `tests/test_media_references.py`; helper `upload_media` ở `conftest.py`. Hai test đồng thời đã thử bỏ khóa `FOR UPDATE`: fail 3/3 lần.

## Quyết định mới

- 2026-11-06 (Bước 7, người dùng duyệt 9 đề xuất, thêm yêu cầu nhận `audio/mp3`, `audio/x-m4a`: đã sửa spec 03 trước): giới hạn đếm theo `kind` gồm cả pending, khóa dòng thiệp; lỗi gắn trường → 422 (`invalid_choice`, `out_of_range`, `invalid_reference`), vượt số lượng → 400 `media_limit`; âm thanh không album, không kích thước; `MediaResponse.kind`; thứ tự chỉ cho ảnh; xoá file khóa dòng thiệp, không If-Match, 204 có `ETag`; schema media + album sang `StrictModel`, `*Out` → `*Response`; settings theo loại; public dạng khung chỉ trả ảnh. Chi tiết: `docs/modules/media.md`.
- 2026-11-06 (Bước 6, người dùng duyệt 8 đề xuất): details mã `required`, `events[i]` theo thứ tự hiển thị sau khi sửa, `content.appearance.sections` mỗi section thiếu một dòng; `breaks_published_invitation` liệt kê mọi điều kiện không đạt; kiểm tra sau 422, 409 slug, 400 `event_limit`; áp dụng cho PATCH thiệp và ghi sự kiện; đổi template mất `cover`/`events` trên thiệp đã publish → 400; publish lại giữ như khung. Chi tiết: `docs/modules/invitations.md`.
- 2026-11-06 (Bước 5, người dùng duyệt 11 đề xuất): `EventResponse` = mọi cột trừ `invitation_id`, + `display_name`; `position` do server quản lý, đánh số lại khi xoá; thứ tự `event_date`, `start_time` (đều NULLS LAST), `position`; tọa độ là số JSON, quá 6 chữ số thập phân → từ chối; `maps_url` http/https giữ nguyên; quy tắc nhiều cột → 422 tại trường phụ thuộc; 400 `event_limit`; ETag ở cả GET danh sách và DELETE 204; PATCH không đổi gì thì không ghi; revalidate khi đã publish; 404 `event_not_found`. Chi tiết: `docs/modules/events.md`.
- 2026-11-06 (Bước 4, người dùng duyệt 9 đề xuất): POST nhận content dạng Merge Patch; null cho nhóm object → `required`; lỗi manifest/tham chiếu media → 422; 409 trả revision qua `ETag`, If-Match chỉ khớp đúng `"<revision>"`; revision chỉ tăng khi có thay đổi; đổi template: chỉnh rồi gộp rồi kiểm tra chặt; month không year → lỗi tại `year`; `primary_event_date` làm ngay. Chốt khi nghiệm thu: slug rỗng lúc tạo thì tự sinh; key giao diện khớp nguyên văn; publish không cần If-Match, không tăng revision. Chi tiết: `docs/modules/invitations.md`.
- 2026-11-06 (Bước 3, người dùng duyệt theo đề xuất): quy tắc phụ của manifest và dòng seed (không trùng, tối thiểu 1 phần tử, dạng key, màu, mã lỗi trùng `invalid_format` / ngoài danh sách `invalid_choice`, `position` 0–3, dữ liệu seed nháp): xem `docs/modules/templates.md`. Bước 4 dùng cùng mã lỗi cho `appearance.sections`.
- 2026-11-05 (Bước 2, người dùng duyệt theo đề xuất): giữ index của khung spec không nhắc tới (`ix_templates_category`, `ix_invitations_template_id`, `ix_albums_invitation_id`, `ix_media_album_id`, `ix_media_invitation_position`); không thêm CHECK/DEFAULT ngoài spec (không CHECK snake_case cho `templates.key`, `revision > 0`, `position >= 0`, `size_bytes > 0`; không unique index "1 file âm thanh"; `media.kind` không DEFAULT). Tên constraint: `docs/modules/{invitations,media,events,templates}.md`.
- 2026-11-05 (Bước 1, người dùng duyệt theo đề xuất):
  - Ngắn hơn tối thiểu → `out_of_range` (không thêm `too_short`). Ký tự điều khiển: văn bản một dòng chặn mọi Cc (kể cả tab); nhiều dòng chỉ cho `\n`, `\t`. U+2028/U+2029 bị chặn ở cả hai.
  - Lỗi không gắn với trường → `field: ""`. Schema cũ chuyển sang `StrictModel` theo bước của từng module.
  - Mặc định: null/thiếu → `required`; sai kiểu → `invalid_format`; `Digits` sai → `invalid_format`; giờ/ngày/UUID không trim; UUID chỉ nhận chữ thường.
  - Chốt khi nghiệm thu: múi giờ sai (phân biệt hoa thường) → `invalid_choice`; dòng trống chỉ có khoảng trắng được giữ nguyên nội dung khi gộp.

## Việc còn treo

- Spec còn trỏ tới `docs/spec-v1.md` (01 › Mục đích và cách dùng; 06 › Mẫu câu giao việc). Chờ quyết định có sửa spec không.
- Schema request của auth (`RegisterRequest`, `LoginRequest`) chưa chuyển sang `StrictModel`/`SingleLine`, và kế hoạch không có bước nào cho auth. Chờ quyết định làm ở bước nào.
- Bản xuất spec mất định dạng: bảng bị trải mỗi ô một dòng; mất sơ đồ quan hệ bảng (03 › "Mũi tên đi từ…") và link "(nguồn)" ở 04 › Ngày âm lịch.
