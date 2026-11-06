# templates

## Mục đích
Danh mục mẫu thiệp (bảng `templates`), schema `TemplateManifest`, API đọc danh sách mẫu, script seed. Phần giao diện của mẫu nằm ở Next.js, tra theo `key`.

## File code chính
- `app/modules/templates/models.py`: `Template`, `TemplateCategory` (Bước 2)
- `app/modules/templates/schemas.py`: `SectionKey`, kiểu `Key`, `HexColor`, `TemplateManifest` (`Palette`, `ManifestOption`, `ManifestDefaults`), `TemplateCreate`, `TemplateResponse` (Bước 3)
- `app/modules/templates/service.py`, `router.py`: từ khung; router đổi sang `TemplateResponse` ở Bước 3
- `app/scripts/seed_templates.py`: `TEMPLATES` (4 mẫu), `validate_templates`, `seed`, `SeedError` (Bước 3)

## API công khai
- `SectionKey`: 9 key section của v1, theo thứ tự trong spec 03. Bước 4 dùng cho `appearance.sections`
- `TemplateManifest`: kiểm tra manifest; cũng là kiểu của `TemplateResponse.manifest`, nên OpenAPI có schema đầy đủ
- `TemplateCreate`: một dòng seed (key, name, description, category, is_premium, position, manifest). Không có endpoint tạo mẫu
- `list_active(db, category=None)`: mẫu đang bật, sắp theo `position`, `name`
- `get_by_key(db, key)`: 404 `template_not_found` nếu không có hoặc đã tắt
- `get_usable_by_key(db, key)`: như trên, thêm 400 `template_premium` (chưa có thanh toán)
- `GET /templates?category=`, `GET /templates/{key}`: trả `TemplateResponse` (id, key, name, description, thumbnail_url, category, is_premium, manifest)
- `validate_templates(rows)`: kiểm tra cả danh sách, sai thì raise `SeedError` (`errors`: `[{index, key, field, code, message}]`)
- `seed(db, rows=TEMPLATES)`: kiểm tra trước, rồi upsert theo `key` trong một transaction; trả số mẫu. CLI: `main()`, sai thì in lỗi ra stderr và thoát mã 1

## Phụ thuộc
- Dùng: core (`Base`, `enum_check`, `StrictModel`, `Choice`, `RequiredSingleLine`, `MultiLine`, `error_details`)
- Được dùng bởi: invitations (`Invitation.template`, chọn mẫu khi tạo/sửa thiệp; Bước 4 dùng `manifest.default_sections`, `SectionKey`)

## Quy tắc spec đang áp dụng
- Cột, kiểu, NULL, DEFAULT, cấu trúc manifest → `docs/spec/03-mo-hinh-du-lieu.md` › templates
- Key snake_case (`classic_01`, `ivory_gold`) → `docs/spec/02-nguyen-tac-va-quy-chuan.md` › Quy ước đặt tên
- `position` 0–3 liên tục → 02 › Quy chuẩn dữ liệu (Thứ tự hiển thị)

## Quy tắc phụ chốt ở Bước 3 (người dùng duyệt theo đề xuất)
- `sections`, `default_sections`, `palettes`, `fonts`, `backgrounds` có ít nhất 1 phần tử (rỗng → `out_of_range`)
- `sections`, `default_sections` không trùng; key trong mỗi danh sách palette/font/nền không trùng. Phần tử trùng (từ lần thứ hai) → `invalid_format` tại `sections[i]` / `palettes[i].key`
- `default_sections[i]` ngoài `sections`, `defaults.*_key` ngoài danh sách → `invalid_choice`
- Key: `^[a-z][a-z0-9]*(_[a-z0-9]+)*$`, tối đa 64, không trim, không đổi hoa thường; rỗng → `required`. `name` của palette/font/nền: một dòng bắt buộc, tối đa 120
- Màu `^#[0-9A-F]{6}$`, không trim, chữ thường bị từ chối. `max_gallery_images`: số nguyên strict ≥ 0, không có giới hạn trên
- Dòng seed: `name` một dòng tối đa 120, `description` nhiều dòng tối đa 500, `position` ≥ 0; key trùng trong danh sách → `invalid_format` tại `key`
- Seed không ghi `thumbnail_url`, `is_active`. Mọi cột còn lại luôn được ghi đè, nên bỏ một trường khỏi seed thì cột về mặc định

## Dữ liệu seed
- 4 mẫu `classic_01`, `minimal_01`, `floral_01`, `vintage_01` (premium). `minimal_01` không có `love_story`; ba mẫu kia có đủ 9 section
- `default_sections` = mọi section của mẫu; `defaults` = phần tử đầu của mỗi danh sách (helper `_manifest`)
- Key palette/font/nền là bản nháp do Claude đề xuất, chưa đối chiếu với component Next.js. Đổi key thì sửa seed và component cùng lúc

## Lưu ý
- Lỗi tham chiếu chéo nằm trong `model_validator(mode="after")`, chỉ chạy khi mọi trường đã hợp lệ: lỗi cấu trúc hiện trước, sửa xong mới thấy lỗi tham chiếu
- `TemplateResponse` validate manifest khi đọc: dòng có manifest sai trong DB làm `GET /templates` lỗi 500. Chỉ ghi manifest qua seed
- `_manifest` chép list `sections`: các mẫu dùng chung một list thì sửa một mẫu sẽ kéo theo mẫu khác (test đã bắt lỗi này)
- Query `category` vẫn là chuỗi tự do (giá trị lạ trả `[]`), chưa dùng `TemplateCategory`: ngoài phạm vi Bước 3
- Không có CHECK snake_case cho `key` ở database (đã chốt Bước 2); `TemplateCreate` kiểm tra khi seed
- Giữ index `ix_templates_category` của khung (spec không nhắc tới, đã chốt giữ)
- Fixture `templates` trong `tests/conftest.py` dùng `make_manifest()` (manifest hợp lệ, nhỏ); key `classic_01`, `minimal_01`, `vintage_01` (premium), `old_01` (tắt)
