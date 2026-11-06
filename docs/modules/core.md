# core

## Mục đích
Hạ tầng dùng chung: cấu hình, database, bảo mật, storage, webhook revalidate. Bước 1: tầng chuẩn hóa dữ liệu request, định dạng lỗi chung. Bước 2: migration 0001 viết lại. Bước 4: Merge Patch, ETag/If-Match. Bước 5: kiểu tọa độ, URL; `max_events_per_invitation`. Bước 7: giới hạn upload theo loại file trong `config.py`. 2026-11-06: kiểu `Email`, `Password` cho auth.

## File code chính
- `app/core/types.py`: kiểu Annotated chuẩn hóa và kiểm tra dữ liệu request (Bước 1; `Latitude`, `Longitude`, `HttpUrl` ở Bước 5)
- `app/core/lunar.py`: âm lịch Việt Nam (Bước 9), mô tả riêng ở `lunar.md`
- `app/core/schemas.py`: `StrictModel` (Bước 1); `field_error`, `duplicate_errors` (Bước 4, chuyển từ templates)
- `app/core/errors.py`: `AppError`, `error_details`, handler lỗi (sửa ở Bước 1, 4)
- `app/core/merge_patch.py`, `app/core/revision.py`: Merge Patch, ETag/If-Match (Bước 4); `main.py` CORS `expose_headers=["ETag"]`
- `app/core/db.py`: `Base` (naming convention), mixin id/timestamp, `enum_check` (Bước 2)
- `alembic/versions/20261104_0001_initial_schema.py`: toàn bộ 7 bảng (viết lại ở Bước 2)
- `alembic/env.py`: `COMPARE_OPTIONS` (so kiểu và DEFAULT), nhận connection truyền vào (Bước 2)
- `config.py`: giữ từ khung; Bước 7 thay `max_upload_bytes`, `max_media_per_invitation`, `allowed_image_types` bằng `max_image_bytes` (15 MB), `max_audio_bytes` (10 MB), `max_images_per_invitation` (200), `max_audio_per_invitation` (1). Loại file cho phép là enum `MediaMimeType` của media, không cấu hình qua env
- `security.py`, `deps.py`, `storage.py`, `revalidate.py`: giữ từ khung

## API công khai
- `enum_check(column, StrEnum)`: chuỗi `<cột> IN ('a', 'b')` cho `CheckConstraint`; tên CHECK đặt dạng `name="<cột>_valid"`, convention thêm tiền tố `ck_<bảng>_`
- `StrictModel`: `strict=True`, `extra="forbid"`
- `SingleLine(n)` / `RequiredSingleLine(n)`: NFC, trim, gộp dấu cách Unicode (kể cả NBSP) thành một; Cc, U+2028/U+2029 → `invalid_characters`
- `MultiLine(n)` / `RequiredMultiLine(n)`: NFC, trim, `\r\n`/`\r` → `\n`, tối đa 2 dòng trống liền nhau (dòng chỉ có khoảng trắng tính là trống); cho `\n`, `\t`, ký tự Cc khác → `invalid_characters`
- `Digits(min, max)` / `RequiredDigits(min, max)`: NFC, trim, chỉ `0-9`; sai ký tự hoặc độ dài → `invalid_format`
- `Email` (bắt buộc): NFC, trim, chữ thường; rỗng → `required`, quá 320 → `too_long`, cú pháp sai (`email-validator`, không tra DNS) → `invalid_format`. Lưu chuỗi đã hạ chữ thường, không lấy bản `normalized` của thư viện
- `Password(min, max)` (bắt buộc): chỉ NFC, không trim; rỗng → `required`, ngắn → `out_of_range`, dài → `too_long` (quy tắc phụ ở `auth.md`)
- Bản không bắt buộc: rỗng sau chuẩn hóa → `None`. Bản bắt buộc: rỗng, null hoặc thiếu → `required`. Độ dài đếm sau chuẩn hóa → `too_long`
- `LocalTime`: đúng `HH:MM` 24 giờ (không trim, không giây) → `datetime.time`, JSON trả `"HH:MM"`
- `IsoDate`: đúng `YYYY-MM-DD` → `date`; `Uuid`: UUID chữ thường 36 ký tự → `uuid.UUID`. Sai → `invalid_format`
- `Timezone`: trim, khớp đúng tên trong `zoneinfo.available_timezones()` (phân biệt hoa thường) → sai là `invalid_choice`
- `Choice(E)`: StrEnum nhận chuỗi (`Annotated[E, Strict(False)]`) → sai là `invalid_choice`
- `Latitude` / `Longitude`: số JSON (int, float) → `Decimal`; chuỗi, boolean, NaN/Infinity → `invalid_format` "Tọa độ phải là số"; ngoài [-90, 90] / [-180, 180] → `out_of_range`; quá 6 chữ số thập phân → `invalid_format` (không làm tròn). Float đổi qua `repr` (chữ số ngắn nhất như client viết). Nhận cả `Decimal` (giá trị đọc từ DB). JSON trả số
- `HttpUrl(n)`: không bắt buộc; NFC, trim, rỗng → `None`; khoảng trắng (kể cả dấu cách Unicode), ký tự điều khiển, scheme khác `http://`/`https://` (không phân biệt hoa thường), thiếu host → `invalid_format`; dài quá → `too_long`. Giữ nguyên chuỗi, khác `pydantic.HttpUrl` (kiểu đó tự sửa URL)
- `AppError(status, code, message, details=(), headers=None)`, `bad_request(..., details=())`, `not_found`, `conflict`, `unauthorized`, `validation_error(details)` (422 do service phát hiện)
- `error_details(errors)`: `ValidationError.errors()` → `details` (loc không chứa body/query/path). Service tự validate thì nối tiền tố vào `loc` trước (content: `("content", *loc)`)
- `merge_patch(target, patch)`: RFC 7386, nhưng null không xoá key: giá trị cũ là danh sách → `[]`, còn lại → `None` để schema trả `required` nếu trường không nhận null. Không sửa `target`
- `etag(revision)`, `IfMatch` (dependency, thiếu → 428 `revision_required`), `check_revision(if_match, current)` (khác `"<revision>"` → 409 `revision_conflict`, header `ETag` mới). Gọi `check_revision` sau `SELECT … FOR UPDATE`. Khai báo `IfMatch` sau `CurrentUser` để 401 đi trước 428
- `error_response(...)`, `register_error_handlers(app)`: handler cho `AppError`, `RequestValidationError` (422 `validation_error`), `StarletteHTTPException` (404 `not_found`, 405 `method_not_allowed`, mã khác lấy từ tên HTTP status)

