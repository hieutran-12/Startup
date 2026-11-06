Mô hình dữ liệu
V1 có 7 bảng. users, refresh_tokens và albums giữ như khung hiện tại. templates, invitations và media thay đổi. events là bảng mới. Mọi bảng đều có id UUID làm khóa chính, cùng created_at và updated_at kiểu TIMESTAMPTZ NOT NULL; các bảng dưới đây không liệt kê lại ba cột này.
Mũi tên đi từ bảng giữ khóa ngoại tới bảng được tham chiếu. Nét đứt là bốn khóa ngoại kép từ invitations tới media, bảo đảm file được gắn phải thuộc đúng thiệp đó.
Bảng giữ nguyên
• users: email, password_hash (cho phép null, chừa chỗ đăng nhập Google/Zalo), full_name, is_active. full_name áp dụng quy tắc văn bản một dòng.
• refresh_tokens: giữ nguyên cơ chế xoay vòng token đã có.
• albums: invitation_id, title (một dòng, tối đa 120 ký tự), position.
templates
Cột
Kiểu
Null
Mặc định
Ràng buộc, ghi chú
key
VARCHAR(64)
Không

UNIQUE; snake_case, ví dụ classic_01
name
VARCHAR(120)
Không


description
TEXT
Có


thumbnail_url
VARCHAR(2048)
Có

Ảnh hệ thống, không phải file người dùng upload
category
VARCHAR(32)
Không

CHECK trong classic, minimal, floral, vintage, modern
is_premium
BOOLEAN
Không
false

is_active
BOOLEAN
Không
true

position
INTEGER
Không
0
Đổi tên từ sort_order cho cùng quy ước với albums, media
manifest
JSONB
Không

Thay field_schema. Khai báo những gì template hỗ trợ (xem bên dưới)
manifest là hợp đồng giữa backend và component React của template. Thêm một palette hay section thì sửa seed và component cùng lúc. Cấu trúc do schema Pydantic TemplateManifest kiểm tra khi seed:
• sections: các section template vẽ được, lấy từ danh sách cố định ở mục nội dung bên dưới.
• default_sections: danh sách section mặc định theo thứ tự, phải là tập con của sections.
• palettes: danh sách {key, name, primary, secondary, background, text}; màu viết dạng #RRGGBB chữ hoa.
• fonts, backgrounds: danh sách {key, name}.
• defaults: {palette_key, font_key, background_key}, mỗi giá trị phải có trong danh sách tương ứng.
• max_gallery_images: số ảnh tối đa template hiển thị.
invitations
Cột
Kiểu
Null
Mặc định
Ràng buộc, ghi chú
owner_id
UUID
Không

FK users, ON DELETE CASCADE, có index. Chỉ dùng để phân quyền, không trả ra API public
template_id
UUID
Không

FK templates, ON DELETE RESTRICT
slug
VARCHAR(60)
Không

UNIQUE; CHECK theo mẫu ^[a-z0-9]+(-[a-z0-9]+)*$, dài 3–60 ký tự
title
VARCHAR(120)
Không

Tên nội bộ hiện ở dashboard, không hiện trên thiệp
status
VARCHAR(16)
Không
'draft'
CHECK trong draft, published
published_at
TIMESTAMPTZ
Có

CHECK ((status = 'published') = (published_at IS NOT NULL))
content
JSONB
Không
Không có
Service luôn ghi object đầy đủ theo schema v1, không dựa vào mặc định của database
content_schema_version
INTEGER
Không
1
CHECK (content_schema_version > 0)
revision
INTEGER
Không
1
Tăng 1 sau mỗi lần ghi vào thiệp hoặc sự kiện của thiệp; dùng để chống ghi đè
cover_media_id
UUID
Có

Ảnh bìa
groom_photo_media_id
UUID
Có

Ảnh chân dung chú rể
bride_photo_media_id
UUID
Có

Ảnh chân dung cô dâu
music_media_id
UUID
Có

Nhạc nền
Bỏ cột event_date của khung cũ; ngày chính của thiệp là MIN(events.event_date).
Bốn cột *_media_id dùng cùng một mẫu khóa ngoại kép, ví dụ với ảnh bìa:
ALTER TABLE invitations ADD CONSTRAINT fk_invitations_cover_media
  FOREIGN KEY (id, cover_media_id) REFERENCES media (invitation_id, id)
  ON DELETE SET NULL (cover_media_id);
