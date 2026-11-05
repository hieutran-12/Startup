# Tài liệu module

Mỗi file `docs/modules/<tên>.md` mô tả code **đã viết** của một module, dài khoảng 30–60 dòng. Chỉ tạo file khi module đã có code; cập nhật ngay sau mỗi lần làm hoặc sửa module đó.

`docs/spec/` là ý định (không tự sửa); file module là hiện trạng của code. Không chép lại nội dung spec vào đây, chỉ trỏ tới mục trong spec.

## Khung một file module

```markdown
# <tên module>

## Mục đích
<1–3 dòng: module làm gì>

## File code chính
- `app/...`: <vai trò>

## API công khai
- Hàm/class: `<tên>(...)`: <làm gì>
- Endpoint: `<METHOD> <đường dẫn>`: <làm gì>

## Phụ thuộc
- Dùng: <module khác>
- Được dùng bởi: <module khác>

## Quy tắc spec đang áp dụng
- <quy tắc ngắn> → `docs/spec/<file>` › <mục>

## Lưu ý
- <điểm dễ sai, giới hạn hiện tại, việc còn dở>
```

## Module dự kiến (theo `docs/spec/06-ke-hoach.md`)

Chưa có code. Tên module chốt lại khi đã thấy cấu trúc `app/` của khung ở Bước 0.

| Module | Phạm vi dự kiến | Bước | File module |
| --- | --- | --- | --- |
| core | `app/core/types.py` (một dòng, nhiều dòng, chuỗi chữ số, giờ HH:MM, múi giờ), base model strict, handler lỗi chung, naming convention trong `app/core/db.py` | 1, 2 | chưa có |
| auth | users, refresh_tokens, endpoint auth (giữ từ khung) | 0, 2 | chưa có |
| templates | Bảng templates, `TemplateManifest`, seed 4 mẫu, `GET /templates` | 2, 3 | chưa có |
| invitations | Bảng invitations, schema content v1, tạo/sửa thiệp (Merge Patch, revision, ETag, If-Match), đổi template, publish | 2, 4, 6 | chưa có |
| events | Bảng events, CRUD, tên mặc định, thứ tự, giới hạn 10 | 2, 5 | chưa có |
| media | Bảng media, `kind` image/audio, upload-url, giới hạn theo loại, xoá file thì dọn tham chiếu | 2, 7 | chưa có |
| albums | Bảng albums, endpoint album (giữ từ khung) | 0, 2 | chưa có |
| banks | File tĩnh danh sách ngân hàng, `GET /banks`, kiểm tra gifts | 8 | chưa có |
| lunar | `app/core/lunar.py`, lịch Việt Nam UTC+7 | 9 | chưa có |
| public | `GET /public/invitations/{slug}`, lọc theo side, display_name, lunar_date, media_by_id | 10 | chưa có |

Bước 11 (README, xoá code cũ) chạm tới mọi module: cập nhật các file module bị ảnh hưởng.
