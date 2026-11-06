# media

## Mục đích
File của thiệp (bảng `media`, `kind` ảnh hoặc âm thanh) và album (bảng `albums`): xin link upload presigned, xác nhận upload, sắp xếp ảnh, gắn album, xoá file kèm dọn tham chiếu của thiệp. Bước 2: model. Bước 7: file âm thanh, giới hạn theo loại, dọn tham chiếu, schema strict.

## File code chính
- `models.py`: `Media`, `Album`, `MediaKind`, `MediaStatus`, CHECK, UNIQUE (Bước 2); `MediaMimeType` (8 loại file, `.kind`, `.extension`) (Bước 7)
- `schemas.py`: `UploadUrlRequest` (kiểm tra dung lượng theo loại, âm thanh không album), `CompleteUploadRequest`, `MediaUpdate`, `ReorderRequest`, `AlbumCreate`, `AlbumUpdate` (đều `StrictModel`); `UploadUrlResponse`, `MediaResponse`, `AlbumResponse`; `max_size_bytes(kind)`, `size_limit_message(kind)`
- `service.py`: upload, quản lý file, album; `_lock_invitation` (khóa dòng thiệp, `populate_existing`)
- `router.py`; `app/scripts/init_storage.py`: tạo bucket, CORS

## API công khai
- `POST /invitations/{id}/media/upload-url` → `UploadUrlResponse` (`headers` là `Content-Type` đúng loại client gửi); `POST .../media/{media_id}/complete` → `MediaResponse`
- `GET .../media?album_id=`: mọi file ready (ảnh và âm thanh), thứ tự `position, created_at`. `PUT .../media/order`: chỉ ảnh. `PATCH .../media/{media_id}` (`album_id`). `DELETE .../media/{media_id}` → 204, header `ETag`
- `GET`/`POST .../albums`, `PATCH`/`DELETE .../albums/{album_id}`
- `MediaResponse`: `id, kind, album_id, url, original_filename, mime_type, size_bytes, width, height, status, position, created_at`

## Phụ thuộc
- Dùng: core (storage, revalidate, `etag`, `StrictModel`, types), invitations (`OwnedInvitation`, `Invitation`, `MEDIA_REFERENCE_COLUMNS`, `service.release_media`)
- Được dùng bởi: invitations (khóa ngoại kép `*_media_id`, kiểm tra tham chiếu, xoá thiệp; trang public đọc `Media`, `Album`: `gallery`, `albums`, `media_by_id`)

## Quy tắc spec đang áp dụng
- Cột, `kind`, loại file, giới hạn → 03 › media; albums → 03 › Bảng giữ nguyên. `kind` suy ra từ `content_type` → 05
- Gán file đúng loại, ready; xoá file thì dọn tham chiếu, tăng revision → 04 › Tham chiếu media (kiểm tra khi gán: `invitations.md`)
- Spec 03 sửa ngày 2026-11-06 (người dùng yêu cầu): nhận thêm `audio/mp3`, `audio/x-m4a`; `mime_type` lưu đúng loại client gửi