Khóa này khiến database từ chối ảnh của thiệp khác và tự đưa cột về null khi file bị xoá. Database không kiểm tra được loại file, nên service phải kiểm tra: ba cột ảnh chỉ nhận kind = image, music_media_id chỉ nhận kind = audio, và file phải ở trạng thái ready. Vì hai bảng trỏ vào nhau, migration tạo invitations và media trước, rồi mới thêm bốn khóa này bằng ALTER TABLE.
events (bảng mới)
Cột
Kiểu
Null
Mặc định
Ràng buộc, ghi chú
invitation_id
UUID
Không

FK invitations, ON DELETE CASCADE
event_type
VARCHAR(32)
Không

CHECK trong engagement, family_ceremony, religious_ceremony, reception, other
host_side
VARCHAR(8)
Không

CHECK trong groom, bride, both
event_name
VARCHAR(120)
Có

Tên hiển thị tùy chỉnh; null thì dùng tên mặc định theo loại lễ và bên
event_date
DATE
Có

Được để trống khi còn nháp; bắt buộc khi publish
start_time
TIME(0)
Có

Giờ địa phương; bắt buộc khi publish
end_time
TIME(0)
Có


timezone
VARCHAR(64)
Không
'Asia/Ho_Chi_Minh'
Tên múi giờ IANA
venue_name
VARCHAR(200)
Có

Tên địa điểm, ví dụ "Nhà hàng ABC"
address
VARCHAR(500)
Có

Địa chỉ; bắt buộc khi publish
latitude
NUMERIC(9,6)
Có

[-90, 90]
longitude
NUMERIC(9,6)
Có

[-180, 180]
maps_url
VARCHAR(2048)
Có

Link mở app chỉ đường; không parse lấy tọa độ từ link này
position
INTEGER
Không
0
Index (invitation_id, position)
Ràng buộc CHECK trên nhiều cột:
• event_type <> 'family_ceremony' OR host_side <> 'both': lễ gia tiên luôn thuộc một bên.
• event_type <> 'other' OR event_name IS NOT NULL: loại other bắt buộc có tên.
• end_time IS NULL OR (start_time IS NOT NULL AND end_time > start_time). V1 không hỗ trợ sự kiện kéo qua nửa đêm.
• (latitude IS NULL) = (longitude IS NULL), kèm CHECK khoảng giá trị của từng cột.
media
Giữ các cột đã có (invitation_id, album_id, storage_key, original_filename, mime_type, size_bytes, width, height, status, position) và thêm:
Thay đổi
Chi tiết
Cột kind
VARCHAR(8) NOT NULL, CHECK trong image, audio
UNIQUE (invitation_id, id)
Đích đến của các khóa ngoại kép từ invitations
CHECK (kind = 'image' OR (width IS NULL AND height IS NULL AND album_id IS NULL))
File âm thanh không có kích thước ảnh và không nằm trong album
Loại file cho phép
Ảnh: image/jpeg, image/png, image/webp, image/avif, tối đa 15 MB. Âm thanh: audio/mpeg, audio/mp4, tối đa 10 MB; nhận thêm audio/mp3 (một số trình duyệt báo file .mp3 như vậy) và audio/x-m4a (trình duyệt thường báo file .m4a như vậy). mime_type lưu đúng loại client gửi, không đổi sang loại chuẩn
Giới hạn số lượng
200 ảnh và 1 file âm thanh mỗi thiệp
Nội dung thiệp (content, schema version 1)
content chỉ chứa dữ liệu hiển thị, gồm năm nhóm: couple, messages, love_story, gifts, appearance. Sự kiện và các ảnh cố định không nằm ở đây.
couple.groom và couple.bride có cùng cấu trúc:
Trường
Kiểu
Null
Tối đa
Ý nghĩa
full_name
Một dòng
Có khi còn nháp, bắt buộc khi publish
100
Họ tên đầy đủ
display_name
Một dòng
Có
40
Tên gọi in to trên thiệp ("Nam"); null thì template dùng full_name
birth_order
Enum eldest, middle, youngest
Có

Thứ bậc trong nhà; template in "Trưởng nam", "Thứ nữ"…; null thì không in
bio
Nhiều dòng
Có
500
Giới thiệu ngắn về người này
father, mother
Object Parent
Không

