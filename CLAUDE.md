# CLAUDE.md

## Hệ thống
Backend v1 cho dịch vụ thiệp cưới online. Cặp đôi chọn template, nhập nội dung, sự kiện, ảnh và nhạc rồi publish; khách mở trang public theo slug, có link riêng cho nhà trai và nhà gái (`?side=`).
- Stack: Python, FastAPI, Pydantic (strict, `extra="forbid"`), PostgreSQL ≥ 15 (docker-compose dùng 16), Alembic, uv, pytest, ruff. Trang public do Next.js render, backend gửi webhook revalidate.
- 7 bảng: users, refresh_tokens, templates, invitations, events, media, albums.
- Một thiệp dùng chung cho hai bên, mỗi sự kiện có `host_side`. `invitations.content` là JSONB có version (couple, messages, love_story, gifts, appearance); sự kiện là bảng riêng; ảnh bìa, chân dung, nhạc nền là cột `*_media_id` có khóa ngoại kép.
- Điểm xuất phát: khung FastAPI `thiepcuoi-backend.zip` (04/11/2026). Chưa có dữ liệu production: viết lại migration 0001, không thêm migration sửa đổi.

## Nguồn chuẩn
- `docs/spec/` là nguồn chuẩn về ý định. Không tự sửa. Code cần khác spec thì dừng, nêu rõ chỗ khác và hỏi; được đồng ý thì sửa spec trước, code sau.
- Không tự thêm trường, bảng hay endpoint ngoài spec. Spec chưa quy định thì dừng và hỏi.
- `docs/spec-v1.md` là bản gốc lưu trữ, không đọc khi làm tác vụ.
- `docs/modules/<tên>.md` (code đã viết) và `docs/progress.md` (tiến độ) do Claude tự cập nhật.

## 14 nguyên tắc bắt buộc (đầy đủ: spec 02)
1. Một trường chỉ mang một ý nghĩa.
2. Một trường chỉ có một kiểu dữ liệu chuẩn.
3. Không lưu đơn vị trong giá trị số; đơn vị nằm ở tên trường (`size_bytes`, `amount_vnd`).
4. Dữ liệu có tập giá trị xác định thì không dùng chuỗi tự do.
5. Cần truy vấn, ràng buộc hoặc được tham chiếu thì là cột/bảng; chỉ để hiển thị thì là JSONB có schema.
6. Không lặp dữ liệu; giá trị tính được thì tính khi trả về, không lưu.
7. Mọi cột và trường JSON quy định rõ NULL, DEFAULT, NOT NULL.
8. Validation hai tầng: DB giữ kiểu, NOT NULL, UNIQUE, FK, CHECK; API giữ schema JSONB và quy tắc nghiệp vụ.
9. Một quy ước đặt tên thống nhất cho toàn dự án.
10. Dữ liệu có cấu trúc linh hoạt phải có số version.
11. API không đoán ý: sai chuẩn thì từ chối kèm mã lỗi rõ ràng, không tự sửa.
12. Mọi chuỗi được trim và chuẩn hóa Unicode NFC trước khi lưu.
13. Tham chiếu tài nguyên khác bằng ID, không chép URL hay tên.
14. Mã toàn chữ số (số tài khoản, mã ngân hàng, số điện thoại) là chuỗi, không phải số nguyên.

## Quy ước đặt tên (đầy đủ: spec 02 › Quy ước đặt tên)
- snake_case mọi nơi, trừ class (PascalCase), URL nhiều từ (kebab-case), biến môi trường (UPPER_SNAKE_CASE).
- Bảng số nhiều; khóa ngoại `<danh từ số ít>_id`; constraint/index tiền tố `pk_ uq_ fk_ ck_ ix_` (naming convention trong `app/core/db.py`).
- Schema Pydantic hậu tố `Create`/`Update`/`Response` (bỏ `Out`). Service là hàm trong `service.py` của module, không viết class.
- Schema request kế thừa `StrictModel`; chuỗi, UUID, ngày, giờ, múi giờ, enum dùng kiểu trong `app/core/types.py` (lý do: `docs/modules/core.md`).
- Endpoint: danh từ số nhiều; hành động không phải CRUD là `POST /<tài nguyên>/{id}/<động từ>`.
- Enum, key template/palette/font, mã lỗi: snake_case chữ thường (`classic_01`). Slug thiệp là kebab-case.
- Hậu tố: `_at` TIMESTAMPTZ, `_date` DATE, `_time` TIME, `_id` khóa, `_count` đếm, `_bytes` dung lượng, `_vnd` tiền; boolean bắt đầu `is_`/`has_`.

