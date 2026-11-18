# Bàn giao ngữ cảnh: backend Thiệp Cưới

Viết ngày 18/11/2026 để mang sang repo mới. File tóm tắt repo `Startup` (https://github.com/hieutran-12/Startup) và các quyết định trong phiên làm việc 16–18/11/2026. Chi tiết đầy đủ vẫn nằm ở các file được trỏ tới; repo mới nên chép kèm `docs/spec/`, `CLAUDE.md` và `README.md`.

## 1. Tóm tắt nhanh

- **Sản phẩm:** backend v1 cho dịch vụ thiệp cưới online. Cặp đôi chọn mẫu, nhập nội dung, sự kiện, ảnh, nhạc rồi đăng thiệp lên một slug; khách mở trang public, có link riêng cho nhà trai và nhà gái.
- **Trạng thái:** xong cả 11 bước kế hoạch. 765/765 test qua, ruff sạch, `alembic check` sạch (18/11/2026, commit `8ae70ec`).
- **Hướng deploy hiện tại:** dùng toàn bộ dịch vụ AWS (quyết định 18/11/2026). Tài liệu deploy trong repo cũ vẫn đang mô tả VPS: xem mục 8.
- **Chưa có dữ liệu production.** Chưa deploy lên đâu cả.
- **Commit `8ae70ec` chưa push** lên GitHub (`main` đi trước `origin/main` 1 commit). Push trước khi clone sang repo mới.

## 2. Stack và cấu trúc

- Python 3.13, FastAPI, Pydantic strict (`extra="forbid"`), SQLAlchemy 2.0 async (asyncpg), PostgreSQL 16, Alembic, uv, pytest, ruff.
- File lưu qua S3 API (boto3): local dùng RustFS 1.0.4 trong docker-compose; code chạy được với AWS S3 (IAM role).
- Trang public do Next.js render (repo khác); backend gửi webhook revalidate.

```text
app/core/       config, db (naming convention), types (kiểu chuẩn hóa), schemas (StrictModel),
                errors, merge_patch, revision (ETag/If-Match), lunar, security, deps, storage, revalidate
app/modules/    auth, templates, invitations, events, media, banks   (models/schemas/service/router)
app/scripts/    seed_templates, init_storage
alembic/        một migration 0001 cho toàn bộ schema
docs/spec/      đặc tả 01–07, nguồn chuẩn
docs/modules/   hiện trạng code từng module (Claude tự cập nhật)
docs/progress.md  tiến độ
tests/          pytest với PostgreSQL thật, storage giả (FakeStorage trong conftest.py)
```

## 3. Cách làm việc đã thống nhất (chi tiết: `CLAUDE.md`)

- `docs/spec/` là nguồn chuẩn. Code cần khác spec thì dừng, nêu chỗ khác và hỏi; được đồng ý thì sửa spec trước, code sau. Không tự thêm trường, bảng, endpoint ngoài spec.
- Việc lớn: nêu kế hoạch ngắn, chờ duyệt. Làm bước kế hoạch: viết test theo tiêu chí nghiệm thu trước.
- Sau mỗi bước: chạy `pytest` và `ruff`, cập nhật `docs/modules/<tên>.md` và `docs/progress.md`, commit ghi rõ bước và module.
- 14 nguyên tắc dữ liệu (spec 02): một trường một nghĩa và một kiểu; đơn vị nằm ở tên trường (`size_bytes`, `amount_vnd`); tập giá trị cố định thì không dùng chuỗi tự do; dữ liệu tính được thì không lưu; mọi chuỗi trim và NFC; API không đoán ý (sai thì từ chối, không tự sửa); tham chiếu bằng ID; mã toàn chữ số là chuỗi.
- Đặt tên: snake_case; bảng số nhiều; constraint `pk_ uq_ fk_ ck_ ix_`; schema hậu tố `Create`/`Update`/`Response`; service là hàm, không phải class; slug kebab-case.

## 4. Mô hình dữ liệu (chi tiết: spec 03)

7 bảng: `users`, `refresh_tokens`, `templates`, `invitations`, `events`, `media`, `albums`.

- **Một thiệp dùng chung cho hai bên.** Mỗi sự kiện có `host_side` (`groom`, `bride`, `both`).
- **`invitations.content`** là JSONB có `content_schema_version` (hiện là 1), gồm:
  - `couple.groom`, `couple.bride`: `full_name`, `display_name`, `birth_order`, `bio`, `father`/`mother` (`full_name`, `is_deceased`), `family_address`
  - `messages`: `greeting`, `invitation_message`, `guest_notes`
  - `love_story`: tối đa 12 mốc (`title`, `description`, `year`, `month`, `media_id`)
  - `gifts`: tối đa 4 tài khoản (`recipient_side`, `bank_bin`, `account_number`, `account_holder`)
  - `appearance`: `palette_key`, `font_key`, `background_key` (theo manifest của mẫu), `sections`
- **Ảnh bìa, chân dung, nhạc nền** là cột `cover_media_id`, `groom_photo_media_id`, `bride_photo_media_id`, `music_media_id`, mỗi cột có khóa ngoại kép `(id, <cột>) → media (invitation_id, id)` với `ON DELETE SET NULL (<cột>)`. Cần PostgreSQL ≥ 15.
- **`events`** là bảng riêng: `event_type` (`engagement`, `family_ceremony`, `religious_ceremony`, `reception`, `other`), ngày, giờ `HH:MM`, `timezone` IANA, địa điểm, tọa độ NUMERIC(9,6), `maps_url`. CHECK: lễ gia tiên không nhận `both`, `other` bắt buộc có tên, giờ kết thúc sau giờ bắt đầu, tọa độ đủ cặp.
- **`media`**: `kind` `image`/`audio`, `status` `pending`/`ready`; âm thanh không có kích thước, không nằm trong album.
- **`templates`**: 4 mẫu seed sẵn, có `manifest` (section, bảng màu, font, nền, mặc định); mẫu `is_premium` bị chặn (chưa có thanh toán).

## 5. Nghiệp vụ chính (chi tiết: spec 04)

- **Sửa thiệp:** `PATCH` theo JSON Merge Patch; `null` là xoá, danh sách bị thay nguyên. Chống ghi đè bằng `revision`: response có `ETag: "<revision>"`, ghi phải gửi `If-Match` (thiếu → 428, lệch → 409).
- **Đổi template:** key giao diện không có trong mẫu mới về `null`; `sections` giữ phần mẫu mới hỗ trợ.
- **Publish** cần: họ tên cô dâu và chú rể; ít nhất một sự kiện; mỗi sự kiện có ngày, giờ bắt đầu, địa chỉ; `sections` có `cover` và `events`. Thiếu → 400 `not_ready_to_publish`. Thiệp đã đăng mà sửa làm mất điều kiện → 400 `breaks_published_invitation`.
- **Link theo bên:** `GET /public/invitations/{slug}?side=groom|bride` chỉ trả sự kiện của bên đó (và của cả hai) cùng tài khoản mừng cưới của bên đó. Sự kiện có `display_name` và `lunar_date` (âm lịch Việt Nam UTC+7, tự cài thuật toán Hồ Ngọc Đức).
- **Upload 3 bước:** xin link presigned → trình duyệt PUT thẳng lên storage → `/complete`. Link ký cả `Content-Type` và dung lượng khai báo (`size_bytes`), storage từ chối PUT khác loại hoặc khác dung lượng.
- **Xoá file** tự gỡ khỏi mọi chỗ thiệp đang dùng (4 cột và `love_story`), tăng revision.
- **Ngân hàng:** `banks.json` tĩnh 76 mục từ VietQR; `bank_bin` lạ → 422.
- **Giới hạn:** 5 thiệp mỗi tài khoản, 10 sự kiện mỗi thiệp, 200 ảnh (15 MB) và 1 file âm thanh (10 MB) mỗi thiệp. Ảnh: jpeg, png, webp, avif; âm thanh: `audio/mpeg`, `audio/mp3`, `audio/mp4`, `audio/x-m4a`.
- **Auth:** access token JWT 15 phút (header `Bearer`); refresh token ngẫu nhiên 30 ngày trong cookie httpOnly path `/auth`, xoay vòng mỗi lần dùng; dùng lại token cũ sau 20 giây thì thu hồi mọi phiên. Mật khẩu Argon2id, băm ở threadpool.
- **Revalidate:** khi thiệp đã đăng thay đổi, backend POST `{"slugs": [...]}` tới `FRONTEND_REVALIDATE_URL` với header `x-revalidate-secret`.

## 6. API (danh sách đầy đủ, có test so với OpenAPI: `README.md` › API)

| Nhóm | Endpoint |
| --- | --- |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /me` |
| Mẫu thiệp | `GET /templates`, `GET /templates/{key}` |
| Thiệp | `GET`/`POST /invitations`, `GET /invitations/slug-availability`, `GET`/`PATCH`/`DELETE /invitations/{id}`, `POST .../publish`, `POST .../unpublish` |
| Sự kiện | `GET`/`POST /invitations/{id}/events`, `PATCH`/`DELETE .../events/{event_id}` |
| File | `POST .../media/upload-url`, `POST .../media/{media_id}/complete`, `GET .../media`, `PUT .../media/order`, `PATCH`/`DELETE .../media/{media_id}` |
| Album | `GET`/`POST .../albums`, `PATCH`/`DELETE .../albums/{album_id}` |
| Khác | `GET /banks`, `GET /public/invitations/{slug}`, `GET /health` |

Mọi lỗi có dạng `{"error": {"code", "message", "details": [{"field", "code", "message"}]}}`. Mã trường: `required`, `invalid_format`, `invalid_characters`, `too_long`, `out_of_range`, `invalid_choice`, `unknown_field`, `invalid_reference`.

## 7. Diễn biến trong phiên 16–18/11/2026

1. **Rà soát backend (16/11):** 762 test qua, chạy thử luồng thật (đăng ký → tạo thiệp → sự kiện → upload ảnh → publish → trang public → xoá) trên PostgreSQL và RustFS: đúng. Tìm thấy lỗ hổng: dùng lại link presigned sau `/complete` ghi đè được file 16 MB.
2. **Tài khoản AWS (16/11):** người dùng có tài khoản AWS gói miễn phí mới (mục 9) và làm các nhiệm vụ nhận thêm credit.
3. **Đổi sang VPS (16/11, commit `3b93f61`):** người dùng thấy AWS không cần cho dự án cỡ này. Thêm `docker-compose.prod.yml` (Caddy, API, PostgreSQL, RustFS), `docker/Caddyfile`, `.env.production.example`; `init_storage` chạy được ở production; README › Lên production viết lại cho VPS. Đã chạy thử trong WSL với domain `*.localhost`, chưa thử trên VPS thật.
4. **Sửa nốt (16/11, commit `8ae70ec`):** link upload ký thêm `Content-Length` (bịt lỗ hổng ở bước 1, đã thử trên RustFS); băm mật khẩu chạy ở threadpool; ghim `rustfs/rustfs:1.0.4`; giới hạn log container; dựng lại `.venv`.
5. **Đổi lại sang AWS (18/11):** người dùng quyết định dùng toàn bộ dịch vụ AWS và chuyển sang repo mới. Chưa sửa gì trong repo cũ theo quyết định này.

## 8. Deploy lên AWS

### Kiến trúc mục tiêu

Theo bản chuẩn bị ngày 09/11/2026 (commit `decfb90`). Những mục ghi "chưa chốt" là việc phải quyết ở repo mới.

| Thành phần | Dịch vụ AWS |
| --- | --- |
| Image Docker của API | ECR |
| Chạy container API | ECS (Fargate hay EC2: chưa chốt) |
| HTTPS cho API | Application Load Balancer + chứng chỉ ACM (chưa chốt domain) |
| Database | RDS PostgreSQL 16 |
| File ảnh, nhạc | S3, bật Block Public Access |
| Đọc file công khai | CloudFront với Origin Access Control tới bucket |
| Quyền cho API | IAM task role (không dùng access key) |
| Secret (`JWT_SECRET`, mật khẩu DB) | Chưa chốt (biến môi trường của task, hoặc Secrets Manager / SSM) |

### Code đã sẵn sàng cho AWS

- `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` để trống → boto3 lấy quyền từ IAM role; URL dạng `https://<bucket>.s3.<region>.amazonaws.com/...`. `S3_REGION` phải là region thật (`ap-southeast-2`), để `auto` thì app không khởi động.
- `MEDIA_PUBLIC_BASE_URL=https://<id>.cloudfront.net` (hoặc domain riêng gắn CloudFront).
- `DATABASE_URL=postgresql+asyncpg://<user>:<mật khẩu>@<endpoint RDS>:5432/<db>?ssl=require` (RDS PostgreSQL 16 mặc định bắt buộc SSL; `ssl=require` không kiểm tra chứng chỉ server).
- Production cần: `APP_ENV=production`, `JWT_SECRET` ≥ 32 ký tự, `COOKIE_SECURE=true`, `CORS_ORIGINS` là domain Next.js; FE và API khác site thì `COOKIE_SAMESITE=none`.
- `Dockerfile`: `python:3.13-slim`, uv 0.13.7, user không phải root, `uvicorn --proxy-headers --forwarded-allow-ips *` cổng 8000; health check `GET /health`. Migration và seed chạy bằng chính image (`alembic upgrade head`, `python -m app.scripts.seed_templates`).
- IAM role cần `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` trên `arn:aws:s3:::<bucket>/*`.
- CORS của bucket: `AllowedOrigins` là domain Next.js, `AllowedMethods` `PUT`, `GET`, `HEAD`, `AllowedHeaders` `*`, `ExposeHeaders` `ETag`. Tên bucket không có dấu chấm.
- `init_storage` từ chối chạy khi `S3_ENDPOINT_URL` trống: bucket AWS cấu hình bằng console hoặc IaC, không bằng script này.

### Việc phải làm khi chuyển sang AWS

- README › Lên production, comment trong `Dockerfile` và `.env.example` đang mô tả VPS. Nội dung AWS cũ có ở commit `decfb90`.
- `docker-compose.prod.yml`, `docker/Caddyfile`, `.env.production.example` chỉ dùng cho VPS: bỏ đi hoặc giữ làm phương án dự phòng (chưa quyết).
- Bản VPS chặn body request của API ở 1 MB bằng Caddy. Trên AWS chưa có lớp tương đương; cần chọn cách giới hạn khác.
- Chưa kiểm chứng: link presigned ký `Content-Length` trên AWS S3 thật (mới thử trên RustFS); toàn bộ kiến trúc chưa từng được dựng.

## 9. Tài khoản AWS hiện có

Không ghi ID tài khoản ở đây; xem trong console.

- Giao diện AWS mới cho tài khoản mới (ra mắt 16/09/2026): mỗi **project** chứa một tài khoản AWS. Project của người dùng tên **"Lift Off Soon"**, region **ap-southeast-2 (Sydney)**. Quản lý project, team, billing ở AWS Settings (`settings.aws.com`).
- **Gói Free** (xem ngày 16/11/2026): còn $100.00 credit, còn 182 ngày (tới 16/05/2027), số tiền phải trả $0.00. Không bị tính tiền tới khi bấm Upgrade. Chưa rõ tài nguyên ra sao khi hết credit hoặc hết hạn.
- **Credit thêm:** tối đa $100, mỗi nhiệm vụ $20, trong widget **Explore AWS** ở Console Home (filter "Earn AWS credits"). Đã tạo budget "My Zero-Spend Budget". Người dùng làm tiếp các nhiệm vụ DynamoDB, Lambda, RDS, EC2 nhưng chưa xác nhận trạng thái "Completed". Nhiệm vụ Bedrock bị `ThrottlingException` (tài khoản mới bị giới hạn token theo ngày) nên bỏ qua. Cần xoá các tài nguyên thử (bảng DynamoDB, hàm Lambda, database RDS, server EC2) nếu chưa xoá.
- **Dịch vụ dùng được trên gói Free** (theo tài liệu AWS, chưa thử): ECS, EC2, RDS, S3, CloudFront, IAM đều có trong danh sách hỗ trợ. Không hỗ trợ: tính năng nhiều region, IAM Identity Center, Lambda@Edge. Trang "All services" của console tô xám dịch vụ không dùng được.
- **Không bật "Activate advanced features"** khi chưa cần: không đảo ngược được, gỡ hạn mức chi tiêu. Sau khi Upgrade, mỗi project có hạn mức chi tiêu theo tháng (từ $20); chạm hạn mức thì AWS tạm dừng project.
- Tài liệu: [Sign in to the new AWS experience](https://docs.aws.amazon.com/accounts/latest/reference/sign-in-new.html), [Supported services](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html), [Activate advanced features](https://docs.aws.amazon.com/accounts/latest/reference/activate-advanced-features.html), [Earning additional credits](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans-activities.html).

## 10. Việc còn mở

| Việc | Trạng thái |
| --- | --- |
| Giới hạn tần suất đăng nhập, đăng ký | Spec 07 xếp ngoài v1; cần người dùng duyệt sửa spec. Nên làm trước khi mở công khai |
| Xác minh email, quên mật khẩu, đăng nhập Google/Zalo | Ngoài v1 (spec 07) |
| Job dọn file `pending`, file mồ côi, refresh token hết hạn | Ngoài v1 (spec 07) |
| Link upload còn hạn 10 phút sau `/complete` vẫn ghi đè được bằng file cùng dung lượng, cùng loại | Muốn bịt thì phải đổi luồng upload trong spec |
| Bản spec trên Claude Docs ("Đặc tả backend thiệp cưới v1", rev 15) thiếu `audio/mp3`, `audio/x-m4a` | Spec trong repo đã đúng |
| Kiến trúc AWS (mục 8) | Chưa chốt Fargate/EC2, domain, cách giữ secret; chưa dựng |

## 11. Môi trường dev của người dùng

- Windows 11, VS Code, Claude Code. Docker Engine 29.9 chạy trong WSL2 Ubuntu (không có Docker Desktop); app và test ở Windows gọi `localhost:5432`, `localhost:9000`.
- **WSL tự tắt** khoảng 15 giây sau khi không còn tiến trình nào giữ, container dừng theo, pytest báo hàng loạt `ConnectionRefusedError`: giữ một cửa sổ Ubuntu mở rồi chạy `docker compose up -d`.
- `alembic.ini` chỉ chứa ký tự ASCII (Alembic đọc bằng cp1252); chạy script qua pipe thì đặt `PYTHONIOENCODING=utf-8`.
- Launcher `.exe` trong `.venv` từng hỏng (`uv trampoline failed to canonicalize script path`); `uv sync --reinstall` đã sửa. Cách tạm: `uv run python -m pytest`.
- Đã bàn chuyển repo vào trong WSL (`~/projects/Startup`, cài uv, `uv sync`) để tránh các lỗi trên; người dùng chưa làm.

## 12. Cách trao đổi với người dùng

- Trả lời bằng tiếng Việt, câu đơn giản.
- Khi hướng dẫn thao tác trên console (AWS), viết từng bước đánh số, làm từng nhiệm vụ một; người dùng gửi ảnh chụp màn hình để hỏi tiếp. Nói rõ khi màn hình có thể khác với hướng dẫn.
- Người dùng đổi hướng hạ tầng nhiều lần (AWS → VPS → AWS): trước khi sửa lớn tài liệu deploy, xác nhận lại hướng hiện tại.

## 13. Lệnh thường dùng

```sh
cp .env.example .env
docker compose up -d                          # PostgreSQL :5432, RustFS :9000
uv sync
uv run alembic upgrade head
uv run python -m app.scripts.seed_templates
uv run python -m app.scripts.init_storage     # chỉ cho RustFS
uv run fastapi dev app/main.py                # http://localhost:8000/docs
uv run pytest                                 # database thiepcuoi_test
uv run ruff check . && uv run ruff format .
uv run alembic check
```

Sửa migration 0001 thì dựng lại DB dev: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` rồi upgrade và seed.
