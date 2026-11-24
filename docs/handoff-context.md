# Bàn giao ngữ cảnh: Thiệp Cưới (backend và web)

Trạng thái ngày **24/11/2026**. Dành cho AI hoặc người mới mở repo backend `Startup`: đọc file này trước, rồi tới `CLAUDE.md`. File chỉ tóm tắt và ghi lại những điều không có trong code. Chi tiết đầy đủ nằm ở các file được trỏ tới.

## 1. Tóm tắt nhanh

- **Sản phẩm:** dịch vụ thiệp cưới online. Cặp đôi chọn mẫu, nhập nội dung, sự kiện, ảnh, nhạc rồi đăng thiệp lên một slug. Khách mở trang public, có link riêng cho nhà trai và nhà gái.
- **Backend (repo này):** xong cả 11 bước kế hoạch (spec 06). 765/765 test qua, ruff sạch. Production chạy trên AWS từ 23/11/2026.
- **Web:** repo riêng, Vite SPA, **chưa nối API** (đăng nhập còn giả lập).
- **Chưa có người dùng thật.** Database production chỉ có 4 mẫu thiệp đã seed.
- **Domain:** `ketduyen.me` (Namecheap, miễn phí 1 năm qua GitHub Student Pack, hết hạn 24/11/2027). Đang gắn: web lên AWS Amplify ở `ketduyen.me`, API ở `api.ketduyen.me`. Tiến độ ở mục 9.
- Tên thương hiệu chưa chốt: web đang để "Vows", định đổi thành "Chung Đôi" (`my-fe-app/src/config/site.ts`).

## 2. Hai repo

| | Backend | Web |
| --- | --- | --- |
| GitHub | `hieutran-12/Startup` | `HuongNguyenQuoc/SuperProject` |
| Trên máy người dùng | `~/Documents/myProject/Startup` | `~/Documents/myProject/SuperProject` (code ở `my-fe-app/`) |
| Stack | Python 3.13, FastAPI (mục 3) | Vite 5, React 18, TypeScript, Mantine 7, react-router 6, yarn v1 |
| Tài liệu cho AI | `CLAUDE.md`, file này | `CLAUDE.md`, `docs/backend.md` |

- Người dùng là chủ dự án, làm backend và hạ tầng cùng Claude ở repo này.
- Code gọi API của web (`http.ts`) do một bạn trong nhóm viết, **chưa push** (24/11). Repo web trên GitHub chưa gọi API nào.
- Không sửa code repo web từ phiên làm việc ở repo này. Hướng dẫn cho người viết web nằm ở `docs/backend.md` bên repo web.

## 3. Stack và cấu trúc backend

- Python 3.13, FastAPI, Pydantic strict (`extra="forbid"`), SQLAlchemy 2.0 async (asyncpg), PostgreSQL 16, Alembic, uv, pytest, ruff.
- File lưu qua S3 API (boto3): local dùng RustFS 1.0.4 trong docker-compose, production dùng AWS S3 với IAM role.

```text
app/core/       config, db (naming convention), types (kiểu chuẩn hóa), schemas (StrictModel),
                errors, merge_patch, revision (ETag/If-Match), lunar, security, deps, storage, revalidate
app/modules/    auth, templates, invitations, events, media, banks   (models/schemas/service/router)
app/scripts/    seed_templates, init_storage
alembic/        một migration 0001 cho toàn bộ schema (chưa có dữ liệu thật nên sửa thẳng)
docker/         nginx-api.conf (Nginx trên EC2), ec2-user-data.sh (chuẩn bị EC2 lần đầu)
docs/spec/      đặc tả 01–07, nguồn chuẩn
docs/modules/   hiện trạng code từng module (Claude tự cập nhật)
docs/progress.md  tiến độ
tests/          pytest với PostgreSQL thật, storage giả (FakeStorage trong conftest.py)
Dockerfile, docker-compose.prod.yml, .env.production.example   production
```

