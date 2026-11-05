# Tiến độ

Cập nhật sau mỗi bước. Giữ dưới 60 dòng; khi dài thì gộp các mục cũ.

## Kế hoạch (`docs/spec/06-ke-hoach.md`)

| Bước | Việc | Trạng thái |
| --- | --- | --- |
| 0 | Chạy khung hiện tại | Chưa bắt đầu (thiếu khung code) |
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

## Quyết định mới

- (chưa có)

## Việc còn treo

- Khung code `thiepcuoi-backend.zip` chưa có trong repo; cần có trước Bước 0.
- Thư mục chưa phải git repo; cần `git init` trước lần commit đầu.
- Lệnh chạy app chưa biết; điền vào `CLAUDE.md` ở Bước 0.
- Spec còn trỏ tới `docs/spec-v1.md` (01 › Mục đích và cách dùng; 06 › Mẫu câu giao việc). Chờ quyết định có sửa spec không.
- Bản xuất spec mất định dạng: bảng bị trải mỗi ô một dòng; mất sơ đồ quan hệ bảng (03 › "Mũi tên đi từ…") và link "(nguồn)" ở 04 › Ngày âm lịch.
