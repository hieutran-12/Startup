API
Các endpoint auth, template, ảnh và album của khung hiện tại được giữ. V1 thêm endpoint sự kiện và danh sách ngân hàng, đổi cách sửa thiệp, thống nhất định dạng lỗi và mở rộng response public.
Endpoint mới hoặc thay đổi
Endpoint
Thay đổi
PATCH /invitations/{invitation_id}
Body dạng JSON Merge Patch, bắt buộc If-Match; nhận thêm bốn cột *_media_id
GET /invitations/{invitation_id} và các response thiệp khác
Thêm revision, content_schema_version, primary_event_date (tính từ sự kiện), bốn cột *_media_id; header ETag
GET /invitations/{invitation_id}/events
Mới. Danh sách sự kiện theo thứ tự hiển thị
POST /invitations/{invitation_id}/events
Mới. Bắt buộc If-Match; response có ETag chứa revision mới của thiệp
PATCH /invitations/{invitation_id}/events/{event_id}
Mới. JSON Merge Patch, bắt buộc If-Match
DELETE /invitations/{invitation_id}/events/{event_id}
Mới. Bắt buộc If-Match
POST /invitations/{invitation_id}/media/upload-url
kind suy ra từ content_type (image/* là ảnh, audio/* là âm thanh), client không gửi
GET /banks
Mới. Danh sách ngân hàng {bin, short_name, name} cho dropdown
GET /public/invitations/{slug}
Thêm tham số ?side=groom hoặc ?side=bride; cấu trúc response mới (bên dưới)
Định dạng lỗi
Mọi lỗi dùng chung một dạng. Handler của RequestValidationError phải được ghi đè để lỗi 422 cũng theo dạng này.
{
  "error": {
    "code": "validation_error",
    "message": "Dữ liệu không hợp lệ",
    "details": [
      {"field": "content.couple.groom.full_name", "code": "required", "message": "Không được để trống"},
      {"field": "start_time", "code": "invalid_format", "message": "Giờ phải có dạng HH:MM"}
    ]
  }
}
• details luôn là danh sách, rỗng khi không có chi tiết. field viết theo dạng đường dẫn có dấu chấm, phần tử danh sách viết love_story[0].title.
• Mã lỗi của từng trường: required, invalid_format, invalid_characters, too_long, out_of_range, invalid_choice, unknown_field, invalid_reference.
• Mã HTTP: 400 lỗi nghiệp vụ, 401 chưa đăng nhập, 404 không tìm thấy hoặc không có quyền, 409 xung đột (slug_taken, revision_conflict), 422 sai định dạng dữ liệu, 428 thiếu If-Match.
Response của trang public
Trường
Nội dung
slug, template_key

side
null, groom hoặc bride, theo tham số đã gửi
content_schema_version, content
Nội dung đã lưu; riêng content.gifts được lọc theo side
cover_media_id, groom_photo_media_id, bride_photo_media_id, music_media_id
ID, tra URL trong media_by_id
events
Danh sách đã lọc theo side và đã sắp xếp. Mỗi phần tử có các cột của bảng events (trừ invitation_id, position), cộng display_name (là event_name hoặc tên mặc định) và lunar_date (null khi chưa có ngày)
albums
{id, title, position}
gallery
Ảnh thư viện theo thứ tự, mỗi phần tử {media_id, album_id}
media_by_id
Map từ ID sang {kind, url, width, height} cho mọi file ready của thiệp
published_at, updated_at

Response public không chứa owner_id, status, revision. Mọi tham chiếu file đều là ID và tra URL trong media_by_id, nên content được trả đúng như đã lưu (trừ phần gifts đã lọc). Header Cache-Control giữ như khung hiện tại.
Liên quan: 04-nghiep-vu.md, 03-mo-hinh-du-lieu.md, 02-nguyen-tac-va-quy-chuan.md