## Phụ thuộc
- Dùng: pydantic, fastapi, `tzdata` (zoneinfo trên Windows không có dữ liệu múi giờ nếu thiếu gói này)
- Được dùng bởi: mọi module

## Quy tắc spec đang áp dụng
- Thứ tự chuẩn hóa chuỗi → `docs/spec/04-nghiep-vu.md` › Chuẩn hóa chuỗi
- Kiểu dữ liệu, NULL/rỗng, strict, extra=forbid → `docs/spec/02-nguyen-tac-va-quy-chuan.md` › Quy chuẩn dữ liệu
- Định dạng lỗi, mã lỗi trường → `docs/spec/05-api.md` › Định dạng lỗi

## Migration và schema test (Bước 2)
- Model là nguồn để so; migration viết tay, chép literal (không import enum từ `app`) để migration không đổi theo code.
- `tests/conftest.py`: mỗi phiên test `DROP SCHEMA public CASCADE` trên `thiepcuoi_test` rồi `alembic upgrade head` qua `config.attributes["connection"]`; `env.py` thấy connection này thì không gọi `fileConfig`.
- `tests/test_db_schema.py::test_migration_matches_models` chạy `compare_metadata` (tương đương `alembic check`). Autogenerate không so CHECK, nên mỗi CHECK có test riêng trên schema của migration.
- Constraint có tên tường minh khi convention cho tên trùng (khóa ngoại kép của invitations, xem `invitations.md`).
- Chốt Bước 2 (người dùng duyệt): giữ index của khung mà spec không nhắc tới (`ix_templates_category`, `ix_invitations_template_id`, `ix_albums_invitation_id`, `ix_media_album_id`, `ix_media_invitation_position`); không thêm CHECK/DEFAULT ngoài spec (không CHECK snake_case cho `templates.key`, `revision > 0`, `position >= 0`, `size_bytes > 0`; không unique index "1 file âm thanh"; `media.kind` không DEFAULT).

## Ánh xạ lỗi Pydantic → mã spec (`errors.py`)
- Lỗi raise thẳng mã spec (`types.py`, `field_error`): giữ nguyên mã và message, kể cả khi input null (sửa ở Bước 4)
- `missing`, hoặc `null` gửi cho trường không nhận null (trừ trường lạ) → `required`
- `extra_forbidden` → `unknown_field`; `string_too_long`, `too_long` → `too_long`; `string_too_short`, `too_short`, `greater_than*`, `less_than*` → `out_of_range` (spec không có `too_short`)
- `enum`, `literal_error` → `invalid_choice`; mọi loại khác (sai kiểu, JSON hỏng, `value_error`) → `invalid_format`
- `field`: `content.love_story[0].title`; lỗi không gắn với trường (JSON hỏng, body không phải object, thiếu body) → `""`
- Lỗi tham chiếu chéo trong `model_validator`: gom `field_error(loc, code, message, value)` rồi raise `ValidationError.from_exception_data(...)`; Pydantic giữ `loc` của từng lỗi và nối tiền tố bên ngoài. Ví dụ: `TemplateManifest`, `Appearance`, `LoveStoryItem`. Validator cần dữ liệu ngoài (manifest) thì đọc `info.context`

## Lưu ý
- FastAPI validate body ở chế độ Python: trong `StrictModel`, khai báo `uuid.UUID`, `date`, `time` hay Enum gốc sẽ từ chối mọi chuỗi. Luôn dùng `Uuid`, `IsoDate`, `LocalTime`, `Choice`. Kiểu `str` thường không được chuẩn hóa: chỉ dùng cho key so khớp nguyên văn (ví dụ `Appearance.palette_key`).
- Lỗi độ dài chuỗi dùng loại `string_too_long` của Pydantic, vì `too_long` của Pydantic là lỗi độ dài danh sách (handler tra template tiếng Việt trước).
- Union không nullable (`A | B`) sẽ thêm tên nhánh vào `loc`; `_field_path` chưa xử lý trường hợp này.
- Strict ở chế độ Python không nhận số JSON cho `Decimal`: tọa độ dùng `Latitude`/`Longitude` (PlainValidator). Phần trăm (NUMERIC(5,2)) chưa có kiểu, chưa trường nào dùng.
- `json.loads` của Starlette nhận `NaN`, `Infinity`: kiểu số thập phân phải tự chặn số không hữu hạn.
- Schema request đã chuyển sang `StrictModel`: templates (Bước 3), invitations (Bước 4), events (Bước 5), media kể cả album (Bước 7), auth (2026-11-06, `Email`, `Password`). Không còn schema request nào dùng `BaseModel` thường.
