# Thiệp Cưới API

Backend cho nền tảng thiệp cưới online: cặp đôi đăng ký tài khoản, chọn mẫu thiệp, điền nội dung, upload ảnh cưới và đăng thiệp lên một đường dẫn riêng (`thiepcuoi.vn/nam-lan`).

**Stack:** FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · Alembic · S3 API (RustFS khi chạy local, Cloudflare R2 khi production) · pytest

## Chạy lần đầu

Cần cài sẵn [uv](https://docs.astral.sh/uv/) và Docker.

```bash
cp .env.example .env
docker compose up -d                              # Postgres :5432, RustFS :9000 (console :9001)
uv sync                                           # tạo .venv, cài thư viện
uv run alembic upgrade head                       # tạo bảng
uv run python -m app.scripts.seed_templates       # thêm 4 mẫu thiệp
uv run python -m app.scripts.init_storage         # tạo bucket, bật CORS cho upload
uv run fastapi dev app/main.py                    # http://localhost:8000/docs
```

Chạy test (dùng database `thiepcuoi_test` mà docker-compose đã tạo sẵn):

```bash
uv run pytest -v
```

Lint và format: `uv run ruff check . && uv run ruff format .`

## Cấu trúc

```
app/
├── main.py                  # tạo FastAPI app, CORS, gắn router
├── models.py                # gom mọi model cho Alembic
├── core/
│   ├── config.py            # đọc .env (pydantic-settings)
│   ├── db.py                # engine, session, Base, mixin id/timestamps
│   ├── security.py          # Argon2, JWT access token, refresh token
│   ├── deps.py              # DbSession, CurrentUser
│   ├── errors.py            # AppError -> {"error": {"code", "message"}}
│   ├── storage.py           # presigned URL, head/delete object (S3/R2)
│   └── revalidate.py        # báo Next.js build lại trang thiệp
├── modules/
│   ├── auth/                # đăng ký, đăng nhập, refresh, logout, /me
│   ├── templates/           # danh sách mẫu thiệp
│   ├── invitations/         # CRUD thiệp, publish, trang public theo slug
│   └── media/               # upload ảnh, album, sắp xếp
└── scripts/                 # seed_templates, init_storage
alembic/versions/            # migration
tests/                       # pytest chạy với Postgres thật, storage giả lập
```

Mỗi module gồm `models.py` (bảng), `schemas.py` (request/response), `service.py` (nghiệp vụ, không phụ thuộc HTTP) và `router.py` (endpoint mỏng, chỉ gọi service).

## API

| Nhóm | Endpoint |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /me` |
| Mẫu thiệp | `GET /templates?category=`, `GET /templates/{key}` |
| Thiệp | `GET/POST /invitations`, `GET/PATCH/DELETE /invitations/{id}`, `POST /invitations/{id}/publish`, `POST /invitations/{id}/unpublish`, `GET /invitations/slug-availability?slug=` |
| Ảnh | `POST /invitations/{id}/media/upload-url`, `POST /invitations/{id}/media/{media_id}/complete`, `GET /invitations/{id}/media?album_id=`, `PATCH/DELETE /invitations/{id}/media/{media_id}`, `PUT /invitations/{id}/media/order` |
| Album | `GET/POST /invitations/{id}/albums`, `PATCH/DELETE /invitations/{id}/albums/{album_id}` |
| Public | `GET /public/invitations/{slug}` (chỉ thiệp đã publish, có Cache-Control) |

Lỗi nghiệp vụ luôn có dạng `{"error": {"code": "slug_taken", "message": "..."}}`. FE nên dựa vào `code` để hiển thị thông báo. Lỗi validate dữ liệu đầu vào là `422` theo định dạng mặc định của FastAPI.

## Các luồng chính cho FE

### Đăng nhập

- `register`/`login` trả `access_token` (sống 15 phút) trong body và đặt cookie httpOnly `refresh_token` (sống 30 ngày, chỉ gửi tới `/auth/*`).
- FE giữ access token **trong bộ nhớ** (không lưu localStorage), gửi qua header `Authorization: Bearer ...`.
- Khi API trả 401 hoặc khi tải lại trang: gọi `POST /auth/refresh` với `credentials: "include"` để lấy access token mới. Refresh token được xoay vòng mỗi lần dùng; nếu một token cũ bị dùng lại, mọi phiên của user bị thu hồi.
- Nên gom các lời gọi refresh đồng thời thành một (nhiều tab cùng refresh vẫn được chấp nhận trong 20 giây).

### Upload ảnh (3 bước, file không đi qua backend)

```ts
// 1. Xin link upload
const ticket = await api.post(`/invitations/${id}/media/upload-url`, {
  filename: file.name, content_type: file.type, size_bytes: file.size, album_id,
});
// 2. PUT file thẳng lên storage, đúng header backend trả về
await fetch(ticket.upload_url, { method: "PUT", headers: ticket.headers, body: file });
// 3. Xác nhận, kèm kích thước ảnh để trang thiệp dựng layout không bị giật
const { width, height } = await readImageSize(file);
const media = await api.post(`/invitations/${id}/media/${ticket.media_id}/complete`, { width, height });
```

Nên nén ảnh ở trình duyệt trước khi upload (ví dụ chuyển sang WebP, cạnh dài khoảng 2000px). Backend kiểm tra lại dung lượng và loại file thật ở bước 3, vì link presigned không giới hạn được dung lượng.

### Trang thiệp public

Next.js render `/[slug]` bằng ISR, lấy dữ liệu từ `GET /public/invitations/{slug}`, rồi chọn component theo `template_key`. Khi cặp đôi sửa hoặc đăng thiệp, backend gọi `FRONTEND_REVALIDATE_URL` với body `{"slugs": [...]}` và header `x-revalidate-secret`. Route này ở Next.js gọi `revalidatePath("/" + slug)` cho từng slug.

### Nội dung thiệp

`content` là JSON, schema chung nằm ở `app/modules/invitations/schemas.py` (`InvitationContent`): `couple`, `events`, `greeting`, `love_story`, `cover_media_id`, `music_url`, `bank_accounts`, `theme`. Template nào cần thêm trường riêng thì cứ gửi lên, backend giữ nguyên. `PATCH` thay thế toàn bộ `content`, nên editor ở FE gửi cả object.

## Lên production

- **Biến môi trường:** `APP_ENV=production`, `JWT_SECRET` ngẫu nhiên ≥ 32 ký tự, `COOKIE_SECURE=true`, `CORS_ORIGINS` là domain Next.js. Nếu FE và API khác site (ví dụ `*.vercel.app` và `api.thiepcuoi.vn`) thì đặt `COOKIE_SAMESITE=none`; tốt nhất là dùng chung domain gốc (`thiepcuoi.vn` và `api.thiepcuoi.vn`).
- **Cloudflare R2:** tạo bucket và API token (quyền Object Read & Write cho bucket đó), gắn custom domain để đọc ảnh công khai (`MEDIA_PUBLIC_BASE_URL`), thêm CORS rule cho phép `PUT` và `GET` từ domain Next.js. `S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, `S3_REGION=auto`.
- **Migration:** chạy `uv run alembic upgrade head` trước mỗi lần deploy. Khi đổi model: `uv run alembic revision --autogenerate -m "mo ta"`, đọc lại file sinh ra rồi mới commit.
- Swagger (`/docs`) tự tắt khi `APP_ENV=production`.

## Việc tiếp theo nên làm

- RSVP và sổ lời chúc: bảng `guests`, `rsvps`, `wishes` gắn với `invitations`, cộng endpoint public có rate limit.
- Rate limit cho `/auth/login`, `/auth/register` (ví dụ dùng Redis hoặc middleware của reverse proxy).
- Job dọn ảnh `pending` quá 24 giờ và object mồ côi trên storage.
- Đăng nhập Google/Zalo (`password_hash` đã cho phép null).
- Thanh toán gói premium: hiện mẫu `is_premium` đang bị chặn ở `templates/service.py::get_usable_by_key`.
- Bản nháp tách khỏi bản đã đăng, nếu muốn cặp đôi sửa thoải mái mà khách chưa thấy.
