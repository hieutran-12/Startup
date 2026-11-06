# invitations

## Mục đích
Bảng `invitations`, schema content v1, tạo/sửa/publish/xoá thiệp (Merge Patch, revision, ETag/If-Match, đổi template, tham chiếu media), kiểm tra slug, trang public theo slug.

## File code chính
- `models.py`: `Invitation`, `InvitationStatus`, `MEDIA_REFERENCE_COLUMNS`, khóa ngoại kép tới media (Bước 2)
- `schemas.py`: content v1 (`InvitationContent`, `Couple`, `Person`, `Parent`, `Messages`, `LoveStoryItem`, `Gift`, `Appearance`, `BirthOrder`, `RecipientSide`), `Slug`/`OptionalSlug`, `InvitationCreate`, `InvitationUpdate`, `InvitationResponse` (Bước 4). `SlugAvailability`, `Public*` từ khung
- `service.py`, `router.py`: viết lại ở Bước 4; điều kiện publish ở Bước 6. `slugs.py`, `deps.py` (`OwnedInvitation`): từ khung

## API công khai
- `GET/POST /invitations`, `GET/PATCH/DELETE /invitations/{id}`, `GET /invitations/slug-availability`, `POST /invitations/{id}/publish|unpublish`, `GET /public/invitations/{slug}`
- Response một thiệp (tạo, xem, sửa, publish, unpublish) có header `ETag: "<revision>"`; danh sách thì không. PATCH bắt buộc `If-Match` (dependency `IfMatch` của core)
- Service: `create`, `update(db, owner, id, data, if_match)` → (thiệp, slug cần revalidate), `to_response`, `list_for_owner` (trả `InvitationResponse`), `get_owned(for_update=)`, `default_content(manifest)`, `adjust_appearance(appearance, manifest)`, `publish`, `unpublish`, `publish_errors(content, events)` (danh sách lỗi `required`, rỗng là đủ điều kiện), `check_still_publishable(db, invitation, content=None)` (thiệp đã publish: không đạt thì rollback, 400 `breaks_published_invitation`), `release_media(invitation, media_id)` (Bước 7: trước khi xoá file, gỡ `love_story[].media_id`, tăng revision nếu thiệp đang dùng file; media gọi), `delete`, `get_public`, `check_slug`
- `InvitationContent.model_validate(data, context={"manifest": TemplateManifest})` kiểm tra cả appearance theo manifest và `gifts[].bank_bin` theo danh sách ngân hàng (Bước 8, `invalid_choice`); không có context thì chỉ kiểm tra cấu trúc (dùng khi trả response)

## Phụ thuộc
- Dùng: core (`merge_patch`, `revision`, `validation_error`, `field_error`), auth (`User`), banks (`is_known_bin`), templates (`TemplateManifest`, `Key`, `SectionKey`), media (`Media`, `MediaKind`, `MediaStatus`, `Album`), events (`Event`, `display_order()`: `primary_event_date`, điều kiện publish)
- Được dùng bởi: media (`OwnedInvitation`, `MEDIA_REFERENCE_COLUMNS`, `release_media`), events (`get_owned(for_update=True)`, tăng `revision` của thiệp, `check_still_publishable` khi ghi sự kiện)

## Quy tắc spec đang áp dụng
- Cột, CHECK, khóa ngoại kép → 03 › invitations. Content v1 → 03 › Nội dung thiệp. NULL/rỗng → 02
- Tạo thiệp (khóa dòng users `FOR UPDATE` rồi đếm, content mặc định, `revision = 1`), Sửa thiệp, Đổi template, Tham chiếu media → 04
- Điều kiện publish, `breaks_published_invitation` → 04 › Publish
- `gifts[].bank_bin` có trong danh sách ngân hàng → 03 › Nội dung thiệp; quy tắc phụ Bước 8 ở `banks.md`
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

