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
| 7 | Media: kind, âm thanh, dọn tham chiếu | Xong 2026-11-06, đã duyệt: 625/625 test qua (43 mới), ruff sạch; `docs/modules/media.md`, `invitations.md`, `core.md` |
| 8 | Danh sách ngân hàng, GET /banks | Xong 2026-11-06, đã duyệt: 662/662 test qua (37 mới), ruff sạch; `docs/modules/banks.md`, `invitations.md` |
| 9 | Âm lịch | Xong 2026-11-06, đã duyệt: 685/685 test qua (23 mới), ruff sạch; `docs/modules/lunar.md`, `core.md` |
| 10 | Response public mới | Xong 2026-11-06, đã duyệt: 704/704 test qua (19 mới), ruff sạch; `docs/modules/invitations.md`, `events.md`, `media.md`, `lunar.md` |
| 11 | README, xoá code cũ | Xong 2026-11-06, đã duyệt: 753/753 test qua (10 mới), ruff sạch; `README.md`, `docs/modules/invitations.md` |

## Ghi chú Bước 0–10 (đã gộp; chi tiết trong `docs/modules/`)

- 2026-11-05: Tách `docs/spec-v1.md` thành `docs/spec/01`–`07` (giữ nguyên chữ, CRLF → LF); tạo `CLAUDE.md`, `docs/modules/`, `docs/progress.md`. Commit đầu `83b3822` là khung nguyên trạng; `thiepcuoi-backend.zip` để ngoài git (`.git/info/exclude`). Bước 0 chỉ sửa `alembic.ini` (Alembic đọc bằng cp1252).
- Bước 1: thêm `Uuid`, `IsoDate`, `Choice` (FastAPI validate ở chế độ Python, strict từ chối chuỗi), dependency `tzdata` (Windows), handler `StarletteHTTPException` (`core.md`).
- Bước 2: test dựng schema bằng `alembic upgrade head`; sửa tối thiểu code cũ (bỏ `event_date` khỏi API thiệp, `create_upload` ghi `kind = image`); DB dev dựng lại (người dùng chạy).
- Bước 3: `TemplateOut` → `TemplateResponse`, key snake_case; DB dev đã xoá 4 dòng key cũ và seed lại. Docker Desktop chưa chạy thì `uv run pytest` treo rất lâu thay vì báo lỗi: chạy `docker compose up -d` trước.
- Bước 4: thêm `merge_patch.py`, `revision.py`, `AppError.headers`, CORS expose `ETag`; `InvitationOut` → `InvitationResponse`; response public giữ dạng khung. Không đổi model, migration.
- Bước 5: thêm `Latitude`, `Longitude`, `HttpUrl` (core), `settings.max_events_per_invitation = 10`, router events trong `main.py`. Không đổi model, migration. Test đồng thời đã thử bỏ khóa `FOR UPDATE`: fail như mong đợi.
- Bước 6: không đổi model, migration, endpoint; bỏ mã `missing_couple_names`; `display_order()` chuyển sang `events/models.py`. Test cũ publish thiệp được thêm sự kiện đủ ngày, giờ, địa chỉ. Thiệp đã publish trên DB dev mà chưa đủ điều kiện: mọi lần sửa sẽ 400 tới khi đủ, hoặc unpublish rồi sửa.
- Bước 7: không đổi model, migration; spec 03 › media sửa theo yêu cầu (nhận `audio/mp3`, `audio/x-m4a`). Env đổi sang `MAX_IMAGE_BYTES`, `MAX_AUDIO_BYTES`, `MAX_IMAGES_PER_INVITATION`, `MAX_AUDIO_PER_INVITATION` (`.env` cũ còn tên cũ thì dùng mặc định). FE: bỏ mã `unsupported_file_type`, `file_too_large` (thành 422); `DELETE /media/{id}` trả `ETag`; `GET /media` có file âm thanh.
- Bước 8: không đổi model, migration, spec; module mới `app/modules/banks/` (`banks.json` 76 dòng từ VietQR, cách tạo lại ở `banks.md`). FE: `GET /banks` không cần đăng nhập; BIN lạ → 422 `invalid_choice` tại `content.gifts[i].bank_bin`; thiệp đã lưu BIN lạ thì lần sửa content kế tiếp bị 422 tới khi sửa gift.
- Bước 9: chỉ thêm `app/core/lunar.py`; 15 ngày đối chiếu khớp xemlicham.com và lichvannien365.com; đổi sang UTC+8 thì test phát hiện (`lunar.md`).
- Bước 10: không đổi model, migration, spec, endpoint (chỉ thêm query `side`); `display_name`, `lunar_date` là `computed_field`. FE: response public thay `media` bằng `gallery` + `media_by_id`, thêm `side`, `content_schema_version`, `events`; `PublicInvitationOut` → `PublicInvitationResponse`.

