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

## Danh sách module (chốt ở Bước 0 theo cấu trúc `app/` của khung)

Code khung chạy được (Bước 0) nhưng chưa có file module: mỗi module có file khi bước đầu tiên làm tới nó. Module nằm trong `app/modules/<tên>/` gồm `models.py`, `schemas.py`, `service.py`, `router.py`.

| Module | Code | Phạm vi | Bước | File module |
| --- | --- | --- | --- | --- |
| core | `app/core/` (config, db, security, deps, errors, schemas, types, storage, revalidate, merge_patch, revision) | Kiểu chuẩn hóa `types.py`, `StrictModel`, định dạng lỗi chung (Bước 1); naming convention trong `db.py`; Merge Patch, ETag/If-Match (Bước 4) | 1, 2, 4 | [core.md](core.md) |
| auth | `app/modules/auth/` | users, refresh_tokens, register/login/refresh/logout, `GET /me` (giữ từ khung) | 2 (model giữ nguyên, không sửa code) | chưa có |
| templates | `app/modules/templates/`, `app/scripts/seed_templates.py` | Bảng templates, `TemplateManifest`, seed 4 mẫu, `GET /templates` | 2, 3 | [templates.md](templates.md) |
| invitations | `app/modules/invitations/` (có `public_router`, `slugs.py`) | Bảng invitations, schema content v1, tạo/sửa thiệp (Merge Patch, revision, ETag, If-Match), đổi template, publish; trang public `GET /public/invitations/{slug}` (lọc side, display_name, lunar_date, media_by_id) | 2, 4, 6, 10 | [invitations.md](invitations.md) |
| events | `app/modules/events/` | Bảng events, CRUD (`/invitations/{id}/events`), tên mặc định, thứ tự, giới hạn 10, If-Match; giữ điều kiện publish khi ghi | 2, 5, 6 | [events.md](events.md) |
| media | `app/modules/media/`, `app/scripts/init_storage.py` | Bảng media và albums, upload-url (`kind` image/audio suy ra từ `content_type`), giới hạn theo loại, endpoint album; xoá file thì dọn tham chiếu của thiệp (gọi `invitations.service.release_media`) | 2, 7 | [media.md](media.md) |
| banks | chưa có (vị trí chốt ở Bước 8) | File tĩnh danh sách ngân hàng, `GET /banks`, kiểm tra gifts | 8 | chưa có |
| lunar | chưa có (`app/core/lunar.py`) | Âm lịch Việt Nam UTC+7 | 9 | chưa có |

Bước 11 (README, xoá code cũ) chạm tới mọi module: cập nhật các file module bị ảnh hưởng.