## 4. Cách làm việc đã thống nhất (chi tiết: `CLAUDE.md`)

- `docs/spec/` là nguồn chuẩn. Code cần khác spec thì dừng, nêu chỗ khác và hỏi. Được đồng ý thì sửa spec trước, code sau. Không tự thêm trường, bảng, endpoint ngoài spec.
- Việc lớn: nêu kế hoạch ngắn, chờ duyệt. Làm một bước kế hoạch thì viết test theo tiêu chí nghiệm thu trước.
- Sau mỗi bước: chạy `pytest` và `ruff`, cập nhật `docs/modules/<tên>.md` và `docs/progress.md` (dưới 60 dòng), rồi commit với thông điệp ghi rõ bước và module.
- 14 nguyên tắc dữ liệu (spec 02), tóm tắt:
  - Một trường một nghĩa và một kiểu.
  - Đơn vị nằm ở tên trường (`size_bytes`).
  - Tập giá trị cố định thì không dùng chuỗi tự do.
  - Dữ liệu tính được thì không lưu.
  - Mọi chuỗi trim và chuẩn hóa NFC.
  - API không đoán ý: sai thì từ chối, không tự sửa.
  - Tham chiếu bằng ID.
  - Mã toàn chữ số là chuỗi.
- File `CLAUDE.md`, `docs/modules/*.md`, `docs/progress.md`, `.env.example` dùng CRLF; `README.md` và file này dùng LF. Sửa bằng script thì giữ nguyên kiểu xuống dòng.

## 5. Dữ liệu, nghiệp vụ, API

Chi tiết: spec 03 (dữ liệu), spec 04 (nghiệp vụ), `README.md` (API và các luồng cho FE).

- **7 bảng:** `users`, `refresh_tokens`, `templates`, `invitations`, `events`, `media`, `albums`. Một thiệp dùng chung cho hai bên; mỗi sự kiện có `host_side` (`groom`, `bride`, `both`).
- **`invitations.content`:** JSONB có version (`content_schema_version` = 1), gồm `couple`, `messages`, `love_story`, `gifts`, `appearance`.
  - Ảnh bìa, chân dung, nhạc nền là cột `*_media_id`, khóa ngoại kép tới `media`.
  - Sự kiện là bảng riêng.
- **Sửa thiệp:** JSON Merge Patch, chống ghi đè bằng `revision`. Response có `ETag`, request ghi phải gửi `If-Match`: thiếu → 428, lệch → 409.
- **Publish** cần: tên cô dâu và chú rể, ít nhất một sự kiện có đủ ngày, giờ, địa chỉ, và `sections` có `cover` và `events`.
- **Trang public:** `GET /public/invitations/{slug}?side=groom|bride`. Kết quả có `lunar_date` (âm lịch, thuật toán Hồ Ngọc Đức).
- **Upload 3 bước:**
  1. Xin link presigned.
  2. Trình duyệt PUT thẳng lên S3. Link ký cả `Content-Type` và dung lượng.
  3. Gọi `/complete`.
- **Auth:**
  - Access token JWT sống 15 phút, gửi qua header `Bearer`.
  - Refresh token sống 30 ngày, nằm trong cookie httpOnly có `Path=/auth`, xoay vòng mỗi lần dùng.
  - Mật khẩu băm bằng Argon2id.
- **Giới hạn:** 5 thiệp mỗi tài khoản, 10 sự kiện mỗi thiệp, 200 ảnh (mỗi ảnh tối đa 15 MB) và 1 file nhạc (tối đa 10 MB) mỗi thiệp.
- **Định dạng lỗi:** `{"error": {"code", "message", "details": [{"field", "code", "message"}]}}`.

## 6. Production trên AWS

