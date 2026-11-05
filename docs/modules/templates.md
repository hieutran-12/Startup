# templates

## Mục đích
Danh mục mẫu thiệp (bảng `templates`), API đọc danh sách mẫu, script seed. Phần giao diện của mẫu nằm ở Next.js, tra theo `key`.

## File code chính
- `app/modules/templates/models.py`: `Template`, `TemplateCategory` (Bước 2)
- `app/modules/templates/schemas.py`: `TemplateOut` (từ khung, đổi `field_schema` thành `manifest` ở Bước 2)
- `app/modules/templates/service.py`, `router.py`: từ khung
- `app/scripts/seed_templates.py`: upsert 4 mẫu theo `key`

## API công khai
- `list_active(db, category=None)`: mẫu đang bật, sắp theo `position`, `name`
- `get_by_key(db, key)`: 404 `template_not_found` nếu không có hoặc đã tắt
- `get_usable_by_key(db, key)`: như trên, thêm 400 `template_premium` (chưa có thanh toán)
- `GET /templates?category=`, `GET /templates/{key}`

## Phụ thuộc
- Dùng: core (`Base`, `enum_check`)
- Được dùng bởi: invitations (`Invitation.template`, chọn mẫu khi tạo/sửa thiệp)

## Quy tắc spec đang áp dụng
- Cột, kiểu, NULL, DEFAULT → `docs/spec/03-mo-hinh-du-lieu.md` › templates
- `category` VARCHAR(32) + `ck_templates_category_valid` (classic, minimal, floral, vintage, modern)
- `position` thay `sort_order`; `manifest` JSONB NOT NULL, không có DEFAULT, thay `field_schema`

## Lưu ý
- Bước 2 chưa có schema `TemplateManifest`: `manifest` đang là `dict` tự do, `TemplateOut.manifest` trả nguyên. Seed vẫn ghi cấu trúc cũ (`sections` gồm key cũ, `max_gallery_images`, `theme`) và key kebab-case (`classic-01`). Cả hai làm ở Bước 3.
- Không có CHECK snake_case cho `key` ở database (đã chốt Bước 2): seed kiểm tra ở Bước 3.
- Giữ index `ix_templates_category` của khung (spec không nhắc tới, đã chốt giữ).
- `TemplateOut` còn hậu tố `Out` và chưa dùng `StrictModel`; query `category` là chuỗi tự do.
- Fixture `templates` trong `tests/conftest.py` tạo mẫu với `manifest={}`.