Luôn có mặt, các trường con có thể null
family_address
Một dòng
Có
300
Địa chỉ gia đình in dưới tên bố mẹ; khác với địa chỉ sự kiện
Parent gồm full_name (một dòng, tối đa 100, có thể null) và is_deceased (boolean, mặc định false). Khi is_deceased là true, template in chữ "Cố" trước tên; người dùng không gõ chữ này vào ô tên.
messages gồm ba trường nhiều dòng, đều có thể null:
Trường
Tối đa
Hiển thị ở đâu
Viết gì
Không viết gì
greeting
1.000
Mở đầu, ngay dưới ảnh bìa
Lời ngỏ của cặp đôi gửi khách, giọng thân mật
Ngày giờ, địa điểm
invitation_message
500
Ngay trên danh sách sự kiện
Câu mời trang trọng của gia đình; null thì template dùng câu mặc định
Tên khách, tên lễ, ngày giờ: template lấy từ dữ liệu
guest_notes
1.000
Cuối thiệp
Thông tin thực tế: trang phục, chỗ gửi xe, giờ đón khách
Lời chúc, lời mời
Câu báo hỷ của gia đình ("Trân trọng báo tin lễ vu quy của con chúng tôi") không có ô nhập. Template sinh câu này từ loại lễ và bên đang xem.
love_story là danh sách tối đa 12 mốc, theo thứ tự hiển thị:
Trường
Kiểu
Null
Ghi chú
title
Một dòng, tối đa 100
Không
Ví dụ "Lần đầu gặp nhau"
description
Nhiều dòng, tối đa 1.000
Có

year
Số nguyên 1900–2100
Có

month
Số nguyên 1–12
Có
Chỉ được có khi đã có year
media_id
UUID
Có
Ảnh ready của chính thiệp
Mốc thời gian lưu bằng year và month thay vì chuỗi kiểu "tháng 3/2019", vì phần lớn mốc chỉ nhớ được tới tháng.
gifts là danh sách tối đa 4 tài khoản mừng cưới:
Trường
Kiểu
Null
Ghi chú
recipient_side
Enum groom, bride
Không
Tài khoản của bên nào
bank_bin
Chuỗi 6 chữ số
Không
Phải có trong danh sách ngân hàng của hệ thống
account_number
Chuỗi 6–19 chữ số
Không
Giao diện bỏ khoảng trắng và dấu chấm trước khi gửi
account_holder
Một dòng, tối đa 100
Không

Danh sách ngân hàng là một file tĩnh trong repo (bin, short_name, name), lấy từ danh sách ngân hàng công khai của VietQR (kiểm tra lại nguồn khi triển khai) và trả ra qua GET /banks. Mã QR do template sinh theo chuẩn VietQR từ bank_bin và account_number.
appearance:
Trường
Kiểu
Null
Ghi chú
palette_key, font_key, background_key
Chuỗi
Có
Phải có trong manifest của template; null thì dùng manifest.defaults
sections
Danh sách key section
Không
Các section hiển thị, theo đúng thứ tự; không trùng, phải là tập con của manifest.sections. Section không có trong danh sách là bị ẩn
Key section cố định của v1: cover, greeting, couple, love_story, events, countdown, gallery, gifts, guest_notes. Nhạc nền là trình phát, không phải section.
Ví dụ một content hợp lệ:
{
  "couple": {
    "groom": {
      "full_name": "Nguyễn Văn Nam", "display_name": "Nam", "birth_order": "eldest", "bio": null,
      "father": {"full_name": "Nguyễn Văn Hùng", "is_deceased": false},
      "mother": {"full_name": "Trần Thị Hoa", "is_deceased": true},
      "family_address": "Số 12 ngõ 34 Láng Hạ, Đống Đa, Hà Nội"
    },
    "bride": {
      "full_name": "Lê Thị Lan", "display_name": "Lan", "birth_order": null, "bio": null,
      "father": {"full_name": null, "is_deceased": false},
      "mother": {"full_name": null, "is_deceased": false},
      "family_address": null
    }
  },
  "messages": {"greeting": "Cảm ơn bạn đã là một phần trong câu chuyện của chúng mình.", "invitation_message": null, "guest_notes": null},
  "love_story": [{"title": "Lần đầu gặp nhau", "description": null, "year": 2019, "month": 3, "media_id": null}],
  "gifts": [{"recipient_side": "groom", "bank_bin": "970436", "account_number": "0123456789", "account_holder": "NGUYEN VAN NAM"}],
  "appearance": {"palette_key": null, "font_key": null, "background_key": null, "sections": ["cover", "greeting", "couple", "events", "gallery", "gifts"]}
}
Liên quan: 02-nguyen-tac-va-quy-chuan.md, 04-nghiep-vu.md
