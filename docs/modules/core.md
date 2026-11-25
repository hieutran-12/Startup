# core

## Mục đích
Hạ tầng dùng chung: cấu hình, database, bảo mật, storage, webhook revalidate. Bước 1: tầng chuẩn hóa dữ liệu request, định dạng lỗi chung. Bước 2: migration 0001 viết lại. Bước 4: Merge Patch, ETag/If-Match. Bước 5: kiểu tọa độ, URL; `max_events_per_invitation`. Bước 7: giới hạn upload theo loại file trong `config.py`. 2026-11-06: kiểu `Email`, `Password` cho auth. 2026-11-09: storage chạy với AWS S3 (IAM role), `Dockerfile`. 2026-11-16: production trên VPS (đã bỏ). 2026-11-23: production trên AWS EC2.

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
- `config.py` (2026-11-09): `s3_access_key_id`, `s3_secret_access_key` nhận `None` (env để trống); `check_storage_settings` (xem mục Storage)
- `storage.py`: giữ từ khung; 2026-11-09 chọn kiểu địa chỉ theo endpoint (xem mục Storage)
- `security.py`, `deps.py`, `revalidate.py`: giữ từ khung
- `Dockerfile`, `.dockerignore` ở gốc repo (2026-11-09): image production, mô tả ở README › Lên production
- `docker-compose.prod.yml`, `.env.production.example`, `docker/nginx-api.conf`, `docker/ec2-user-data.sh`: production trên AWS EC2 (2026-11-23)

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

