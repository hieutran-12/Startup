# Thiệp Cưới API

Backend v1 cho dịch vụ thiệp cưới online. Cặp đôi đăng ký tài khoản, chọn mẫu thiệp, nhập nội dung, sự kiện, ảnh và nhạc nền rồi đăng thiệp lên một đường dẫn riêng (`thiepcuoi.vn/nam-lan`). Một thiệp dùng chung cho hai bên gia đình; khách mở link chung hoặc link riêng của nhà trai, nhà gái. Trang thiệp public do Next.js render.

**Stack:** Python 3.13 · FastAPI · Pydantic (strict) · SQLAlchemy 2.0 async · PostgreSQL ≥ 15 (docker-compose dùng 16) · Alembic · S3 API (RustFS khi chạy local, Cloudflare R2 khi production) · uv · pytest · ruff

## Tài liệu

| Ở đâu | Nội dung |
| --- | --- |
| `docs/spec/01`–`07` | Đặc tả v1, là nguồn chuẩn: quyết định, nguyên tắc, mô hình dữ liệu, nghiệp vụ, API, kế hoạch, ngoài phạm vi. Code khác spec thì sửa code |
| `docs/modules/<tên>.md` | Hiện trạng code của từng module và các quy tắc phụ đã chốt khi làm |
| `docs/progress.md` | Tiến độ theo các bước của kế hoạch |
| `CLAUDE.md` | Quy trình làm việc, quy ước đặt tên, tác vụ nào đọc file nào |

## Chạy lần đầu

