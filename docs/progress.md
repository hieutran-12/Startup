# Tiến độ

Cập nhật sau mỗi bước. Giữ dưới 60 dòng; khi dài thì gộp các mục cũ.

## Kế hoạch (`docs/spec/06-ke-hoach.md`)

| Bước | Việc | Trạng thái |
| --- | --- | --- |
| 0 | Chạy khung hiện tại | Xong 2026-11-05: 28/28 test qua, ruff sạch, `/docs` mở được; chỉ sửa `alembic.ini` |
| 1 | Tầng chuẩn hóa, base model, lỗi 422 | Chưa bắt đầu |
| 2 | Model và migration 0001 | Chưa bắt đầu |
| 3 | Manifest template, seed | Chưa bắt đầu |
| 4 | Content v1, tạo/sửa thiệp, revision | Chưa bắt đầu |
| 5 | Module events | Chưa bắt đầu |
| 6 | Publish, breaks_published_invitation | Chưa bắt đầu |
| 7 | Media: kind, âm thanh, dọn tham chiếu | Chưa bắt đầu |
| 8 | Danh sách ngân hàng, GET /banks | Chưa bắt đầu |
| 9 | Âm lịch | Chưa bắt đầu |
| 10 | Response public mới | Chưa bắt đầu |
| 11 | README, xoá code cũ | Chưa bắt đầu |

## Đã xong ngoài kế hoạch

- 2026-11-05: Tách `docs/spec-v1.md` thành `docs/spec/01`–`07` (giữ nguyên chữ, đổi CRLF sang LF); tạo `CLAUDE.md`, `docs/modules/`, `docs/progress.md`.
- 2026-11-05: Giải nén khung vào thư mục gốc, `git init`; commit đầu `83b3822` là khung nguyên trạng. `thiepcuoi-backend.zip` để ngoài git (`.git/info/exclude`).

## Ghi chú Bước 0

- Lỗi duy nhất: Alembic đọc `alembic.ini` bằng cp1252 trên Windows, hỏng ở chú thích tiếng Việt. Sửa: viết chú thích không dấu.
- Script `seed_templates`, `init_storage` in tiếng Việt: hỏng khi chạy qua pipe (cp1252), chạy trong terminal thì bình thường. Không sửa code.
- Khung dùng tên module: core, auth, templates, invitations (gồm trang public), media (gồm album). Danh sách module đã chốt lại trong `docs/modules/README.md`.

## Quyết định mới

- (chưa có)

## Việc còn treo

- Spec còn trỏ tới `docs/spec-v1.md` (01 › Mục đích và cách dùng; 06 › Mẫu câu giao việc). Chờ quyết định có sửa spec không.
- Bản xuất spec mất định dạng: bảng bị trải mỗi ô một dòng; mất sơ đồ quan hệ bảng (03 › "Mũi tên đi từ…") và link "(nguồn)" ở 04 › Ngày âm lịch.