Region `ap-southeast-2` (Sydney). Tất cả dựng bằng AWS CLI ngày 23/11/2026. Bảng tài nguyên đầy đủ, quy trình phát hành và sao lưu ở `README.md` › Lên production; ghi chú kỹ thuật ở `docs/modules/core.md` › Production trên AWS EC2.

```text
GitHub SuperProject (main) ──push──► Amplify build my-fe-app ──► https://ketduyen.me
Trình duyệt ──► https://api.ketduyen.me ──► Nginx (EC2) ──► container API :8000 ──► RDS PostgreSQL 16
            ├── PUT link presigned ──► S3 thiepcuoi-media-prod (private)
            └── GET ảnh, nhạc ──► CloudFront (OAC) ──► S3
```

| Thành phần | Tên |
| --- | --- |
| EC2 `t4g.small` Ubuntu 24.04 arm64, Elastic IP `54.79.7.46` | tag `Name=thiepcuoi-api` |
| RDS PostgreSQL 16 `db.t4g.micro` | `thiepcuoi-db` |
| S3 file người dùng, sau CloudFront | `thiepcuoi-media-prod` |
| ECR, tag là commit hash | `thiepcuoi-api` |
| IAM role của EC2 (inline policy S3 tên `thiepcuoi-media-s3`) | `thiepcuoi-api-ec2-role` |
| Secret (SecureString) | `/thiepcuoi/prod/DB_PASSWORD`, `/thiepcuoi/prod/JWT_SECRET` |
| Security group | `thiepcuoi-api-sg`, `thiepcuoi-db-sg` |
| Amplify Hosting (web) | `ketduyen-web` (đang dựng, mục 9) |

Repo public nên không ghi account ID, endpoint RDS hay secret vào đây. Cần thì tra bằng CLI:

```bash
aws ec2 describe-instances --filters Name=tag:Name,Values=thiepcuoi-api Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text
aws rds describe-db-instances --db-instance-identifier thiepcuoi-db --query 'DBInstances[0].Endpoint.Address' --output text
aws cloudfront list-distributions --query 'DistributionList.Items[].[Id,DomainName]' --output text
aws amplify list-apps --query 'apps[].[appId,name,defaultDomain]' --output text
```

### Trên EC2

- `/opt/thiepcuoi/` có `docker-compose.prod.yml` và `.env`.
  - `.env` có quyền 600, theo mẫu `.env.production.example`.
  - `DATABASE_URL` và `JWT_SECRET` lấy từ Parameter Store khi dựng.
  - `API_IMAGE` là tag ECR đang chạy.
- Nginx cài trên máy: `/etc/nginx/conf.d/thiepcuoi-api.conf`, theo mẫu `docker/nginx-api.conf`. Chứng chỉ Let's Encrypt do certbot cấp, `certbot.timer` tự gia hạn.
- Sửa `.env` xong thì chạy lại: `docker compose -f docker-compose.prod.yml up -d`.

### Claude điều khiển EC2 bằng SSM, không có SSH

- Gửi lệnh bằng `aws ssm send-command --document-name AWS-RunShellScript`. Document này chạy bằng `sh`, nên `set -o pipefail` báo lỗi.
- Cách đã dùng: script trên máy dev đọc một file lệnh, bọc nó thành `cat > /tmp/ssm-job.sh <<'EOF' ... EOF; bash /tmp/ssm-job.sh`, gửi đi, rồi hỏi `get-command-invocation` tới khi xong và in stdout, stderr.
- Script đặt trong scratchpad của phiên và mất khi scratchpad bị dọn: viết lại theo cách trên.
- Xoá user thử ở production: chạy Python trong container, `docker compose -f docker-compose.prod.yml exec -T api python -`, rồi xoá `users` có email `e2e-%@example.com` (các bảng con xoá theo; file trên S3 thì không, nên xoá file qua API trước).
- **Không bao giờ in secret** (mật khẩu DB, JWT) ra màn hình hay ghi vào git.

## 7. Domain và DNS