## Quy tắc phụ chốt ở Bước 7 (người dùng duyệt 9 đề xuất, 2026-11-06)
1. Giới hạn đếm theo `kind`, gồm cả file pending; khóa dòng thiệp khi đếm. File âm thanh upload dở giữ chỗ tới khi FE gọi DELETE bằng `media_id` đã nhận. Đổi nhạc: xoá file cũ rồi upload file mới.
2. `content_type` ngoài danh sách → 422 `invalid_choice` (so khớp nguyên văn, không tự đổi chữ thường); vượt dung lượng → 422 `size_bytes` `out_of_range` ("Ảnh tối đa 15 MB", "File âm thanh tối đa 10 MB"); vượt số lượng → 400 `media_limit` ("Mỗi thiệp tối đa 200 ảnh", "... 1 file âm thanh"). `/complete` giữ 400 `upload_not_found`, `invalid_upload` (kiểm tra lại dung lượng theo loại, Content-Type thật phải đúng `mime_type`). Bỏ mã `unsupported_file_type`, `file_too_large` của khung.
3. Âm thanh + `album_id` (upload-url, PATCH) → 422 `album_id` `invalid_reference` "File âm thanh không nằm trong album"; `/complete` âm thanh có `width`/`height` khác null → 422 `invalid_format` (kể cả khi đã ready).
4. `MediaResponse` thêm `kind`; `GET /media` trả cả âm thanh, không thêm query param.
5. Ảnh mới: `position` = max của các ảnh + 1; âm thanh luôn 0. `PUT /media/order` có id không phải ảnh → 400 `invalid_media_ids`.
6. Xoá file: khóa dòng thiệp, không cần If-Match, 204 có `ETag` = revision sau khi xoá; không kiểm tra `breaks_published_invitation`; thiệp đã publish thì revalidate (như khung).
7. Mọi schema request (cả album) là `StrictModel`: `filename` `RequiredSingleLine(255)`, `title` `RequiredSingleLine(120)`, `album_id` `Uuid`. PATCH album: không gửi thì giữ, null → `required`. `MediaOut`/`AlbumOut` → `*Response`; giữ tên `*Request` cho body của hành động không phải CRUD.
8. Settings: `max_image_bytes`, `max_audio_bytes`, `max_images_per_invitation`, `max_audio_per_invitation` (thay `max_upload_bytes`, `max_media_per_invitation`, `allowed_image_types`). Đuôi file: `mp3` (`audio/mpeg`, `audio/mp3`), `m4a` (`audio/mp4`, `audio/x-m4a`).
9. Response public dạng khung: danh sách `media` chỉ có ảnh (Bước 10 thay bằng `gallery` chỉ có ảnh và `media_by_id` có mọi file ready: `invitations.md`).

## Thứ tự kiểm tra
- upload-url: 401 → 404 thiệp (dependency `OwnedInvitation`, chạy trước validate body) → 422 body (loại, dung lượng, âm thanh + album) → khóa dòng thiệp → 404 `album_not_found` → 400 `media_limit` → ghi.
- complete: 404 `media_not_found` → 422 kích thước của âm thanh → (đã ready: trả luôn) → 400 `upload_not_found` → 400 `invalid_upload` (xoá bản ghi và object) → ready.
- delete: 404 → khóa dòng thiệp → 404 file → `release_media` → xoá, flush → đọc lại bốn cột → commit.

## Lưu ý
- Xoá file: database đưa cột `*_media_id` về null (`ON DELETE SET NULL (<cột>)`); service gỡ `love_story[].media_id` và tăng revision qua `invitations.service.release_media`. Một file ở nhiều chỗ vẫn chỉ tăng revision 1. Sau flush phải `refresh` bốn cột vì ORM không biết SET NULL.
- Hai test đồng thời (4 request âm thanh; PATCH gắn file vào love_story cùng lúc DELETE file đó) đã thử bỏ khóa: fail 3/3 lần.
- Không có unique index cho "1 file âm thanh" (chốt Bước 2): khóa dòng thiệp giữ giới hạn.
- `storage.head` so `Content-Type` thật với `mime_type` (hạ chữ thường giá trị của storage khi so); file PUT với loại khác loại đã ký bị `invalid_upload`.
- File pending không bao giờ được xác nhận vẫn nằm trong DB và storage (khung chưa có việc dọn, ngoài phạm vi v1).
- Giữ index `ix_media_album_id`, `ix_media_invitation_position`, `ix_albums_invitation_id` của khung. `PATCH` album vẫn cho đặt `position` tùy ý như khung.
- Test: `tests/test_media.py` (upload, loại, giới hạn, schema, album), `tests/test_media_references.py` (gán vào thiệp, dọn tham chiếu); helper `upload_media` ở `tests/conftest.py`.