## Production trên AWS EC2 (2026-11-23, người dùng chốt hướng này)
- Dựng bằng AWS CLI, bảng tài nguyên ở README › Lên production: EC2 `t4g.small` Ubuntu 24.04 arm64 có Nginx trên máy, container API lấy image từ ECR (`docker-compose.prod.yml`), RDS PostgreSQL 16.15 `db.t4g.micro`, S3 `thiepcuoi-media-prod` sau CloudFront (OAC), IAM role `thiepcuoi-api-ec2-role`, secret ở SSM Parameter Store. Không đổi model, migration, endpoint, spec. Bản VPS 2026-11-16 (Caddy, PostgreSQL và RustFS trong compose) đã bỏ ở commit `4c91757`, `49caf62`.
- Gói Free của AWS chỉ cho giữ backup RDS 1 ngày (đặt 7 thì `FreeTierRestrictionError`).
- IAM role có `s3:ListBucket` trên bucket: thiếu quyền này thì `HeadObject` cho file chưa upload trả 403 thay vì 404, `storage.head` raise và `/complete` thành 500.
- Container lấy quyền IAM qua IMDSv2 nên EC2 đặt hop limit 2 (mặc định 1 thì request từ container không tới được metadata).
- Image build arm64 trên Mac (Colima) 160 MB, chạy thẳng trên Graviton.
- Đã chạy thử trên production (HTTP qua Elastic IP): link presigned ký `Content-Length` trên AWS S3 thật đúng như RustFS (đúng dung lượng 200; thừa 1 byte, sai dung lượng, sai loại 403; dùng lại link cùng dung lượng và loại vẫn 200, việc treo đã biết); preflight CORS của bucket đúng origin; đăng ký → tạo thiệp → sự kiện → upload → `/complete` → gắn ảnh bìa → publish → trang public (`?side=groom`, âm lịch) → đọc ảnh qua CloudFront 200, đọc thẳng S3 403 → xoá ảnh, xoá thiệp. Dữ liệu thử đã xoá. Log có IP thật của client (Nginx đặt `X-Forwarded-For`).
- File đã xoá vẫn được CloudFront trả từ cache tới 24 giờ (TTL mặc định của `CachingOptimized`); code chưa tạo invalidation.
- 2026-11-24, chưa có tiền mua domain: HTTPS qua subdomain miễn phí DuckDNS `thiepcuoi-api.duckdns.org` (trỏ về Elastic IP) + Let's Encrypt (`certbot --nginx --redirect`, không đăng ký email, `certbot.timer`, gia hạn thử `--dry-run` thành công); http → https 301. `COOKIE_SAMESITE=none` để web khác domain giữ được cookie (Safari vẫn chặn cookie bên thứ ba). Chạy lại luồng thử qua https: đúng; cookie `HttpOnly; Path=/auth; SameSite=none; Secure`; `POST /auth/refresh` bằng cookie 200. Dữ liệu thử đã xoá.
- 2026-11-24, domain `ketduyen.me` (Namecheap, GitHub Student Pack; người dùng chọn web trên Amplify, không chung server với API): API ở `api.ketduyen.me` (bản ghi A về Elastic IP; chứng chỉ certbot tên `api.ketduyen.me` phủ cả tên DuckDNS cũ, chứng chỉ DuckDNS riêng đã xoá; `--dry-run` thành công). `.env`: `CORS_ORIGINS=https://ketduyen.me`, `COOKIE_SAMESITE=lax`; CORS của bucket `https://ketduyen.me`, `http://localhost:5173`. Web: Amplify `ketduyen-web` nối GitHub (monorepo `my-fe-app`), ALIAS `@` và CNAME `www` về CloudFront của Amplify. Rule Amplify: rule theo domain viết `https://www.ketduyen.me` không kèm `/<*>` (có đường dẫn thì bị bỏ qua, không báo lỗi); rule mặc định `/<*>` → `/index.html` `404-200` làm route SPA 301 thêm `/` rồi 404, thay bằng regex SPA (200). Chạy thử luồng thật qua `api.ketduyen.me` với `Origin: https://ketduyen.me`: 18/18 đúng (preflight origin lạ 400; cookie `Path=/auth; SameSite=lax; Secure`; preflight S3 200). Dữ liệu thử đã xoá.
- 2026-11-24, chuyển CI/CD sang GitLab (người dùng chọn hướng A: không Kubernetes): repo gốc `gitlab.com/ketduyen/thiepcuoi-api` (private), GitHub `hieutran-12/Startup` sẽ là bản sao. Giai đoạn 1: `.gitlab-ci.yml` stage `lint`, `test`; `workflow:rules` chạy pipeline MR, bỏ pipeline nhánh khi nhánh đã có MR mở; image `ghcr.io/astral-sh/uv:0.13.7-python3.13-trixie-slim` (tag `bookworm` không có); service `postgres:16-alpine` alias `postgres`; pytest xuất JUnit cho tab Tests. Cache uv ở `.uv-cache` trong project (GitLab chỉ cache được đường dẫn trong project): phải loại khỏi ruff (`extend-exclude`, không dựa vào `.gitignore` vì ruff chỉ đọc `.gitignore` khi có `.git`), nếu không ruff quét cả thư viện (33.892 lỗi). Chạy thử 2 job trên máy bằng đúng image (đưa code vào container bằng `tar` qua stdin: Colima không chia sẻ `/private/tmp`).
- 2026-11-25, CI/CD GitLab đủ 5 stage (người dùng duyệt hướng A): `build` (runner `saas-linux-small-arm64`, `docker:27` + `docker:27-dind --mtu=1400`, OIDC `id_tokens` → role `thiepcuoi-gitlab-ci`, ECR tag `$CI_COMMIT_SHORT_SHA`), `deploy-staging`, `smoke-staging`, `deploy-production` (`when: manual`, `resource_group`). `deploy/ssm-run.sh` gửi `deploy.sh` qua SSM dạng gzip+base64 (chỉ chữ số nên nhét vào JSON an toàn) và chỉ nhận tham số khớp regex. `deploy/deploy.sh`: `flock`; tải image trước rồi mới ghi tag vào `.env`; migration bằng image mới trước khi nhận request; blue-green đổi `thiepcuoi-upstream.conf` rồi `nginx -s reload`, kiểm tra `https://api.ketduyen.me/health` qua `--resolve` 5 lần, lỗi thì trả upstream cũ. Staging: database `thiepcuoi_staging` với user riêng, `REVOKE CONNECT ... FROM PUBLIC` trên cả 2 database (user staging không vào được production); bucket + CloudFront riêng dùng chung OAC; `APP_ENV=staging` (Swagger mở). Compose `env_file` dạng `required: false` để file env của môi trường khác thiếu cũng không chặn. Chuyển production sang blue-green: chạy `api-green` song song container cũ, đổi Nginx, kiểm tra, rồi mới xoá container cũ: 18/18 request trả 200. Thử deploy, rollback, deploy lại: 56/56 trả 200; tag không tồn tại thì dừng ở `docker pull`. Lần đầu `certbot` cho staging báo "unexpected error", chạy lại thì được.
- 2026-11-25, chạy pipeline thật lần đầu: MR !1 merge (`c155caf`), 5/5 stage xanh khoảng 6 phút; production `green` = `c155caf6`, `blue` giữ `e995527`. Đo 15 phút lúc bấm duyệt: 644/646 trả 200, 2 lần lỗi đều ngoài lúc đổi màu (mạng phía máy đo). Push mirror GitLab → GitHub `hieutran-12/Startup` (chỉ nhánh protected, token GitHub classic scope `repo`); trên máy dev remote GitHub đổi tên `github`, khoá push.
- 2026-11-25, cảnh báo khi API chết (người dùng duyệt kiến trúc): stack CloudFormation `thiepcuoi-monitoring` (`infra/monitoring.yml`): EventBridge Scheduler `rate(1 minute)` → Lambda `thiepcuoi-uptime` (python3.13 arm64, code inline `ZipFile`) → metric `Thiepcuoi/Uptime` `Healthy`/`LatencyMs` → alarm Minimum < 1 trong 3/3 phút, `TreatMissingData: breaching` → SNS `thiepcuoi-alerts` → email (tham số `AlertEmail`, để trống thì không tạo subscription). Không dùng Route 53 health check: SNS ở us-east-1 bị chặn (`AuthorizationError`, gói Free chỉ cho region của project). Đã thử code Lambda trên máy với CloudWatch giả (URL sai → 0), cfn-lint, `validate-template`.
- Chưa làm: `media.ketduyen.me` (CloudFront cần chứng chỉ ACM ở us-east-1, gói Free chặn tính năng nhiều region), revalidate (web là Vite SPA), bỏ tên DuckDNS.