- `ketduyen.me` đăng ký ở Namecheap ngày 24/11/2026, hết hạn **24/11/2027**. Gia hạn `.me` mất phí, nhớ gia hạn trước hạn.
- DNS dùng Namecheap BasicDNS (Domain List › Manage › Advanced DNS).
- Lúc nhận domain, gói Student Pack đã tạo sẵn bản ghi cho GitHub Pages: 4 bản ghi A `@` → `185.199.108.153`…`185.199.111.153` và CNAME `www` → `ketduyen.me`. Các bản ghi này được giữ tới khi Amplify đưa bản ghi mới; khi đó xoá chúng, vì ALIAS `@` không đứng chung với A `@`.
- Bản ghi theo kế hoạch:

| Bản ghi | Trỏ tới | Dùng cho |
| --- | --- | --- |
| A `api` | `54.79.7.46` (Elastic IP) | API, chứng chỉ do certbot cấp trên EC2 |
| ALIAS `@` | domain CloudFront do Amplify cấp | web |
| CNAME `www` | domain CloudFront do Amplify cấp (Amplify chuyển `www` về domain gốc) | web |
| CNAME `_…` | `_….acm-validations.aws.` | Amplify xác minh chứng chỉ |

- Web và API cùng domain gốc, nên cookie `refresh_token` dùng `COOKIE_SAMESITE=lax` và Safari vẫn giữ được.
  - `CORS_ORIGINS=https://ketduyen.me`.
  - CORS của bucket cho `https://ketduyen.me` và `http://localhost:5173`, vì trình duyệt upload thẳng lên S3.
- Tên cũ `thiepcuoi-api.duckdns.org` (DuckDNS miễn phí, dùng trước khi có domain) vẫn trỏ về EC2 và có chứng chỉ riêng. Bỏ khỏi Nginx khi web đã chuyển hẳn sang `api.ketduyen.me`.
- Chưa làm `media.ketduyen.me` cho CloudFront: chứng chỉ phải tạo ở us-east-1, mà gói Free không cho dùng tính năng nhiều region. URL ảnh được tính lúc trả về (`MEDIA_PUBLIC_BASE_URL`), nên đổi sau này không phải sửa dữ liệu.

## 8. Web (repo SuperProject) so với spec

- **Spec ghi web là Next.js, nhưng web thật là Vite SPA:**
  - Webhook revalidate (`FRONTEND_REVALIDATE_URL`) không dùng, đang để trống. `app/core/revalidate.py` bỏ qua khi biến trống.
  - Link thiệp chia sẻ lên Zalo hay Facebook chỉ hiện ảnh và tiêu đề chung của site, không có thẻ meta riêng từng thiệp.
  - Chưa quyết có chuyển sang Next.js hay không. Muốn đổi thì hỏi người dùng và sửa spec trước.
- **Key mẫu thiệp lệch giữa hai bên:**
  - Web có 4 mẫu, slug `royal-blue`, `dragon-phoenix-red`, `cherry-blossom-pink`, `minimalism-dark-red` (`my-fe-app/src/templates/registry.ts`).
  - Backend seed `classic_01`, `minimal_01`, `floral_01`, `vintage_01` (`app/scripts/seed_templates.py`). Key phải là snake_case (spec 03).
  - Cần chốt lại danh sách mẫu, rồi sửa seed và `manifest` (section, bảng màu, font, nền) cho khớp component web. Hỏi người dùng trước.
- **Web chưa có route trang thiệp public.** README ghi 3 đường dẫn: `/{slug}`, `/{slug}/nha-trai`, `/{slug}/nha-gai`.
- **Web chạy local** gọi API qua proxy của Vite (`/api` → `https://api.ketduyen.me`). Cách làm ở `docs/backend.md` bên repo web.

## 9. Diễn biến và việc đang làm

