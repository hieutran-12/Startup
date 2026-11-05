# invitations

## Mục đích
Bảng `invitations`, tạo/sửa/publish/xoá thiệp của chủ thiệp, kiểm tra slug và trang public theo slug.

## File code chính
- `app/modules/invitations/models.py`: `Invitation`, `InvitationStatus`, `MEDIA_REFERENCE_COLUMNS`, khóa ngoại kép tới media (viết lại ở Bước 2)
- `schemas.py`, `service.py`, `router.py` (`router` và `public_router`), `slugs.py`, `deps.py` (`OwnedInvitation`): từ khung, Bước 2 chỉ bỏ `event_date`

## API công khai
- Service: `list_for_owner`, `get_owned(db, owner, id, for_update=False)`, `check_slug`, `create`, `update`, `publish`, `unpublish`, `delete`, `get_public`
- `GET/POST /invitations`, `GET/PATCH/DELETE /invitations/{id}`, `GET /invitations/slug-availability`
- `POST /invitations/{id}/publish`, `POST /invitations/{id}/unpublish`
- `GET /public/invitations/{slug}`

## Phụ thuộc
- Dùng: core, auth (`User`), templates (`Template`), media (`Media`, `Album` khi xoá thiệp và trả trang public)
- Được dùng bởi: media (`OwnedInvitation`), events (FK `events.invitation_id`)

## Quy tắc spec đang áp dụng
- Cột, CHECK, khóa ngoại kép → `docs/spec/03-mo-hinh-du-lieu.md` › invitations
- CHECK: `ck_invitations_status_valid`, `ck_invitations_slug_valid` (mẫu + dài 3–60), `ck_invitations_published_at_matches_status`, `ck_invitations_content_schema_version_positive`
- `content` JSONB NOT NULL không DEFAULT: service luôn ghi object đầy đủ
- Bỏ cột `event_date`: ngày chính là `MIN(events.event_date)`, tính khi trả về

## Khóa ngoại kép `*_media_id`
- `cover_media_id`, `groom_photo_media_id`, `bride_photo_media_id`, `music_media_id`: `(id, <cột>) → media (invitation_id, id)`, `ON DELETE SET NULL (<cột>)`
- Tên tường minh `fk_invitations_cover_media`… (naming convention sẽ đặt cả bốn là `fk_invitations_id_media`)
- `use_alter=True`: invitations và media trỏ vào nhau; migration thêm bốn khóa bằng `ALTER TABLE` sau khi tạo bảng
- Database không kiểm tra `kind`/`status` của file: việc của service (Bước 4, 7)

## Lưu ý
- ORM không biết `SET NULL (<cột>)`: xoá media xong, object `Invitation` đang nằm trong session vẫn giữ id cũ, cần `refresh` nếu dùng tiếp (Bước 7).
- `revision`, `content_schema_version`, bốn cột `*_media_id` đã có trong model nhưng service chưa đọc/ghi (Bước 4).
- Schema content vẫn là `InvitationContent` cũ (`extra="allow"`, `events`/`bank_accounts` trong JSONB), schema request chưa dùng `StrictModel`: thay ở Bước 4.
- Bước 2 bỏ `event_date` khỏi `InvitationCreate`/`InvitationUpdate`/`InvitationOut`/`PublicInvitationOut`; schema cũ không `forbid` nên client cũ gửi `event_date` vẫn bị bỏ qua lặng lẽ.
- Publish mới kiểm tra tên cô dâu chú rể (Bước 6); response public còn dạng khung (Bước 10).
- Tạo thiệp hai request đồng thời có thể vượt giới hạn 5 (Bước 4).
- Slug sai mẫu lọt xuống database thì `IntegrityError` bị map thành `slug_taken`; hiện `slug_error` chặn trước nên không xảy ra.
