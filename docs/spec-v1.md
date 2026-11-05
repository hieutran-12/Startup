Đặc tả backend thiệp cưới v1
5 thg 11, 2026 · @Hieu Tran
Mục đích và cách dùng
Tài liệu này là nguồn chuẩn cho backend v1: mọi quyết định về dữ liệu, ràng buộc và API đều nằm ở đây. Khi code khác tài liệu thì sửa code, không sửa tài liệu cho khớp code.
• Đưa vào repo: xuất doc này ra Markdown, lưu tại docs/spec-v1.md, rồi thêm vào CLAUDE.md dòng: "Đọc docs/spec-v1.md trước khi sửa code. Không tự thêm trường, bảng hay endpoint ngoài tài liệu; chỗ nào tài liệu chưa quy định thì dừng lại và hỏi."
• Điểm xuất phát: khung FastAPI gửi ngày 04/11/2026 (thiepcuoi-backend.zip). Mục "Kế hoạch triển khai" liệt kê từng thay đổi cần làm trên khung đó.
• Migration: chưa có dữ liệu production, nên viết lại migration đầu tiên thay vì thêm migration sửa đổi.
• Phiên bản: đây là v1 của đặc tả. Mỗi lần đổi quyết định, cập nhật tài liệu trước rồi mới sửa code.
Quyết định đã chốt
Mỗi thiệp có một bộ nội dung dùng chung cho cả hai bên. Sự kiện tách thành bảng riêng và gắn bên tổ chức. Mọi tham chiếu tới ảnh và nhạc cố định đều là khóa ngoại thật.
Năm câu hỏi mở
#
Câu hỏi
Chọn
Lý do
Đã loại
1
Một thiệp hay hai thiệp cho hai bên
Một thiệp nhiều sự kiện, mỗi sự kiện có host_side. Link riêng cho từng bên chỉ hiện sự kiện của bên đó
Thông tin cặp đôi, câu chuyện và album dùng chung nên không lặp dữ liệu. Khách vẫn chỉ thấy sự kiện mình được mời
Hai thiệp riêng: lặp toàn bộ nội dung và album, sửa hai nơi, dễ lệch nhau
2
Chuỗi rỗng và null
Trường văn bản không bắt buộc: rỗng sau khi trim thì lưu null. Trường bắt buộc: rỗng thì trả lỗi 422
Chỉ một cách biểu diễn "không có nội dung"; không truy vấn hay template nào phải kiểm tra hai giá trị
Phân biệt "" với null: hai cách biểu diễn cùng một nghĩa
3
Danh sách event_type
5 giá trị: engagement, family_ceremony, religious_ceremony, reception, other. Tên lễ (vu quy, thành hôn) suy ra từ event_type và host_side
Loại lễ và bên tổ chức là hai ý nghĩa, mỗi ý một trường; không tạo được tổ hợp vô lý
Enum gộp bên như vu_quy, thanh_hon: cho phép dữ liệu mâu thuẫn kiểu "vu quy do nhà trai tổ chức"
4
Các trường lời văn
greeting, invitation_message, guest_notes (thay additional_notes) và love_story dạng danh sách mốc. Câu báo hỷ của gia đình do template tự sinh
Mỗi trường có một vị trí và một giọng văn cố định (định nghĩa ở mục Mô hình dữ liệu)
additional_notes: tên quá chung, mỗi template sẽ hiểu một kiểu
5
Tham chiếu ảnh bìa, nhạc nền
Cột thật cover_media_id, music_media_id với khóa ngoại kép (id, cover_media_id) trỏ tới media (invitation_id, id)
Database bảo đảm file tồn tại và thuộc đúng thiệp; xoá file thì cột tự về null. Đã chạy thử trên PostgreSQL 16
Để trong JSONB: database không kiểm tra được, dễ trỏ tới file đã xoá hoặc của thiệp khác
Quyết định phụ
Vấn đề
Chọn
Lý do
Sự kiện lưu ở đâu
Bảng events, không nằm trong JSONB
Đây là dữ liệu nghiệp vụ: cần kiểu DATE/TIME, ràng buộc CHECK, và RSVP sau này cần event_id để tham chiếu
Ngày chính của thiệp
Không lưu cột riêng; lấy ngày sớm nhất trong events
Tránh lặp dữ liệu rồi lệch nhau
Giờ sự kiện
event_date + start_time + end_time + timezone (múi giờ IANA)
Khách cần giờ tại địa điểm, không cần một thời điểm UTC
Ngày âm lịch
Hệ thống tự tính khi trả trang public; bỏ trường cho người dùng gõ
Dữ liệu tính được thì không lưu; gõ tay dễ sai
Giao diện
palette_key, font_key, background_key chọn từ danh sách template cho phép; sections là danh sách section hiển thị theo thứ tự
Tập giá trị cố định, không ra thiệp vỡ bố cục. Màu tự chọn để dành cho gói trả phí
Mừng cưới
bank_bin theo danh sách ngân hàng của VietQR, số tài khoản dạng chuỗi chữ số; mã QR do template sinh
Không gõ tên ngân hàng tự do, không upload ảnh QR
Nhạc nền
Cặp đôi upload file âm thanh (bảng media, kind = audio)
Dùng lại luồng upload sẵn có. Thư viện nhạc có bản quyền để sau
Kiểu dữ liệu ở API
Kiểu chặt: số phải là số JSON, boolean phải là true/false; không tự đổi "2" thành 2
Một chuẩn duy nhất từ API tới database; chuyển đổi là việc của giao diện
Sửa thiệp
PATCH theo JSON Merge Patch (RFC 7386), kèm revision để chống ghi đè
Không gửi là giữ nguyên, gửi null là xoá. Hai tab cùng sửa không đè mất dữ liệu của nhau
Định dạng lỗi
Mọi lỗi, kể cả 422, cùng một dạng {"error": {code, message, details}}
FE xử lý lỗi ở một chỗ
Version nội dung
Cột content_schema_version
Nguyên tắc 10
Phiên bản PostgreSQL
Tối thiểu 15 (docker-compose đang dùng 16)
Cú pháp ON DELETE SET NULL (cột) có từ bản 15
Nguyên tắc bắt buộc
Mọi thay đổi code phải thỏa 14 nguyên tắc dưới đây. Nguyên tắc 1–10 là bộ gốc, 11–14 là phần bổ sung.
1. Một trường dữ liệu chỉ mang một ý nghĩa.
2. Một trường dữ liệu chỉ có một kiểu dữ liệu chuẩn.
3. Không lưu đơn vị đo trong giá trị số. Đơn vị nằm trong tên trường: size_bytes, amount_vnd.
4. Không dùng chuỗi tự do cho dữ liệu có tập giá trị xác định.
5. Tách dữ liệu nghiệp vụ khỏi dữ liệu hiển thị. Dữ liệu cần truy vấn, ràng buộc hoặc được nơi khác tham chiếu thì là cột hoặc bảng; dữ liệu chỉ để hiển thị thì nằm trong JSONB có schema.
6. Không lặp dữ liệu. Dữ liệu tính được (số ảnh trong album, ngày âm lịch, ngày chính của thiệp) thì tính khi trả về, không lưu.
7. Quy định rõ NULL, DEFAULT và NOT NULL cho từng cột và từng trường JSON.
8. Validation hai tầng. Database giữ kiểu, NOT NULL, UNIQUE, khóa ngoại và CHECK trên cột thường. Tầng API giữ schema của JSONB và các quy tắc nghiệp vụ.
9. Thống nhất quy ước đặt tên trên toàn dự án.
10. Dữ liệu có cấu trúc linh hoạt phải có số version.
11. API không đoán ý người dùng. Dữ liệu sai chuẩn thì từ chối kèm mã lỗi rõ ràng, không tự sửa.
12. Mọi chuỗi đều được trim và chuẩn hóa Unicode về dạng NFC trước khi lưu.
13. Tham chiếu tới tài nguyên khác bằng ID, không sao chép URL hay tên của tài nguyên đó.
14. Mã định danh gồm toàn chữ số (số tài khoản, mã ngân hàng, số điện thoại) là chuỗi, không phải số nguyên, vì số 0 ở đầu có ý nghĩa và không ai cộng trừ chúng.
Quy chuẩn dữ liệu
Mỗi loại dữ liệu có đúng một kiểu lưu trong database và một định dạng trên API. Giao diện có thể linh hoạt, nhưng dữ liệu gửi lên API phải đúng chuẩn này.
Kiểu dữ liệu
Loại
Kiểu PostgreSQL
Định dạng trên API
Quy tắc
ID
UUID
Chuỗi UUID chữ thường
Backend sinh, client không gửi
Văn bản một dòng (tên, địa điểm)
VARCHAR(n)
Chuỗi
Trim, NFC, gộp khoảng trắng liên tiếp thành một; không chứa xuống dòng hay ký tự điều khiển
Văn bản nhiều dòng (lời ngỏ, câu chuyện)
TEXT
Chuỗi
Trim hai đầu, NFC, đổi \r\n thành \n, tối đa 2 dòng trống liền nhau
Email
VARCHAR(320)
Chuỗi
Trim, chữ thường, kiểm tra định dạng
Số lượng
INTEGER
Số nguyên JSON
Không nhận chuỗi; ≥ 0 trừ khi quy định khác
Tiền
BIGINT
Số nguyên JSON
Đơn vị là đồng, tên trường có hậu tố _vnd. Cần nhiều loại tiền thì thêm cột currency (ISO 4217)
Phần trăm
NUMERIC(5,2)
Số JSON
Không dùng FLOAT
Ngày
DATE
"YYYY-MM-DD"