1. **05–06/11:** tách spec, làm Bước 0–11. Mọi bước được người dùng duyệt. Quyết định phụ của từng bước ghi trong `docs/progress.md` và `docs/modules/`.
2. **09/11 → 23/11:** hướng hạ tầng đổi nhiều lần.
   - AWS (ECS, chưa dựng).
   - VPS (Caddy, PostgreSQL và RustFS trong compose; đã bỏ).
   - Chốt **AWS EC2** ngày 23/11: một máy, Nginx trên host, không dùng ECS hay Load Balancer để tiết kiệm.
   - Trước khi sửa lớn tài liệu deploy, xác nhận lại hướng với người dùng.
3. **16/11:** link upload ký thêm `Content-Length`, băm mật khẩu chạy ở threadpool.
4. **23/11:** máy dev chuyển từ Windows sang Mac. Dựng toàn bộ production bằng AWS CLI, chạy thử luồng thật qua Internet: đúng.
5. **24/11:**
   - Chưa có domain: API dùng HTTPS qua DuckDNS, `COOKIE_SAMESITE=none` (Safari chặn cookie bên thứ ba).
   - Cùng ngày người dùng có domain `ketduyen.me` và chọn: web lên **Amplify** (không chung server với API), API ở `api.ketduyen.me`, cookie về `lax`.
6. **Đang làm (kế hoạch đã duyệt 24/11), theo thứ tự:**
   1. Người dùng thêm bản ghi A `api` ở Namecheap.
   2. Người dùng tạo app Amplify nối GitHub. Phải bấm trên trình duyệt: monorepo, thư mục gốc `my-fe-app`, nhánh `main`, tên `ketduyen-web`.
   3. Claude đặt cấu hình Amplify bằng CLI:
      - Biến `VITE_API_URL=https://api.ketduyen.me` và `AMPLIFY_MONOREPO_APP_ROOT=my-fe-app`.
      - Rule chuyển `www` về domain gốc, và rule SPA trả `/index.html`.
      - Build nhánh `main`.
      - Gắn domain `ketduyen.me` và `www`.
   4. Người dùng thêm các bản ghi Amplify đưa: ALIAS `@`, CNAME `www`, CNAME xác minh chứng chỉ.
   5. Claude làm trên EC2 và S3:
      - Thêm `api.ketduyen.me` vào Nginx và chạy certbot.
      - Trong `.env` đặt `CORS_ORIGINS=https://ketduyen.me`, `COOKIE_SAMESITE=lax`, rồi `compose up -d`.
      - Sửa CORS của bucket.
   6. Chạy thử luồng thật qua `https://api.ketduyen.me` với `Origin: https://ketduyen.me`, rồi xoá dữ liệu thử.
   7. Cập nhật README › Lên production, `core.md`, `progress.md`, file này, và `docs/backend.md` bên web. Commit, không push.

## 10. Tài khoản AWS

- Tài khoản theo giao diện AWS mới: mỗi project là một tài khoản. Project tên "Lift Off Soon", quản lý ở `settings.aws.com`.
- Dùng **gói Free**: có credit, không bị trừ tiền tới khi bấm Upgrade. Chi phí ước tính khoảng $40/tháng, trừ vào credit.
- Gói Free có giới hạn:
  - Backup RDS chỉ giữ 1 ngày.
  - Không dùng được tính năng nhiều region.
  - Lambda@Edge không dùng được.
  - Amplify, CloudFront, ACM, EC2, RDS, S3, ECR, SSM đều có trong danh sách được hỗ trợ.
- **Không bật "Activate advanced features"**: bật rồi không đảo ngược được, và hạn mức chi tiêu bị gỡ.
- CLI đăng nhập bằng `aws login` (profile `default`, region `ap-southeast-2`). **Phiên hết hạn sau vài giờ.** Gặp "Your session has expired" thì nhờ người dùng chạy lại `aws login --region ap-southeast-2` trong terminal của họ. Claude không tự đăng nhập được.

