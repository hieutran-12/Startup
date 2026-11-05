# core

## Mục đích
Hạ tầng dùng chung: cấu hình, database, bảo mật, storage, webhook revalidate. Từ Bước 1 có thêm tầng chuẩn hóa dữ liệu request và định dạng lỗi chung. Bước 2: migration 0001 viết lại, test dựng schema bằng migration.

## File code chính
- `app/core/types.py`: kiểu Annotated chuẩn hóa và kiểm tra dữ liệu request (Bước 1)
- `app/core/schemas.py`: `StrictModel`, base model của schema request (Bước 1)
- `app/core/errors.py`: `AppError`, `error_details`, handler lỗi (sửa ở Bước 1)
- `app/core/db.py`: `Base` (naming convention), mixin id/timestamp, `enum_check` (Bước 2)
- `alembic/versions/20261104_0001_initial_schema.py`: toàn bộ 7 bảng (viết lại ở Bước 2)
- `alembic/env.py`: `COMPARE_OPTIONS` (so kiểu và DEFAULT), nhận connection truyền vào (Bước 2)
- `config.py`, `security.py`, `deps.py`, `storage.py`, `revalidate.py`: giữ từ khung

## API công khai
- `enum_check(column, StrEnum)`: chuỗi `<cột> IN ('a', 'b')` cho `CheckConstraint`; tên CHECK đặt dạng `name="<cột>_valid"`, convention thêm tiền tố `ck_<bảng>_`
- `StrictModel`: `strict=True`, `extra="forbid"`
- `SingleLine(n)` / `RequiredSingleLine(n)`: NFC, trim, gộp dấu cách Unicode (kể cả NBSP) thành một; Cc, U+2028/U+2029 → `invalid_characters`
- `MultiLine(n)` / `RequiredMultiLine(n)`: NFC, trim, `\r\n`/`\r` → `\n`, tối đa 2 dòng trống liền nhau (dòng chỉ có khoảng trắng tính là trống); cho `\n`, `\t`, ký tự Cc khác → `invalid_characters`
- `Digits(min, max)` / `RequiredDigits(min, max)`: NFC, trim, chỉ `0-9`; sai ký tự hoặc độ dài → `invalid_format`
- Bản không bắt buộc: rỗng sau chuẩn hóa → `None`. Bản bắt buộc: rỗng, null hoặc thiếu → `required`. Độ dài đếm sau chuẩn hóa → `too_long`
- `LocalTime`: đúng `HH:MM` 24 giờ (không trim, không giây) → `datetime.time`, JSON trả `"HH:MM"`
- `IsoDate`: đúng `YYYY-MM-DD` → `date`; `Uuid`: UUID chữ thường 36 ký tự → `uuid.UUID`. Sai → `invalid_format`
- `Timezone`: trim, khớp đúng tên trong `zoneinfo.available_timezones()` (phân biệt hoa thường) → sai là `invalid_choice`
- `Choice(E)`: StrEnum nhận chuỗi (`Annotated[E, Strict(False)]`) → sai là `invalid_choice`
- `AppError(status, code, message, details=())`, `bad_request(..., details=())`, `not_found`, `conflict`, `unauthorized`
- `error_details(errors)`: `ValidationError.errors()` → `details` (loc không chứa body/query/path). Dùng lại khi service tự validate (ví dụ content sau Merge Patch)
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

## Ánh xạ lỗi Pydantic → mã spec (`errors.py`)
- `missing`, hoặc `null` gửi cho trường không nhận null (trừ trường lạ) → `required`
- `extra_forbidden` → `unknown_field`; `string_too_long`, `too_long` → `too_long`
- `string_too_short`, `too_short`, `greater_than*`, `less_than*` → `out_of_range` (đã chốt: spec không có `too_short`)
- `enum`, `literal_error` → `invalid_choice`; mọi loại khác (sai kiểu, JSON hỏng, `value_error`) → `invalid_format`
- `field`: `content.love_story[0].title`; lỗi không gắn với trường (JSON hỏng, body không phải object, thiếu body) → `""`

## Lưu ý
- FastAPI validate body ở chế độ Python: trong `StrictModel`, khai báo `uuid.UUID`, `date`, `time` hay Enum gốc sẽ từ chối mọi chuỗi. Luôn dùng `Uuid`, `IsoDate`, `LocalTime`, `Choice`.
- Kiểu `str` thường trong `StrictModel` không được chuẩn hóa: chuỗi phải dùng kiểu ở `types.py`.
- Lỗi độ dài chuỗi dùng loại `string_too_long` của Pydantic, vì `too_long` của Pydantic là lỗi độ dài danh sách (handler tra template tiếng Việt trước).
- Union không nullable (`A | B`) sẽ thêm tên nhánh vào `loc`; `_field_path` chưa xử lý trường hợp này.
- Chưa có số thập phân (`Decimal`) cho tọa độ, phần trăm: strict ở chế độ Python không nhận số JSON cho `Decimal`, cần kiểu riêng khi làm events (Bước 5).
- Schema hiện có của auth, media, templates, invitations chưa chuyển sang `StrictModel` (quyết định Bước 1): đi theo bước của module; auth chưa có bước.
