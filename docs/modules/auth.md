# auth

## Mục đích
Tài khoản (bảng `users`), phiên đăng nhập (bảng `refresh_tokens`), đăng ký, đăng nhập, xoay vòng refresh token, đăng xuất, `GET /me`. Cơ chế token giữ nguyên từ khung; ngày 2026-11-06 (cùng đợt Bước 11) schema request chuyển sang `StrictModel`.

## File code chính
- `models.py`: `User` (`email` VARCHAR(320) UNIQUE, `password_hash` cho phép null, `full_name` VARCHAR(120), `is_active`), `RefreshToken` (`token_hash` SHA-256, `expires_at`, `revoked_at`, `user_agent`): từ khung
- `schemas.py`: `RegisterRequest`, `LoginRequest` (`StrictModel`), `UserResponse` (đổi tên từ `UserOut`), `TokenResponse`
- `service.py`: `register`, `login`, `rotate_refresh_token`, `logout`; `router.py`: endpoint, cookie
- `app/core/security.py` (Argon2id, JWT access token, refresh token ngẫu nhiên), `app/core/deps.py` (`CurrentUser`): từ khung

## API công khai
- `POST /auth/register` → 201 `TokenResponse`, đặt cookie `refresh_token` (httpOnly, `path=/auth`); email trùng → 409 `email_taken`
- `POST /auth/login` → `TokenResponse`; sai email hoặc mật khẩu → 401 `invalid_credentials`; tài khoản bị khoá → 401 `account_disabled`
- `POST /auth/refresh` (cookie) → `TokenResponse`, xoay vòng token; mã 401: `missing_refresh_token`, `invalid_refresh_token`, `refresh_token_rotated` (dùng lại trong 20 giây), `refresh_token_reused` (quá 20 giây: thu hồi mọi phiên), `refresh_token_expired`, `account_disabled`
- `POST /auth/logout` → 204, thu hồi token trong cookie; `GET /me` → `UserResponse` (`id, email, full_name, created_at`)
- `CurrentUser`: header `Authorization: Bearer <access_token>`; thiếu → 401 `unauthorized`, sai/hết hạn → 401 `invalid_token`

## Phụ thuộc
- Dùng: core (`StrictModel`, `Email`, `Password`, `RequiredSingleLine`, `security`, `errors`)
- Được dùng bởi: mọi module cần đăng nhập (`CurrentUser`); invitations (`User`, khóa dòng `users` khi tạo thiệp)

## Quy tắc spec đang áp dụng
- `users`, `refresh_tokens` giữ như khung; `full_name` là văn bản một dòng → `docs/spec/03-mo-hinh-du-lieu.md` › Bảng giữ nguyên
- Email: VARCHAR(320), trim, chữ thường, kiểm tra định dạng → 02 › Kiểu dữ liệu; nguyên tắc 12; 02 › Quy tắc trên API (chỉ email, slug, enum hạ chữ thường)
- Strict, `extra="forbid"`, định dạng lỗi 422 → 02 › Quy tắc trên API; 05 › Định dạng lỗi
- Ngoài phạm vi: giới hạn tần suất, quên mật khẩu, xác minh email, Google/Zalo → 07

## Quy tắc phụ chốt ngày 2026-11-06 (người dùng duyệt)
1. `full_name`: `RequiredSingleLine(120)` (NFC, trim, gộp khoảng trắng; xuống dòng → `invalid_characters`; rỗng → `required`; quá 120 → `too_long`).
2. `email`: kiểu `Email` của core: NFC → trim → chữ thường → rỗng `required` → quá 320 `too_long` → cú pháp sai `invalid_format` "Email không hợp lệ" (`email-validator`, không tra DNS). Lưu đúng chuỗi đã trim và hạ chữ thường, không lấy bản `normalized` của thư viện. Đăng nhập dùng cùng kiểu.
3. `password`: kiểu `Password(min, max)` của core: chỉ NFC, không trim (dấu cách là một phần của mật khẩu, kể cả mật khẩu toàn dấu cách); độ dài đếm sau NFC. Đăng ký 8–128, đăng nhập 1–128 (mật khẩu sai là 401, không phải 422). Ngắn → `out_of_range`, dài → `too_long`, rỗng/null/thiếu → `required`, không phải chuỗi → `invalid_format`.
4. `UserOut` → `UserResponse`; JSON không đổi.

## Lưu ý
- NFC cho mật khẩu: bàn phím macOS/iOS có thể gõ tiếng Việt ra NFD, Windows ra NFC. Tài khoản tạo trước ngày 2026-11-06 với mật khẩu dạng NFD (chỉ có trên DB dev) không đăng nhập được nữa.
- `login` gọi `verify_password` với hash giả khi email không tồn tại, để thời gian phản hồi không lộ email nào đã đăng ký.
- Refresh token không phải JWT; DB chỉ lưu hash. Hai request refresh trong 20 giây (`REUSE_GRACE_PERIOD`) chỉ bị từ chối, không thu hồi phiên.
- Refresh token hết hạn không bị xoá (job dọn ngoài phạm vi v1, spec 07).
- Test: `tests/test_auth.py` (luồng token, validation qua API), `tests/test_core_types.py` (`Email`, `Password`).