## 11. Việc còn mở

| Việc | Ghi chú |
| --- | --- |
| Gắn domain `ketduyen.me` | Đang làm, mục 9 |
| Key mẫu thiệp FE/BE lệch | Mục 8; cần người dùng chốt |
| Next.js hay SPA cho trang thiệp public | Mục 8 |
| Giới hạn tần suất đăng nhập, đăng ký | Spec 07 xếp ngoài v1; nên làm trước khi mở công khai, cần duyệt sửa spec |
| Xác minh email, quên mật khẩu, đăng nhập Google/Zalo | Ngoài v1 (spec 07) |
| Job dọn file `pending`, file mồ côi, refresh token hết hạn | Ngoài v1 (spec 07) |
| Link upload còn hạn 10 phút sau `/complete` vẫn ghi đè được bằng file cùng dung lượng, cùng loại | Muốn bịt thì phải đổi luồng upload trong spec |
| File đã xoá còn trong cache CloudFront tới 24 giờ | Code chưa tạo invalidation |
| `media.ketduyen.me` | Mục 7 |
| README › Chạy lần đầu còn ghi chú Windows/WSL | Máy dev giờ là Mac; sửa khi đụng tới README |
| Gia hạn domain | Trước 24/11/2027 |

**Lộ trình nâng cấp khi có người dùng thật.** Hiện tại: 1 EC2, deploy API bằng tay, chỉ có production, hạ tầng dựng bằng CLI. Thứ tự nâng cấp:

1. CI/CD cho API: GitHub Actions chạy test, build image arm64, đẩy ECR, deploy qua SSM.
2. Theo dõi lỗi và cảnh báo: CloudWatch, báo khi `/health` lỗi.
3. Môi trường staging.
4. Nhiều máy sau Load Balancer (ECS), RDS Multi-AZ, backup giữ lâu hơn (cần nâng gói).
5. Hạ tầng viết thành code (CDK hoặc Terraform).

## 12. Môi trường dev

- MacBook Air M5 (arm64, cùng kiến trúc với EC2 nên build image không cần `buildx`), VS Code, Claude Code.
- Docker CLI và Colima cài qua Homebrew (không có Docker Desktop). Plugin compose khai báo trong `cliPluginsExtraDirs` của `~/.docker/config.json`.
- **Chạy `colima start` trước** `docker compose up -d` và `uv run pytest`. Colima tắt thì pytest treo, hoặc `docker` báo không kết nối được.
- Lệnh `aws`, `docker` không tìm thấy: `eval "$(/opt/homebrew/bin/brew shellenv)"`.

## 13. Cách trao đổi với người dùng

- **Luôn trả lời bằng tiếng Việt, câu đơn giản**, kể cả khi người dùng viết tiếng Anh.
- Việc người dùng phải tự làm (console AWS, Namecheap, GitHub): viết từng bước đánh số, mỗi lần một việc, chờ người dùng báo lại (thường kèm ảnh chụp màn hình). Nói rõ khi màn hình có thể khác hướng dẫn.
- Người dùng thích Claude làm hộ phần CLI ("làm luôn hết đi"). Những việc cần trình duyệt thì vẫn phải nhờ người dùng: `aws login`, OAuth GitHub, Namecheap.
- Chỉ push lên GitHub khi người dùng đồng ý.
- Không gửi email hay thông tin cá nhân của người dùng cho dịch vụ ngoài. Let's Encrypt đăng ký không dùng email.
- Người dùng chưa có ngân sách: ưu tiên cách miễn phí hoặc nằm trong credit, nói rõ chi phí trước khi tạo tài nguyên tốn tiền.

## 14. Lệnh thường dùng

```sh
colima start                                  # máy dev Mac
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

Sửa migration 0001 thì dựng lại DB dev: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` rồi upgrade và seed. Phát hành API lên production: README › Lên production › Phát hành phiên bản mới.