## Ghi chú Bước 11

- `README.md` viết lại cho dev BE/FE: lệnh chạy, cấu trúc, bảng mọi endpoint, quy ước dữ liệu, định dạng lỗi, revision/ETag/If-Match, các luồng FE (Merge Patch, sự kiện, upload ảnh và nhạc, mừng cưới, publish, trang public, content v1), production, ngoài phạm vi. Không nhắc `event_date`, `theme`, `lunar_date_text` và các trường content của khung.
- `tests/test_readme.py`: README không chứa tên trường cũ; endpoint trong README (dạng `` `METHOD /path` ``) khớp hai chiều với OpenAPI. Đổi endpoint mà quên README thì test fail.
- Xoá code: vulture không thấy code chết trong `app/` (chỉ route, validator, fixture do framework gọi). Giữ `Digits`, `RequiredMultiLine` (chỉ test dùng, nhưng là bộ kiểu spec 04 yêu cầu) và các test gửi trường cũ để kiểm tra bị từ chối.
- Dọn: `SlugAvailability` → `SlugAvailabilityResponse` (JSON không đổi); `.env.example` thêm `MAX_EVENTS_PER_INVITATION`; mã mẫu trong `test_core_errors.py` đổi thành `sample_rule_broken`; `tests/test_public.py` chạy `ruff format`. Không đổi model, migration, endpoint.

## Quyết định mới