Cần cài sẵn [uv](https://docs.astral.sh/uv/) và Docker.

```bash
cp .env.example .env
docker compose up -d                              # PostgreSQL :5432, RustFS :9000 (console :9001)
uv sync                                           # tạo .venv, cài thư viện
uv run alembic upgrade head                       # tạo 7 bảng
uv run python -m app.scripts.seed_templates       # thêm 4 mẫu thiệp (chạy lại nhiều lần vẫn đúng)
uv run python -m app.scripts.init_storage         # tạo bucket, bật CORS cho upload
uv run fastapi dev app/main.py                    # http://localhost:8000/docs
```

Trước khi commit:

```bash
uv run pytest          # database thiepcuoi_test (docker-compose tạo sẵn), schema dựng bằng alembic upgrade head
uv run ruff check .    # lint
uv run ruff format .   # format
uv run alembic check   # model khớp migration
```

- Docker chưa chạy thì `uv run pytest` treo rất lâu thay vì báo lỗi: chạy `docker compose up -d` trước. Toàn bộ test (khoảng 750) mất 6–11 phút trên máy dev.
- Chưa có dữ liệu production nên chỉ có một migration `0001`: đổi model thì sửa thẳng file đó, rồi dựng lại DB dev (`DROP SCHEMA public CASCADE; CREATE SCHEMA public;`, `alembic upgrade head`, seed lại).
- Windows: `alembic.ini` chỉ được chứa ký tự ASCII (Alembic đọc file này bằng cp1252). Chạy script qua pipe thì đặt `PYTHONIOENCODING=utf-8`.

## Cấu trúc

```text
app/
├── main.py                  # tạo FastAPI app, CORS (cho JS đọc header ETag), handler lỗi, gắn router
├── models.py                # gom mọi model cho Alembic
├── core/
│   ├── config.py            # đọc .env (pydantic-settings), các giới hạn số lượng và dung lượng
│   ├── db.py                # engine, session, Base (naming convention pk_/uq_/fk_/ck_/ix_), mixin
│   ├── types.py             # kiểu chuẩn hóa dữ liệu request: SingleLine, MultiLine, Digits, Email…
│   ├── schemas.py           # StrictModel (strict, extra="forbid"), helper lỗi tham chiếu chéo
│   ├── errors.py            # AppError, định dạng lỗi chung, handler 422/404/405
│   ├── merge_patch.py       # JSON Merge Patch (RFC 7386)
│   ├── revision.py          # ETag, If-Match
│   ├── lunar.py             # âm lịch Việt Nam UTC+7
│   ├── security.py          # Argon2id, JWT access token, refresh token
│   ├── deps.py              # DbSession, CurrentUser
│   ├── storage.py           # presigned URL, head/delete object (S3/R2)
│   └── revalidate.py        # báo Next.js build lại trang thiệp
├── modules/
│   ├── auth/                # đăng ký, đăng nhập, refresh, logout, /me
│   ├── templates/           # mẫu thiệp, TemplateManifest
│   ├── invitations/         # thiệp, content v1, publish, trang public theo slug
│   ├── events/              # sự kiện của thiệp
│   ├── media/               # upload ảnh và nhạc, album, sắp xếp
│   └── banks/               # danh sách ngân hàng (banks.json) cho mục mừng cưới
└── scripts/                 # seed_templates, init_storage
alembic/versions/            # migration 0001: toàn bộ schema
docs/                        # spec, tài liệu module, tiến độ
tests/                       # pytest chạy với PostgreSQL thật, storage giả lập
```

Mỗi module gồm `models.py` (bảng), `schemas.py` (request/response), `service.py` (nghiệp vụ, là các hàm, không phụ thuộc HTTP) và `router.py` (endpoint mỏng, chỉ gọi service). `banks` không có bảng nên không có `models.py`.

## API

Swagger ở `/docs` khi chạy local (tự tắt khi `APP_ENV=production`). Endpoint cần header `Authorization: Bearer <access_token>`, trừ nhóm auth (riêng `GET /me` cần token), mẫu thiệp, ngân hàng, trang public và health.

| Nhóm | Endpoint |
| --- | --- |
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /me` |
| Mẫu thiệp | `GET /templates` (`?category=`), `GET /templates/{key}` |
| Thiệp | `GET /invitations`, `POST /invitations`, `GET /invitations/slug-availability` (`?slug=`), `GET /invitations/{invitation_id}`, `PATCH /invitations/{invitation_id}`, `DELETE /invitations/{invitation_id}` |
| Đăng thiệp | `POST /invitations/{invitation_id}/publish`, `POST /invitations/{invitation_id}/unpublish` |
| Sự kiện | `GET /invitations/{invitation_id}/events`, `POST /invitations/{invitation_id}/events`, `PATCH /invitations/{invitation_id}/events/{event_id}`, `DELETE /invitations/{invitation_id}/events/{event_id}` |
| File (ảnh, nhạc) | `POST /invitations/{invitation_id}/media/upload-url`, `POST /invitations/{invitation_id}/media/{media_id}/complete`, `GET /invitations/{invitation_id}/media` (`?album_id=`), `PUT /invitations/{invitation_id}/media/order`, `PATCH /invitations/{invitation_id}/media/{media_id}`, `DELETE /invitations/{invitation_id}/media/{media_id}` |
| Album | `GET /invitations/{invitation_id}/albums`, `POST /invitations/{invitation_id}/albums`, `PATCH /invitations/{invitation_id}/albums/{album_id}`, `DELETE /invitations/{invitation_id}/albums/{album_id}` |
| Ngân hàng | `GET /banks` |
| Trang public | `GET /public/invitations/{slug}` (`?side=groom` hoặc `?side=bride`) |
| Hệ thống | `GET /health` |

### Quy ước dữ liệu

Chi tiết ở `docs/spec/02-nguyen-tac-va-quy-chuan.md`.

- **Kiểu chặt:** số phải là số JSON, boolean phải là `true`/`false`; `"2"` hay `"true"` bị từ chối. Gửi trường không có trong schema → 422 `unknown_field`.
- **Chuỗi:** server chuẩn hóa Unicode NFC và trim trước khi lưu; văn bản một dòng được gộp khoảng trắng và không được có xuống dòng. Trường không bắt buộc gửi `""` thì lưu `null`; trường bắt buộc gửi `""` → 422 `required`.
- **Không đoán ý:** dữ liệu sai chuẩn bị từ chối, không tự sửa (không làm tròn tọa độ, không đọc `"20/12/2026"` thành ngày). Việc chuyển đổi là của giao diện.
- **Định dạng:** ID là UUID chữ thường; ngày `"YYYY-MM-DD"`; giờ sự kiện `"HH:MM"` kèm `timezone` IANA (`Asia/Ho_Chi_Minh`); thời điểm hệ thống ISO 8601 UTC; số tài khoản, BIN ngân hàng là chuỗi chữ số.
- **Response đầy đủ:** mọi trường đã khai báo đều có mặt, kể cả khi là `null`; danh sách rỗng là `[]`, không bao giờ `null`.
- **Tham chiếu bằng ID:** ảnh và nhạc gắn vào thiệp bằng `media_id`; URL tra trong `media_by_id` (trang public) hoặc `GET /invitations/{invitation_id}/media`.

### Định dạng lỗi

Mọi lỗi, kể cả 422, có cùng một dạng. FE dựa vào `code` để chọn thông báo và vào `details[].field` để gắn lỗi vào đúng ô nhập.

```json
{
  "error": {
    "code": "validation_error",
    "message": "Dữ liệu không hợp lệ",
    "details": [
      {"field": "content.couple.groom.full_name", "code": "required", "message": "Không được để trống"},
      {"field": "start_time", "code": "invalid_format", "message": "Giờ phải có dạng HH:MM"}
    ]
  }
}
```

- `details` luôn là danh sách, rỗng khi không có chi tiết. `field` là đường dẫn có dấu chấm, phần tử danh sách viết `love_story[0].title`; lỗi không gắn với trường nào (JSON hỏng) có `field: ""`.
- Mã của từng trường: `required`, `invalid_format`, `invalid_characters`, `too_long`, `out_of_range`, `invalid_choice`, `unknown_field`, `invalid_reference`.
- Mã HTTP: 400 lỗi nghiệp vụ (`not_ready_to_publish`, `breaks_published_invitation`, `invitation_limit`, `event_limit`, `media_limit`, `template_premium`…), 401 chưa đăng nhập, 404 không tìm thấy hoặc không có quyền, 409 xung đột (`slug_taken`, `revision_conflict`, `email_taken`), 422 sai định dạng dữ liệu, 428 thiếu `If-Match` (`revision_required`).

### Chống ghi đè: revision, ETag, If-Match

- Response của một thiệp (tạo, xem, sửa, đăng, gỡ) có header `ETag: "<revision>"`; `revision` cũng có trong body.
- `PATCH /invitations/{invitation_id}` và mọi thao tác ghi sự kiện phải gửi `If-Match` đúng nguyên giá trị ETag, kể cả ngoặc kép (`If-Match: "3"`). Thiếu → 428 `revision_required`; khác revision hiện tại → 409 `revision_conflict`, header `ETag` của response 409 là revision mới nhất: FE tải lại thiệp rồi cho người dùng sửa tiếp.
- Danh sách sự kiện, các thao tác ghi sự kiện và việc xoá file cũng trả `ETag`; FE dùng giá trị mới nhất cho lần ghi kế tiếp.
- `revision` tăng khi content, sự kiện, `title`, `slug`, mẫu thiệp hoặc file gắn vào thiệp thay đổi. Album và thứ tự ảnh không làm tăng; request không đổi giá trị nào thì không tăng.

## Các luồng chính cho FE

### Đăng nhập

- `POST /auth/register` (`email`, `password` 8–128 ký tự, `full_name`) và `POST /auth/login` trả `access_token` (sống 15 phút) trong body, đồng thời đặt cookie httpOnly `refresh_token` (sống 30 ngày, chỉ gửi tới `/auth/*`).
- Email được trim và hạ chữ thường. Mật khẩu giữ nguyên dấu cách, chỉ được chuẩn hóa NFC (cùng mật khẩu có dấu gõ trên macOS hay Windows là một).
- FE giữ access token **trong bộ nhớ** (không lưu localStorage), gửi qua header `Authorization: Bearer ...`.
- Khi API trả 401 hoặc khi tải lại trang: gọi `POST /auth/refresh` với `credentials: "include"` để lấy access token mới. Refresh token xoay vòng mỗi lần dùng. Token cũ dùng lại trong 20 giây chỉ bị từ chối (401 `refresh_token_rotated`); dùng lại sau đó thì mọi phiên của user bị thu hồi (`refresh_token_reused`). Nên gom các lời gọi refresh đồng thời của nhiều tab thành một.

### Tạo và sửa thiệp

1. `GET /templates` lấy danh sách mẫu. `manifest` của mỗi mẫu cho biết section, bảng màu, font, nền được phép và giá trị mặc định.
2. `POST /invitations` với `template_key` (bắt buộc), `title`, `slug` (bỏ trống thì tự sinh từ tên, kiểm tra trước bằng `GET /invitations/slug-availability?slug=`) và `content` (tùy chọn, gộp lên nội dung mặc định). Mỗi tài khoản tối đa 5 thiệp; mẫu premium chưa dùng được.
3. `PATCH /invitations/{invitation_id}` nhận body dạng JSON Merge Patch (RFC 7386), kèm `If-Match`. Có thể gửi `Content-Type: application/merge-patch+json`.
   - Chỉ gửi trường cần đổi; trường không gửi được giữ nguyên.
   - `null` là xoá giá trị; gửi `null` cho danh sách thì danh sách về `[]`.
   - Danh sách (`love_story`, `gifts`, `appearance.sections`) luôn bị thay nguyên: muốn sửa một mốc thì gửi lại cả danh sách.
4. Đổi `template_key`: nội dung giữ nguyên. `palette_key`, `font_key`, `background_key` không có trong mẫu mới về `null`; `sections` giữ các section mẫu mới hỗ trợ, đúng thứ tự cũ.

```ts
const res = await api.patch(`/invitations/${id}`, {
  content: { couple: { groom: { display_name: "Nam" } }, messages: { guest_notes: null } },
  cover_media_id: coverId,
}, { headers: { "If-Match": etag } });
etag = res.headers.get("ETag"); // dùng cho lần ghi kế tiếp
```

### Sự kiện

- Mỗi thiệp tối đa 10 sự kiện (400 `event_limit`). Mỗi sự kiện có `event_type` (`engagement`, `family_ceremony`, `religious_ceremony`, `reception`, `other`) và `host_side` (`groom`, `bride`, `both`); các trường khác (ngày, giờ, múi giờ, địa điểm, tọa độ, link chỉ đường) ở `docs/spec/03-mo-hinh-du-lieu.md` › events.
- `event_name` để `null` thì `display_name` là tên mặc định theo loại lễ và bên ("Lễ vu quy", "Tiệc cưới nhà trai"…). Loại `other` bắt buộc có tên; lễ gia tiên (`family_ceremony`) không nhận `both`; giờ kết thúc phải sau giờ bắt đầu; tọa độ phải đủ cặp.
- Danh sách trả theo thứ tự hiển thị: ngày, rồi giờ bắt đầu, rồi thứ tự thêm vào; sự kiện chưa có ngày xếp cuối. `position` do server quản lý.
- Thêm, sửa (Merge Patch), xoá đều cần `If-Match` với revision của thiệp và trả `ETag` mới.
- `primary_event_date` của thiệp là ngày sớm nhất trong các sự kiện, server tự tính.

### Upload ảnh và nhạc nền (3 bước, file không đi qua backend)

```ts
// 1. Xin link upload; ảnh hay âm thanh suy ra từ content_type
const ticket = await api.post(`/invitations/${id}/media/upload-url`, {
  filename: file.name, content_type: file.type, size_bytes: file.size,
  album_id, // chỉ ảnh mới nằm trong album; âm thanh bỏ trường này
});
// 2. PUT file thẳng lên storage, đúng header backend trả về
await fetch(ticket.upload_url, { method: "PUT", headers: ticket.headers, body: file });
// 3. Xác nhận. Ảnh gửi kèm kích thước để trang thiệp dựng layout không bị giật; âm thanh gửi {}
const size = isImage ? await readImageSize(file) : {};
const media = await api.post(`/invitations/${id}/media/${ticket.media_id}/complete`, size);
```

- Ảnh: `image/jpeg`, `image/png`, `image/webp`, `image/avif`, tối đa 15 MB, 200 ảnh mỗi thiệp. Âm thanh: `audio/mpeg`, `audio/mp3`, `audio/mp4`, `audio/x-m4a`, tối đa 10 MB, 1 file mỗi thiệp.
- Sai loại file hoặc quá dung lượng → 422; vượt số lượng → 400 `media_limit`. Số lượng tính cả file đang upload dở, nên đổi nhạc thì xoá file cũ trước.
- Backend kiểm tra lại dung lượng và loại file thật ở bước 3, vì link presigned không giới hạn được dung lượng. Nên nén ảnh ở trình duyệt trước khi upload (ví dụ chuyển sang WebP, cạnh dài khoảng 2000px).
- Gắn file vào thiệp bằng `PATCH /invitations/{invitation_id}`: `cover_media_id`, `groom_photo_media_id`, `bride_photo_media_id` nhận ảnh, `music_media_id` nhận âm thanh; ảnh của một mốc câu chuyện là `content.love_story[].media_id`. File chưa `ready`, sai loại hoặc của thiệp khác → 422 `invalid_reference`.
- `DELETE /invitations/{invitation_id}/media/{media_id}` tự gỡ file khỏi mọi chỗ thiệp đang dùng (cột `*_media_id`, `love_story`).

### Mừng cưới

- `GET /banks` trả `[{bin, short_name, name}]` lấy từ danh sách ngân hàng công khai của VietQR, dùng cho dropdown.
- `content.gifts` tối đa 4 tài khoản, mỗi tài khoản có `recipient_side` (`groom` hoặc `bride`), `bank_bin` (phải có trong danh sách), `account_number` (6–19 chữ số; FE bỏ khoảng trắng và dấu chấm trước khi gửi) và `account_holder`. Mã QR do template sinh theo chuẩn VietQR.

### Đăng thiệp

- `POST /invitations/{invitation_id}/publish` thành công khi có họ tên cô dâu và chú rể, có ít nhất một sự kiện và sự kiện nào cũng có ngày, giờ bắt đầu, địa chỉ, và `appearance.sections` có `cover` và `events`. Thiếu → 400 `not_ready_to_publish`, `details` liệt kê đường dẫn từng trường còn thiếu.
- Thiệp đã đăng vẫn sửa được và thay đổi hiện ngay cho khách (v1 chưa tách bản nháp khỏi bản đã đăng). Mọi lần sửa phải giữ đủ các điều kiện trên, nếu không → 400 `breaks_published_invitation` với `details` cùng dạng.
- `POST /invitations/{invitation_id}/unpublish` gỡ thiệp khỏi trang public.

### Trang thiệp public

- Next.js có ba đường dẫn cho mỗi thiệp: `/{slug}`, `/{slug}/nha-trai`, `/{slug}/nha-gai`, lần lượt gọi `GET /public/invitations/{slug}` không tham số, với `?side=groom` và với `?side=bride`. Chỉ trả thiệp đã đăng.
- Có `side` thì chỉ trả sự kiện của bên đó và của cả hai bên, cùng tài khoản mừng cưới của bên đó. Response có `side` để template chọn câu báo hỷ và thứ tự hai gia đình. `side` khác `groom`, `bride` → 422.
- Response gồm `slug`, `template_key`, `side`, `content_schema_version`, `content`, bốn cột `*_media_id`, `events`, `albums`, `gallery`, `media_by_id`, `published_at`, `updated_at`; không có `owner_id`, `status`, `revision`.
  - `events`: mỗi sự kiện có thêm `display_name` và `lunar_date` (`{day, month, year, is_leap_month, year_name}` theo lịch Việt Nam, `null` khi chưa có ngày).
  - `gallery`: `[{media_id, album_id}]` theo thứ tự thư viện ảnh; template tự giới hạn theo `max_gallery_images` của manifest.
  - `media_by_id`: map từ ID sang `{kind, url, width, height}` cho mọi file `ready`. Mọi tham chiếu file là ID, template tra URL ở đây.
- Header `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=600`. Next.js render bằng ISR rồi chọn component theo `template_key`.
- Khi thiệp đã đăng thay đổi (sửa thiệp, sự kiện, xoá file, đăng, gỡ, xoá thiệp), backend gọi `FRONTEND_REVALIDATE_URL` với body `{"slugs": [...]}` và header `x-revalidate-secret`. Route này ở Next.js build lại cả ba đường dẫn của từng slug.

### Nội dung thiệp (`content`)

`content` (schema version 1, trường `content_schema_version`) chỉ chứa dữ liệu hiển thị. Schema đầy đủ ở `docs/spec/03-mo-hinh-du-lieu.md` › Nội dung thiệp và `InvitationContent` trong OpenAPI.

| Nhóm | Nội dung |
| --- | --- |
| `couple` | `groom`, `bride`: họ tên, tên gọi in to, thứ bậc trong nhà, giới thiệu, bố mẹ (`is_deceased` để template in chữ "Cố"), địa chỉ gia đình |
| `messages` | `greeting` (lời ngỏ của cặp đôi), `invitation_message` (câu mời của gia đình), `guest_notes` (thông tin thực tế cho khách) |
| `love_story` | Tối đa 12 mốc: `title`, `description`, `year`, `month`, `media_id` |
| `gifts` | Tối đa 4 tài khoản mừng cưới (mục Mừng cưới) |
| `appearance` | `palette_key`, `font_key`, `background_key` (trong manifest của mẫu, `null` thì dùng mặc định), `sections` (section hiển thị theo thứ tự) |

Sự kiện và các ảnh, nhạc cố định không nằm trong `content`. Trường lạ bị từ chối: muốn thêm trường thì sửa spec và schema trước.

## Lên production

- **Biến môi trường:** `APP_ENV=production`, `JWT_SECRET` ngẫu nhiên ≥ 32 ký tự, `COOKIE_SECURE=true`, `CORS_ORIGINS` là domain Next.js. Nếu FE và API khác site (ví dụ `*.vercel.app` và `api.thiepcuoi.vn`) thì đặt `COOKIE_SAMESITE=none`; tốt nhất là dùng chung domain gốc (`thiepcuoi.vn` và `api.thiepcuoi.vn`). Các giới hạn `MAX_*` có trong `.env.example`.
- **Cloudflare R2:** tạo bucket và API token (quyền Object Read & Write cho bucket đó), gắn custom domain để đọc file công khai (`MEDIA_PUBLIC_BASE_URL`), thêm CORS rule cho phép `PUT` và `GET` từ domain Next.js. `S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, `S3_REGION=auto`.
- **Migration:** chạy `uv run alembic upgrade head` trước mỗi lần deploy. Khi đã có dữ liệu production, đổi model thì thêm migration mới (`uv run alembic revision --autogenerate -m "mo ta"`), đọc lại file sinh ra rồi mới commit.
- Swagger (`/docs`) tự tắt khi `APP_ENV=production`.

## Ngoài phạm vi v1

Chưa làm trong v1; hướng thiết kế đã ghi ở `docs/spec/07-ngoai-pham-vi.md`: RSVP và danh sách khách, sổ lời chúc, nhiều người cùng sửa một thiệp, tách bản nháp khỏi bản đã đăng, thanh toán gói trả phí (mẫu `is_premium` hiện bị chặn ở `templates/service.py::get_usable_by_key`), thư viện nhạc có bản quyền, bảo mật tài khoản (giới hạn tần suất, quên mật khẩu, xác minh email, đăng nhập Google/Zalo), job dọn file `pending` và refresh token hết hạn, xử lý ảnh phía server, sự kiện kéo qua nửa đêm.