Giờ địa phương của sự kiện
TIME(0)
"HH:MM", 24 giờ
Luôn đi kèm timezone của sự kiện
Thời điểm hệ thống ghi nhận
TIMESTAMPTZ
ISO 8601 theo UTC, ví dụ "2026-11-05T06:30:00Z"
Dùng cho created_at, published_at…
Múi giờ
VARCHAR(64)
Tên IANA, ví dụ "Asia/Ho_Chi_Minh"
Phải nằm trong cơ sở dữ liệu múi giờ IANA
Trạng thái, loại
VARCHAR + CHECK
Chuỗi snake_case chữ thường
Tập giá trị cố định, khai báo bằng StrEnum trong code
Boolean
BOOLEAN NOT NULL
true/false
Không bao giờ null, luôn có mặc định. Tên bắt đầu bằng is_ hoặc has_
URL
VARCHAR(2048)
Chuỗi
Chỉ http hoặc https
Kích thước file
BIGINT
Số nguyên JSON
Đơn vị byte, tên trường có hậu tố _bytes
Thứ tự hiển thị
INTEGER
Số nguyên JSON
Bắt đầu từ 0, liên tục sau mỗi lần sắp xếp
Tọa độ
NUMERIC(9,6)
Số JSON
latitude trong [-90, 90], longitude trong [-180, 180]; có cả hai hoặc không có cái nào
Số điện thoại
VARCHAR(16)
Chuỗi E.164, ví dụ "+84912345678"
Giao diện đổi 0912 345 678 sang E.164 trước khi gửi
Mã định danh toàn chữ số
VARCHAR(n)
Chuỗi chỉ gồm 0-9
Số tài khoản 6–19 chữ số, BIN ngân hàng 6 chữ số
Nội dung linh hoạt
JSONB NOT NULL
Object
Có schema kiểm tra và content_schema_version
NULL, rỗng và mặc định
Loại trường
"Không có giá trị" được biểu diễn là
Ghi chú
Văn bản không bắt buộc
null
Chuỗi rỗng hoặc chỉ có khoảng trắng thì lưu null
Văn bản bắt buộc
Không được thiếu
Rỗng sau khi trim thì trả 422, mã required
Số
null là chưa biết, 0 là bằng không
Không tự đổi qua lại giữa hai giá trị
Boolean
Luôn true hoặc false
Gửi null thì trả 422
Danh sách
[]
Không bao giờ null; trong PATCH, gửi null cho danh sách nghĩa là đặt về []
Nhóm object (couple, groom, father…)
Luôn có mặt
Các trường con có thể là null
Không lưu chữ thay cho giá trị rỗng như "Không có", "N/A" hay "-". Giao diện để trống ô thì gửi null.
Quy tắc trên API
• Kiểu chặt: số và boolean dùng chế độ strict của Pydantic. "2", "02", "2 người", "true" đều bị từ chối.
• Ngày giờ chỉ nhận đúng định dạng ở bảng trên. Không nhận "20/12/2026" hay "11h".
• Trường lạ: mọi schema đặt extra="forbid". Gửi trường không có trong đặc tả thì trả 422, mã unknown_field.
• Response đầy đủ: response luôn trả mọi trường đã khai báo, kể cả trường có giá trị null, để FE không phải phân biệt "thiếu" với "rỗng".
• Không tự đổi chữ hoa thường của tên người hay địa danh. Chỉ email, slug và giá trị enum được chuẩn hóa về chữ thường.
Quy ước đặt tên
Toàn dự án dùng snake_case, trừ tên class (PascalCase), đường dẫn URL nhiều từ (kebab-case) và biến môi trường (UPPER_SNAKE_CASE).
Thành phần
Quy ước
Ví dụ
Bảng database
snake_case, số nhiều
invitations, events
Cột
snake_case
created_at
Khóa ngoại
<danh từ số ít>_id
invitation_id, cover_media_id
Constraint, index
Tiền tố pk_, uq_, fk_, ck_, ix_ theo naming convention đã có trong app/core/db.py
ck_events_event_type_valid
Biến, hàm Python
snake_case
create_invitation()
Class Python
PascalCase
Invitation
Schema Pydantic
PascalCase + hậu tố theo vai trò: Create, Update, Response
InvitationCreate, InvitationResponse (thay cho hậu tố Out hiện có)
Service
Hàm trong service.py của từng module, không viết thành class
invitations.service.publish(db, owner, invitation_id)
Endpoint
Chữ thường, danh từ số nhiều; nhiều từ thì dùng kebab-case
/invitations/{invitation_id}/events, /media/upload-url
Hành động nghiệp vụ không phải CRUD
POST với động từ đặt sau tài nguyên
POST /invitations/{invitation_id}/publish
Query param, key JSON
snake_case
album_id, event_date
Giá trị enum, key của template, palette, font
snake_case chữ thường
family_ceremony, classic_01, ivory_gold
Mã lỗi
snake_case
slug_taken
Biến môi trường
UPPER_SNAKE_CASE
DATABASE_URL
Hậu tố của tên trường cho biết kiểu dữ liệu:
• _at là TIMESTAMPTZ, _date là DATE, _time là TIME.
• _id là khóa, _count là số đếm, _bytes là dung lượng, _vnd là tiền.
• Boolean bắt đầu bằng is_ hoặc has_.
Key của template đổi từ kebab-case sang snake_case (classic-01 thành classic_01) để cùng quy ước với các key khác. Slug của thiệp vẫn là kebab-case vì nằm trên URL.
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
Ảnh: image/jpeg, image/png, image/webp, image/avif, tối đa 15 MB. Âm thanh: audio/mpeg, audio/mp4, tối đa 10 MB
Giới hạn số lượng
200 ảnh và 1 file âm thanh mỗi thiệp
Quy tắc nghiệp vụ và validation
Mọi lần ghi đều chạy theo thứ tự: chuẩn hóa chuỗi, kiểm tra schema, kiểm tra quy tắc nghiệp vụ, rồi mới lưu. Thiệp đã publish còn phải luôn thỏa điều kiện publish sau mỗi lần sửa.
Chuẩn hóa chuỗi
Viết thành các kiểu Annotated dùng lại được (ví dụ SingleLine(max_length), MultiLine(max_length) và bản bắt buộc của chúng), áp dụng theo thứ tự:
1. Chuẩn hóa Unicode về NFC.
2. Trim hai đầu.
3. Văn bản một dòng: gộp khoảng trắng liên tiếp thành một; có xuống dòng hoặc ký tự điều khiển thì trả lỗi invalid_characters.
4. Văn bản nhiều dòng: đổi \r\n và \r thành \n, giữ tối đa 2 dòng trống liền nhau.
5. Rỗng: trường không bắt buộc thì thành null, trường bắt buộc thì trả lỗi required.
6. Kiểm tra độ dài, đếm bằng số ký tự sau khi đã chuẩn hóa.
Tạo thiệp
• Tối đa 5 thiệp mỗi tài khoản. Khóa dòng users của chủ thiệp bằng SELECT … FOR UPDATE trước khi đếm, để hai request đồng thời không vượt giới hạn.
• Template phải đang hoạt động và không phải premium.
• Slug giữ nguyên quy tắc của khung hiện tại: tự sinh từ tên nếu không nhập, bỏ dấu tiếng Việt, thêm hậu tố khi trùng, chặn danh sách slug dành riêng.
• content khởi tạo là object v1 đầy đủ, với appearance.sections lấy từ manifest.default_sections. content_schema_version = 1, revision = 1.
Sửa thiệp
• PATCH /invitations/{invitation_id} nhận body dạng JSON Merge Patch (RFC 7386) cho các trường title, slug, template_key, content và bốn cột *_media_id.
• Cách gộp: object được gộp đệ quy, danh sách bị thay nguyên, null nghĩa là "không có giá trị" theo bảng NULL ở mục Quy chuẩn dữ liệu. Gộp xong thì kiểm tra lại toàn bộ content.
• Chống ghi đè: response của thiệp có header ETag: "<revision>". Mọi PATCH thiệp và mọi thao tác ghi sự kiện phải gửi If-Match: "<revision>". Thiếu header thì trả 428 revision_required; khác revision hiện tại thì trả 409 revision_conflict kèm revision mới nhất.
• revision tăng khi content, sự kiện, title, slug, template hoặc cột *_media_id thay đổi. Thao tác trên album và thư viện ảnh không làm tăng revision.
Đổi template
Khi template_key đổi, nội dung được giữ và chỉ phần giao diện được điều chỉnh, không trả lỗi:
• palette_key, font_key, background_key không có trong manifest mới thì về null.
• sections giữ các section template mới hỗ trợ, đúng thứ tự cũ. Nếu không còn section nào thì lấy manifest.default_sections của template mới.
Sự kiện
• Tối đa 10 sự kiện mỗi thiệp.
• Thứ tự hiển thị: event_date, rồi start_time, rồi position. Sự kiện chưa có ngày xếp cuối.
• timezone phải là tên có trong cơ sở dữ liệu múi giờ IANA (kiểm tra bằng zoneinfo).
• Tên mặc định khi event_name là null:
event_type
groom
bride
both
engagement
Lễ ăn hỏi
Lễ ăn hỏi
Lễ ăn hỏi
family_ceremony
Lễ thành hôn
Lễ vu quy
Không hợp lệ
religious_ceremony
Lễ cưới
Lễ cưới
Lễ cưới
reception
Tiệc cưới nhà trai
Tiệc cưới nhà gái
Tiệc cưới
other
Bắt buộc có event_name
Bắt buộc có event_name
Bắt buộc có event_name
Link theo bên
• GET /public/invitations/{slug} không có tham số thì trả mọi sự kiện và mọi tài khoản mừng cưới.
• Khi có ?side=groom hoặc ?side=bride: chỉ trả sự kiện có host_side bằng bên đó hoặc both, và tài khoản mừng cưới có recipient_side bằng bên đó. Response có trường side để template chọn câu báo hỷ và thứ tự hai gia đình.
• Next.js có ba đường dẫn cho mỗi thiệp: /{slug}, /{slug}/nha-trai, /{slug}/nha-gai. Webhook revalidate gửi slug, route phía Next.js tự build lại cả ba.
Publish
Publish thành công khi đủ các điều kiện sau. Thiếu điều kiện nào thì trả 400 not_ready_to_publish, trong details liệt kê đường dẫn từng trường còn thiếu.
• Có couple.groom.full_name và couple.bride.full_name.
• Có ít nhất một sự kiện, và sự kiện nào cũng có event_date, start_time, address.
• appearance.sections có cover và events.
Sau khi publish, mọi lần sửa cũng phải giữ đủ các điều kiện trên, nếu không thì trả 400 breaks_published_invitation. Thay đổi trên thiệp đã publish hiện ngay cho khách (v1 chưa tách bản nháp khỏi bản đã đăng).
Tham chiếu media
• Ba cột ảnh nhận file kind = image; music_media_id nhận file kind = audio. File phải ở trạng thái ready. Việc file thuộc đúng thiệp đã được khóa ngoại kép bảo đảm.
• love_story[].media_id không có khóa ngoại, nên service tự kiểm tra: ảnh, ready, thuộc chính thiệp.
• Khi xoá một file: database tự đưa các cột *_media_id về null; service xóa media_id đó khỏi love_story trong cùng transaction. Nếu file đó đang được thiệp tham chiếu, ở cột hoặc trong love_story, thì tăng revision.
Ngày âm lịch
• Response public trả kèm mỗi sự kiện có ngày một object lunar_date gồm day, month, year, is_leap_month và year_name (ví dụ "Bính Ngọ"). Giá trị này tính khi trả về, không lưu.
• Phải tính theo lịch Việt Nam dùng múi giờ UTC+7. Không dùng thư viện âm lịch Trung Quốc, vì lịch Trung Quốc tính theo UTC+8 và có năm lệch cả tháng.
• Test bắt buộc: ngày 21/01/1985 là mùng 1 Tết Ất Sửu theo lịch Việt Nam, trong khi Tết theo lịch Trung Quốc năm đó là 20/02/1985 (nguồn).
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
Kế hoạch triển khai
Giao cho Claude Code từng bước một, theo đúng thứ tự dưới đây. Bước nào cũng phải có test và qua uv run pytest cùng uv run ruff check . trước khi commit. Bước 0 làm trước hết, vì khung hiện tại chưa từng được chạy.
Bước
Việc cần làm
Tiêu chí nghiệm thu
0
Chạy khung hiện tại: docker compose up -d, uv sync, alembic upgrade head, pytest; sửa lỗi nếu có
28 test hiện có đều qua; app khởi động được và /docs mở được
1
Tầng chuẩn hóa: app/core/types.py (văn bản một dòng, nhiều dòng, chuỗi chữ số, giờ HH:MM, múi giờ), base model strict với extra="forbid", handler lỗi 422 theo định dạng chung
Test: chuỗi NFD lưu ra NFC; "" thành null; "2" bị từ chối ở trường số; trường lạ trả unknown_field; lỗi 422 có details đúng đường dẫn
2
Viết lại model và migration 0001 theo mục Mô hình dữ liệu, kể cả khóa ngoại kép và các CHECK
alembic upgrade head chạy trên PostgreSQL 16; alembic revision --autogenerate không sinh thay đổi nào; test database: gắn ảnh của thiệp khác bị từ chối, xoá ảnh thì cột về null, xoá thiệp không lỗi
3
Manifest template: schema TemplateManifest, seed lại 4 mẫu với key snake_case
Seed chạy lại nhiều lần vẫn đúng; manifest sai cấu trúc thì seed báo lỗi; GET /templates trả manifest
4
Schema content v1; tạo thiệp với nội dung mặc định; PATCH theo Merge Patch, revision, ETag, If-Match; quy tắc đổi template; kiểm tra tham chiếu media
Test: không gửi trường thì giữ nguyên, gửi null thì xoá, danh sách bị thay nguyên; thiếu If-Match trả 428, sai revision trả 409; đổi template thì key giao diện không hợp lệ về null; hai request tạo thiệp đồng thời không vượt giới hạn 5
5
Module events: CRUD, tên mặc định, thứ tự, giới hạn 10, If-Match
Test mọi CHECK (lễ gia tiên không nhận both, other bắt buộc có tên, giờ kết thúc sau giờ bắt đầu, tọa độ đủ cặp); bảng tên mặc định đúng từng ô
6
Quy tắc publish và breaks_published_invitation
Test từng điều kiện thiếu xuất hiện trong details; sửa thiệp đã publish mà xoá tên cô dâu thì bị từ chối
7
Media: cột kind, file âm thanh, giới hạn theo loại, xoá file thì dọn tham chiếu trong love_story
Test: upload mp3 cho music_media_id được, gán ảnh vào music_media_id bị từ chối; xoá ảnh đang dùng ở love_story thì media_id ở đó về null
8
Danh sách ngân hàng: file tĩnh, GET /banks, kiểm tra gifts
bank_bin không có trong danh sách bị từ chối; số tài khoản có chữ hoặc khoảng trắng bị từ chối
9
Âm lịch: app/core/lunar.py theo lịch Việt Nam UTC+7
Test ngày 21/01/1985 là mùng 1 tháng Giêng năm Ất Sửu; thêm ít nhất 5 ngày đối chiếu với lịch vạn niên Việt Nam, trong đó có một ngày thuộc tháng nhuận
10
Response public mới: lọc theo side, display_name, lunar_date, media_by_id
Test: ?side=bride không trả sự kiện hay tài khoản của nhà trai; response không có owner_id
11
Cập nhật README theo đặc tả; xoá code và test không còn dùng
Toàn bộ test qua, ruff sạch, README không còn nhắc tới event_date của thiệp, theme hay lunar_date_text
Mẫu câu giao việc cho từng bước:
Đọc docs/spec-v1.md. Làm Bước <số> trong mục "Kế hoạch triển khai", không làm sang bước khác.
Viết test theo "Tiêu chí nghiệm thu" trước, rồi mới viết code cho test qua.
Chỗ nào đặc tả chưa quy định thì dừng lại và hỏi tôi, không tự quyết.
Xong thì chạy uv run pytest và uv run ruff check ., báo kết quả, rồi commit.
Ngoài phạm vi v1
Các việc dưới đây không làm trong v1. Hướng thiết kế đã được ghi lại để mô hình v1 không chặn đường mở rộng sau này.
Việc
Hướng thiết kế khi làm
RSVP, danh sách khách, link riêng cho từng khách
Bảng guests (có side, số điện thoại E.164) và rsvps tham chiếu event_id. Link của khách tự lọc theo bên
Sổ lời chúc
Bảng wishes, endpoint public có giới hạn tần suất gửi
Nhiều người cùng sửa một thiệp
Bảng invitation_members (invitation_id, user_id, role). Không thêm cột chủ sở hữu thứ hai
Tách bản nháp khỏi bản đã đăng
Khi publish, lưu snapshot của response public; trang public đọc snapshot
Thanh toán gói trả phí
Mở khóa template premium và cho tự chọn mã màu
Thư viện nhạc có bản quyền
Bảng nhạc của hệ thống, dùng song song với file cặp đôi tự upload
Bảo mật tài khoản
Giới hạn tần suất đăng nhập và đăng ký, quên mật khẩu, xác minh email, đăng nhập Google/Zalo
Dọn dẹp định kỳ
Job xoá file pending quá 24 giờ, file mồ côi trên storage và refresh token hết hạn
Xử lý ảnh phía server
Tạo bản thu nhỏ và bản WebP sau khi upload
Sự kiện kéo qua nửa đêm
Thêm cột end_date, nới ràng buộc giờ kết thúc
Nguồn
• Vietnamese calendar (Wikiwand): lịch Việt Nam dùng UTC+7 và Tết 1985 lệch một tháng so với Trung Quốc.
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