- 2026-11-06 (Bước 10, người dùng duyệt 4 đề xuất): `side` chỉ nhận đúng `groom`/`bride`, sai (kể cả rỗng, `both`, chữ hoa) → 422 `invalid_choice` trước khi tìm slug; `gallery` = mọi ảnh ready theo `position, created_at`, không loại ảnh đang dùng, không cắt theo `max_gallery_images`; `albums` gồm cả album rỗng; `content` kiểu `InvitationContent`, đọc không context. Chi tiết: `docs/modules/invitations.md`.
- 2026-11-06 (Bước 9, người dùng duyệt 7 đề xuất): tự cài đặt thuật toán Hồ Ngọc Đức, không dependency; `to_lunar(date) -> LunarDate` (frozen dataclass 5 trường), tháng nhuận mang số tháng lặp lại; can chi viết "Tỵ", "Kỷ", "Mão"; tính cho mọi `date`, không raise, không null; UTC+7 cho mọi năm. Chi tiết: `docs/modules/lunar.md`.
- 2026-11-06 (Bước 8, người dùng duyệt 9 đề xuất): đủ 76 mục VietQR, không lọc `transferSupported`; chỉ `bin`, `short_name`, `name`, đã chuẩn hóa, giữ thứ tự nguồn; file sai thì app không khởi động; `GET /banks` không cần đăng nhập, không tham số; BIN lạ → 422 `invalid_choice`; kiểm tra mỗi lần content được kiểm tra theo request, không kiểm tra khi đọc; số tài khoản giữ quy tắc Bước 4; không có script tải lại. Chi tiết: `docs/modules/banks.md`.
- 2026-11-06 (Bước 7, người dùng duyệt 9 đề xuất, thêm yêu cầu nhận `audio/mp3`, `audio/x-m4a`: đã sửa spec 03 trước): giới hạn đếm theo `kind` gồm cả pending, khóa dòng thiệp; lỗi gắn trường → 422 (`invalid_choice`, `out_of_range`, `invalid_reference`), vượt số lượng → 400 `media_limit`; âm thanh không album, không kích thước; `MediaResponse.kind`; thứ tự chỉ cho ảnh; xoá file khóa dòng thiệp, không If-Match, 204 có `ETag`; schema media + album sang `StrictModel`, `*Out` → `*Response`; settings theo loại; public dạng khung chỉ trả ảnh. Chi tiết: `docs/modules/media.md`.
- 2026-11-06 (Bước 6, người dùng duyệt 8 đề xuất): details mã `required`, `events[i]` theo thứ tự hiển thị sau khi sửa, `content.appearance.sections` mỗi section thiếu một dòng; `breaks_published_invitation` liệt kê mọi điều kiện không đạt; kiểm tra sau 422, 409 slug, 400 `event_limit`; áp dụng cho PATCH thiệp và ghi sự kiện; đổi template mất `cover`/`events` trên thiệp đã publish → 400; publish lại giữ như khung. Chi tiết: `docs/modules/invitations.md`.
- 2026-11-06 (Bước 5, người dùng duyệt 11 đề xuất): `EventResponse` = mọi cột trừ `invitation_id`, + `display_name`; `position` do server quản lý, đánh số lại khi xoá; thứ tự `event_date`, `start_time` (đều NULLS LAST), `position`; tọa độ là số JSON, quá 6 chữ số thập phân → từ chối; `maps_url` http/https giữ nguyên; quy tắc nhiều cột → 422 tại trường phụ thuộc; 400 `event_limit`; ETag ở cả GET danh sách và DELETE 204; PATCH không đổi gì thì không ghi; revalidate khi đã publish; 404 `event_not_found`. Chi tiết: `docs/modules/events.md`.
- 2026-11-06 (Bước 4, người dùng duyệt 9 đề xuất): POST nhận content dạng Merge Patch; null cho nhóm object → `required`; lỗi manifest/tham chiếu media → 422; 409 trả revision qua `ETag`, If-Match chỉ khớp đúng `"<revision>"`; revision chỉ tăng khi có thay đổi; đổi template: chỉnh rồi gộp rồi kiểm tra chặt; month không year → lỗi tại `year`; `primary_event_date` làm ngay. Chốt khi nghiệm thu: slug rỗng lúc tạo thì tự sinh; key giao diện khớp nguyên văn; publish không cần If-Match, không tăng revision. Chi tiết: `docs/modules/invitations.md`.
- 2026-11-05/06 (Bước 1–3, người dùng duyệt theo đề xuất): quy tắc phụ của tầng chuẩn hóa và ánh xạ mã lỗi (`core.md`); giữ index của khung, không thêm CHECK/DEFAULT ngoài spec (`core.md` và file module của từng bảng); quy tắc manifest và dòng seed (`templates.md`).

## Việc treo đã xử lý (không còn việc nào treo)

- 2026-11-06 (người dùng duyệt 5 đề xuất): auth chuyển sang `StrictModel`: `full_name` `RequiredSingleLine(120)`; kiểu mới `Email` (NFC, trim, chữ thường, tối đa 320, `email-validator` không tra DNS) và `Password(min, max)` (chỉ NFC, không trim; đăng ký 8–128, đăng nhập 1–128) ở core; `UserOut` → `UserResponse`. 743/743 test qua (39 mới), ruff sạch. FE: lỗi 422 của auth giờ có mã spec (`required`, `out_of_range`, `unknown_field`…); `full_name` được gộp khoảng trắng; mật khẩu dạng NFD và NFC là một. Chi tiết: `docs/modules/auth.md`.
- 2026-11-06 (người dùng duyệt): spec 01–07 dựng lại định dạng từ doc gốc trên Claude Docs ("Đặc tả backend thiệp cưới v1", rev 15): bảng, khối code, link "(nguồn)" ở 04 › Ngày âm lịch, sơ đồ quan hệ 7 bảng bằng Mermaid ở 03, cột "Đọc" ở bảng 06; script so chữ xác nhận chữ không đổi. Bỏ chỗ trỏ tới `docs/spec-v1.md` ở 01 › Mục đích và cách dùng và 06 › Mẫu câu giao việc. Doc trên Claude Docs không sửa (chưa có `audio/mp3`, `audio/x-m4a` của Bước 7).