## Quy tắc phụ chốt ở Bước 6 (người dùng duyệt 8 đề xuất, 2026-11-06)
1. `details` của `not_ready_to_publish`: mọi dòng mã `required`, theo thứ tự spec: `content.couple.{groom,bride}.full_name`; `events` (chưa có sự kiện); `events[i].{event_date,start_time,address}` với `i` theo thứ tự hiển thị của trạng thái sau khi sửa (khớp GET .../events); `content.appearance.sections` mỗi section thiếu một dòng, message có `(cover)`/`(events)`.
2. `breaks_published_invitation` (400): cùng dạng `details`, liệt kê mọi điều kiện không đạt sau khi sửa.
3. Kiểm tra sau mọi lỗi 422, 409 `slug_taken`, 400 `event_limit`, ngay trước khi ghi; bị từ chối thì không ghi, không tăng revision, không revalidate. PATCH không đổi gì vẫn 200.
4. Áp dụng: PATCH thiệp, POST/PATCH/DELETE sự kiện. Unpublish, xoá thiệp, album, media không kiểm tra.
5. Đổi template làm mất `cover`/`events` (sau `adjust_appearance`) trên thiệp đã publish → 400 `breaks_published_invitation`; thiệp nháp vẫn đổi được, không lỗi.
6. Thiệp đã publish thêm sự kiện thì POST phải đủ ngày, giờ, địa chỉ.
7. Publish thiệp đã publish: giữ như khung (kiểm tra lại, `published_at = now`, revalidate); không If-Match, không tăng revision.
8. Message: `not_ready_to_publish` "Thiệp chưa đủ thông tin để đăng", `breaks_published_invitation` "Thiệp đang đăng phải giữ đủ thông tin bắt buộc"; từng dòng ở `_REQUIRED_*` trong `service.py`.

## Thứ tự kiểm tra
PATCH: 401 → 428 thiếu If-Match → 422 body → 404 → 409 revision (sau `SELECT … FOR UPDATE`) → 404/400 template → 422 content và tham chiếu media (gộp chung một lần) → 409 slug → (không đổi gì: 200, dừng) → 400 `breaks_published_invitation` (thiệp đã publish) → ghi, tăng revision.

Publish: 401 → 404 → khóa dòng thiệp `FOR UPDATE` → đọc sự kiện theo thứ tự hiển thị → 400 `not_ready_to_publish` → ghi. Ghi sự kiện cũng khóa dòng thiệp trước, nên không xoá được sự kiện giữa lúc kiểm tra và lúc đăng (test đồng thời đã thử bỏ khóa: fail).

## Lưu ý
- Tham chiếu media chỉ kiểm tra khi có trong request (cột gửi khác null; `love_story` có trong patch thì kiểm tra cả danh sách). Gửi lại đúng id cũ mà file đã hỏng vẫn bị 422.
- Seed đổi manifest của template đang dùng mà appearance đã lưu không còn hợp lệ: mọi PATCH có content sẽ 422 tới khi sửa appearance (chỉ đổi template mới tự chỉnh).
- `IntegrityError` chỉ map `slug_taken` khi vi phạm `uq_invitations_slug`; lỗi khác raise tiếp.
- OpenAPI: `content` của Create/Update là object tự do (schema thật là `InvitationContent` ở response). FastAPI nhận `application/merge-patch+json` nhưng OpenAPI chỉ ghi `application/json`.
- Điều kiện publish chỉ xét `full_name` (`display_name` không thay được). `PublicInvitationOut` còn dạng khung (Bước 10); từ Bước 7 danh sách `media` chỉ có ảnh; `content.gifts` chưa lọc theo side (Bước 10).
- ORM không biết `SET NULL (<cột>)`: xoá media xong, object `Invitation` trong session vẫn giữ id cũ. `media.service.delete_media` `refresh` bốn cột sau flush (Bước 7); code khác xoá media trong session còn giữ thiệp thì cũng phải refresh.
- Test publish: `tests/test_publish.py` (fixture `no_events_01` là mẫu không có section events). Test khác publish thiệp thì thêm sự kiện đủ ngày, giờ, địa chỉ (`_add_ready_event` ghi thẳng DB để giữ revision).
- Test: fixture `minimal_01` có manifest khác `classic_01` (`make_minimal_manifest`); test tham chiếu media ở đây ghi thẳng `Media` vào DB; luồng upload thật và dọn tham chiếu khi xoá file: `tests/test_media_references.py`; test đồng thời đã thử bỏ khóa `FOR UPDATE` thì fail.
