# media

## Mục đích
File của thiệp (bảng `media`) và album (bảng `albums`): xin link upload presigned, xác nhận upload, sắp xếp, gắn album, xoá.

## File code chính
- `app/modules/media/models.py`: `Media`, `Album`, `MediaKind`, `MediaStatus` (Bước 2 thêm `kind`, CHECK, UNIQUE)
- `schemas.py`, `service.py`, `router.py`: từ khung, Bước 2 chỉ ghi `kind`
- `app/scripts/init_storage.py`: tạo bucket, CORS

## API công khai
- `POST /invitations/{id}/media/upload-url`, `POST /invitations/{id}/media/{media_id}/complete`
- `GET /invitations/{id}/media?album_id=`, `PUT /invitations/{id}/media/order`, `PATCH`/`DELETE /invitations/{id}/media/{media_id}`
- `GET`/`POST /invitations/{id}/albums`, `PATCH`/`DELETE /invitations/{id}/albums/{album_id}`

## Phụ thuộc
- Dùng: core (storage, revalidate), invitations (`OwnedInvitation`, `Invitation`)
- Được dùng bởi: invitations (khóa ngoại kép `*_media_id`, trang public, xoá thiệp)

## Quy tắc spec đang áp dụng
- Cột của media → `docs/spec/03-mo-hinh-du-lieu.md` › media; albums → 03 › Bảng giữ nguyên
- `kind` VARCHAR(8) NOT NULL, không DEFAULT; `ck_media_kind_valid` (image, audio)
- `ck_media_audio_has_no_image_fields`: `kind = 'image'` hoặc `width`, `height`, `album_id` đều null
- `uq_media_invitation_id (invitation_id, id)`: đích đến của khóa ngoại kép từ invitations
- Xoá file thì cột `*_media_id` trỏ tới nó về null (do database, xem `invitations.md`)

## Lưu ý
- `create_upload` luôn ghi `kind = image` và chỉ nhận ảnh theo `settings`. File âm thanh, giới hạn theo loại (15 MB ảnh, 10 MB âm thanh, 200 ảnh, 1 file âm thanh) và dọn tham chiếu trong `love_story` làm ở Bước 7.
- Không có unique index cho "1 file âm thanh mỗi thiệp" (đã chốt Bước 2): service kiểm tra.
- Giữ index `ix_media_album_id`, `ix_media_invitation_position`, `ix_albums_invitation_id` của khung.
- Schema còn hậu tố `Out`, chưa dùng `StrictModel`.