## Storage với AWS S3 và image production (2026-11-09)
- Có `S3_ENDPOINT_URL` (RustFS): `addressing_style="path"`, URL `endpoint/bucket/key`. Endpoint trống (AWS S3): `addressing_style="virtual"` ghi rõ, URL `https://<bucket>.s3.<region>.amazonaws.com/key`. Để mặc định thì botocore 1.43 ký presigned URL trên endpoint toàn cầu `<bucket>.s3.amazonaws.com`; bucket mới tạo ngoài us-east-1 bị 307, trình duyệt PUT qua CORS sẽ lỗi.
- Hai key đều `None`: boto3 lấy quyền theo chuỗi mặc định (biến môi trường `AWS_*`, task role của ECS, instance profile của EC2). Test dùng biến môi trường `AWS_*` thay cho IAM role.
- `check_storage_settings` (app không khởi động nếu sai): chỉ đặt một trong hai key → lỗi; endpoint trống mà `S3_REGION` vẫn là `auto` → lỗi (`auto` chỉ hợp với storage tự đặt endpoint).
- Spec không nhắc nhà cung cấp cloud: phần này không đổi model, migration, endpoint, spec.
- `Dockerfile`: `python:3.13-slim`, uv 0.13.7 (đọc được `uv.lock` revision 5; nâng uv dev mà lock đổi revision thì nâng theo), `uv sync --locked --no-dev`, user không phải root, `uvicorn --proxy-headers --forwarded-allow-ips *` cổng 8000. Migration và seed chạy bằng chính image. Đã build và chạy thử 2026-11-10 (Docker Engine 29.9 trong WSL2): image 664 MB, trong `/app` chỉ có `alembic/`, `alembic.ini`, `app/`, `pyproject.toml`, `uv.lock` và `.venv`; container nối DB local trả `/health`, `/templates`, `/banks`.
- Trên Windows, `uvicorn.exe ... --forwarded-allow-ips *` bị launcher đổi `*` thành danh sách file; viết `--forwarded-allow-ips=*`. CMD dạng mảng trong Docker không bị.
- RDS: `DATABASE_URL` thêm `?ssl=require`; SQLAlchemy chuyển nguyên `ssl` sang `asyncpg.connect`.

## Lưu ý
- FastAPI validate body ở chế độ Python: trong `StrictModel`, khai báo `uuid.UUID`, `date`, `time` hay Enum gốc sẽ từ chối mọi chuỗi. Luôn dùng `Uuid`, `IsoDate`, `LocalTime`, `Choice`. Kiểu `str` thường không được chuẩn hóa: chỉ dùng cho key so khớp nguyên văn (ví dụ `Appearance.palette_key`).
- Lỗi độ dài chuỗi dùng loại `string_too_long` của Pydantic, vì `too_long` của Pydantic là lỗi độ dài danh sách (handler tra template tiếng Việt trước).
- Union không nullable (`A | B`) sẽ thêm tên nhánh vào `loc`; `_field_path` chưa xử lý trường hợp này.
- Strict ở chế độ Python không nhận số JSON cho `Decimal`: tọa độ dùng `Latitude`/`Longitude` (PlainValidator). Phần trăm (NUMERIC(5,2)) chưa có kiểu, chưa trường nào dùng.
- `json.loads` của Starlette nhận `NaN`, `Infinity`: kiểu số thập phân phải tự chặn số không hữu hạn.
- Schema request đã chuyển sang `StrictModel`: templates (Bước 3), invitations (Bước 4), events (Bước 5), media kể cả album (Bước 7), auth (2026-11-06, `Email`, `Password`). Không còn schema request nào dùng `BaseModel` thường.
