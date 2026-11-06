# invitations

## Mục đích
Bảng `invitations`, schema content v1, tạo/sửa/publish/xoá thiệp (Merge Patch, revision, ETag/If-Match, đổi template, tham chiếu media), kiểm tra slug, trang public theo slug.

## File code chính
- `models.py`: `Invitation`, `InvitationStatus`, `MEDIA_REFERENCE_COLUMNS`, khóa ngoại kép tới media (Bước 2)
- `schemas.py`: content v1 (`InvitationContent`, `Couple`, `Person`, `Parent`, `Messages`, `LoveStoryItem`, `Gift`, `Appearance`, `BirthOrder`, `RecipientSide`), `Slug`/`OptionalSlug`, `InvitationCreate`, `InvitationUpdate`, `InvitationResponse` (Bước 4). `SlugAvailability`, `Public*` từ khung
- `service.py`, `router.py`: viết lại ở Bước 4. `slugs.py`, `deps.py` (`OwnedInvitation`): từ khung

## API công khai
- `GET/POST /invitations`, `GET/PATCH/DELETE /invitations/{id}`, `GET /invitations/slug-availability`, `POST /invitations/{id}/publish|unpublish`, `GET /public/invitations/{slug}`
- Response một thiệp (tạo, xem, sửa, publish, unpublish) có header `ETag: "<revision>"`; danh sách thì không. PATCH bắt buộc `If-Match` (dependency `IfMatch` của core)
- Service: `create`, `update(db, owner, id, data, if_match)` → (thiệp, slug cần revalidate), `to_response`, `list_for_owner` (trả `InvitationResponse`), `get_owned(for_update=)`, `default_content(manifest)`, `adjust_appearance(appearance, manifest)`, `publish`, `unpublish`, `delete`, `get_public`, `check_slug`
- `InvitationContent.model_validate(data, context={"manifest": TemplateManifest})` kiểm tra cả appearance theo manifest; không có context thì chỉ kiểm tra cấu trúc (dùng khi trả response)

## Phụ thuộc
- Dùng: core (`merge_patch`, `revision`, `validation_error`, `field_error`), auth (`User`), templates (`TemplateManifest`, `Key`, `SectionKey`), media (`Media`, `MediaKind`, `MediaStatus`, `Album`), events (`Event`, tính `primary_event_date`)
- Được dùng bởi: media (`OwnedInvitation`), events (`get_owned(for_update=True)`, tăng `revision` của thiệp khi ghi sự kiện)

## Quy tắc spec đang áp dụng
- Cột, CHECK, khóa ngoại kép → 03 › invitations. Content v1 → 03 › Nội dung thiệp. NULL/rỗng → 02
- Tạo thiệp (khóa dòng users `FOR UPDATE` rồi đếm, content mặc định, `revision = 1`), Sửa thiệp, Đổi template, Tham chiếu media → 04
- Mã lỗi, mã HTTP, trường response → 05

## Quy tắc phụ chốt ở Bước 4 (người dùng duyệt 9 đề xuất, 2026-11-06)
1. POST nhận `content` tùy chọn, cùng dạng Merge Patch với PATCH, gộp lên content mặc định (`sections` = `default_sections` nếu không gửi).
2. `null` cho nhóm object (`couple`, `groom`, `father`, `messages`, `appearance`) → 422 `required`.
3. Phần tử `love_story`/`gifts` thiếu trường được phép null thì là null; thiếu trường bắt buộc → `required`.
4. Lỗi theo manifest, tham chiếu media → 422 `validation_error` (`invalid_choice`/`invalid_reference`, đường dẫn đúng trường). 400 chỉ cho lỗi nghiệp vụ không gắn trường.
5. 409 trả revision mới nhất trong header `ETag`. If-Match chỉ khớp đúng `"<revision>"`; `5`, `W/"5"`, `*`, danh sách → 409.
6. revision chỉ tăng khi có giá trị thực sự đổi; PATCH không đổi gì → 200, không ghi (`updated_at` giữ nguyên).
7. Đổi template cùng lúc gửi appearance: chỉnh appearance cũ theo manifest mới → gộp patch → kiểm tra chặt (giá trị gửi tường minh mà sai thì 422).
8. Có `month` mà `year` null → `content.love_story[i].year`, `required`, "Cần nhập năm khi có tháng".
9. `primary_event_date` = `MIN(events.event_date)`, tính khi trả về.
- Suy ra từ spec 02 (không hỏi lại): slug lúc tạo rỗng/null thì tự sinh; PATCH `slug`/`title`/`template_key`/`content` null hoặc rỗng → `required`. Key appearance so khớp nguyên văn (`""` → `invalid_choice`); section trùng → `invalid_format` (như manifest). Publish không cần If-Match, không tăng revision (spec không liệt kê `status`).

## Thứ tự kiểm tra PATCH
401 → 428 thiếu If-Match → 422 body → 404 → 409 revision (sau `SELECT … FOR UPDATE`) → 404/400 template → 422 content và tham chiếu media (gộp chung một lần) → 409 slug → ghi, tăng revision nếu có thay đổi.

## Lưu ý
- Tham chiếu media chỉ kiểm tra khi có trong request (cột gửi khác null; `love_story` có trong patch thì kiểm tra cả danh sách). Gửi lại đúng id cũ mà file đã hỏng vẫn bị 422.
- Seed đổi manifest của template đang dùng mà appearance đã lưu không còn hợp lệ: mọi PATCH có content sẽ 422 tới khi sửa appearance (chỉ đổi template mới tự chỉnh).
- `IntegrityError` chỉ map `slug_taken` khi vi phạm `uq_invitations_slug`; lỗi khác raise tiếp.
- OpenAPI: `content` của Create/Update là object tự do (schema thật là `InvitationContent` ở response). FastAPI nhận `application/merge-patch+json` nhưng OpenAPI chỉ ghi `application/json`.
- Publish vẫn mã `missing_couple_names`, chỉ kiểm tra `full_name` hai bên: Bước 6 thay bằng `not_ready_to_publish`, `breaks_published_invitation`. `PublicInvitationOut` còn dạng khung (Bước 10). `gifts.bank_bin` chưa đối chiếu danh sách ngân hàng (Bước 8).
- ORM không biết `SET NULL (<cột>)`: xoá media xong, object `Invitation` trong session vẫn giữ id cũ, cần `refresh` (Bước 7).
- Test: fixture `minimal_01` có manifest khác `classic_01` (`make_minimal_manifest`); test tham chiếu media ghi thẳng `Media` vào DB (upload âm thanh thuộc Bước 7); test đồng thời đã thử bỏ khóa `FOR UPDATE` thì fail.