## Lệnh thường dùng
```sh
cp .env.example .env                       # lần đầu
docker compose up -d                       # PostgreSQL :5432, RustFS (S3) :9000
uv sync                                    # cài dependency
uv run alembic upgrade head                # chạy migration
uv run python -m app.scripts.seed_templates  # seed mẫu thiệp
uv run python -m app.scripts.init_storage    # tạo bucket, CORS (lần đầu)
uv run fastapi dev app/main.py             # chạy app: http://localhost:8000/docs
uv run pytest                              # test (thiepcuoi_test, schema dựng bằng alembic upgrade head)
uv run ruff check .                        # lint
uv run alembic check                       # model khớp migration (như autogenerate, không ghi file)
```
Sửa migration 0001 thì DB dev phải dựng lại: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` rồi upgrade, seed.
Windows: `alembic.ini` chỉ dùng ký tự ASCII (Alembic đọc .ini bằng cp1252). Chạy script qua pipe thì đặt `PYTHONIOENCODING=utf-8`.

## Mục lục: tác vụ → file cần đọc
Spec trong `docs/spec/`: 01-quyet-dinh · 02-nguyen-tac-va-quy-chuan · 03-mo-hinh-du-lieu · 04-nghiep-vu · 05-api · 06-ke-hoach · 07-ngoai-pham-vi.
Module trong `docs/modules/<tên>.md` (danh sách và vị trí code: `docs/modules/README.md`). Chưa có file nghĩa là module chưa được bước nào làm tới: đọc code khung trực tiếp.

| Tác vụ | Spec | Module |
| --- | --- | --- |
| Làm một bước kế hoạch | 06 (dòng "Đọc:" của bước đó) | theo bước |
| Tìm lý do của một quyết định | 01 | |
| Kiểu dữ liệu, NULL/rỗng, chuẩn hóa chuỗi | 02 › Quy chuẩn dữ liệu; 04 › Chuẩn hóa chuỗi | core |
| Định dạng lỗi, mã lỗi, mã HTTP | 05 › Định dạng lỗi | core |
| Model, migration, CHECK, khóa ngoại | 03; 02 › Quy ước đặt tên | core + module của bảng |
| Auth, users, refresh token | 03 › Bảng giữ nguyên | auth |
| Template, manifest, seed | 03 › templates; 04 › Đổi template | templates |
| Tạo/sửa thiệp, Merge Patch, revision, If-Match | 04 › Tạo thiệp, Sửa thiệp; 05 | invitations + core |
| Schema content (couple, messages, love_story, appearance) | 03 › Nội dung thiệp | invitations |
| Publish | 04 › Publish | invitations |
| Sự kiện | 03 › events; 04 › Sự kiện; 05 | events |
| Media, upload, nhạc nền | 03 › invitations, media; 04 › Tham chiếu media; 05 | media |
| Album | 03 › Bảng giữ nguyên | media |
| Ngân hàng, mừng cưới (gifts) | 03 › Nội dung thiệp; 05 (GET /banks) | banks |
| Âm lịch | 04 › Ngày âm lịch; 07 › Nguồn | lunar |
| Trang public, `?side=` | 05 › Response của trang public; 04 › Link theo bên | invitations |
| Việc có vẻ nằm ngoài v1 | 07 (không làm, hỏi trước) | |

## Quy trình mọi tác vụ
Trước khi code:
1. Đọc `docs/progress.md`.
2. Chỉ đọc spec và module liên quan (xem mục lục). Không đọc toàn bộ `docs/spec/`.
3. Việc lớn: nêu kế hoạch ngắn và chờ duyệt rồi mới sửa code.
4. Spec chưa quy định thì dừng và hỏi, không tự quyết.

Khi làm một bước kế hoạch: chỉ làm bước đó; viết test theo "Tiêu chí nghiệm thu" trước rồi mới viết code.

Sau khi code xong một bước:
1. Chạy `uv run pytest` và `uv run ruff check .`, báo kết quả.
2. Tạo hoặc cập nhật `docs/modules/<tên>.md` cho module vừa làm hoặc vừa sửa.
3. Cập nhật `docs/progress.md`.
4. CLAUDE.md thiếu hoặc sai (lệnh, quy ước, module mới trong mục lục) thì sửa, giữ dưới 100 dòng; chi tiết thuộc module thì ghi vào file module.
5. Commit, thông điệp nêu rõ bước và module.

Sửa module có sẵn: đọc `docs/modules/<tên>.md` và spec liên quan trước; sửa xong cập nhật lại file module đó.
