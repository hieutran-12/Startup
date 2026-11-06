# Đặc tả backend thiệp cưới v1

5 thg 11, 2026 · @Hieu Tran

## Mục đích và cách dùng

Tài liệu này là nguồn chuẩn cho backend v1: mọi quyết định về dữ liệu, ràng buộc và API đều nằm ở đây. Khi code khác tài liệu thì sửa code, không sửa tài liệu cho khớp code.

- **Trong repo:** spec nằm ở `docs/spec/01`–`07`, tách từ bản xuất `docs/spec-v1.md` (chỉ lưu trữ). `CLAUDE.md` trỏ tới đây.
- **Điểm xuất phát:** khung FastAPI gửi ngày 04/11/2026 (`thiepcuoi-backend.zip`). `06-ke-hoach.md` liệt kê từng thay đổi cần làm trên khung đó.
- **Migration:** chưa có dữ liệu production, nên viết lại migration đầu tiên thay vì thêm migration sửa đổi.
- **Phiên bản:** đây là v1 của đặc tả. Mỗi lần đổi quyết định, cập nhật tài liệu trước rồi mới sửa code.

## Quyết định đã chốt

Mỗi thiệp có một bộ nội dung dùng chung cho cả hai bên. Sự kiện tách thành bảng riêng và gắn bên tổ chức. Mọi tham chiếu tới ảnh và nhạc cố định đều là khóa ngoại thật.

### Năm câu hỏi mở

| # | Câu hỏi | Chọn | Lý do | Đã loại |
| --- | --- | --- | --- | --- |
| 1 | Một thiệp hay hai thiệp cho hai bên | Một thiệp nhiều sự kiện, mỗi sự kiện có `host_side`. Link riêng cho từng bên chỉ hiện sự kiện của bên đó | Thông tin cặp đôi, câu chuyện và album dùng chung nên không lặp dữ liệu. Khách vẫn chỉ thấy sự kiện mình được mời | Hai thiệp riêng: lặp toàn bộ nội dung và album, sửa hai nơi, dễ lệch nhau |
| 2 | Chuỗi rỗng và `null` | Trường văn bản không bắt buộc: rỗng sau khi trim thì lưu `null`. Trường bắt buộc: rỗng thì trả lỗi 422 | Chỉ một cách biểu diễn "không có nội dung"; không truy vấn hay template nào phải kiểm tra hai giá trị | Phân biệt `""` với `null`: hai cách biểu diễn cùng một nghĩa |
| 3 | Danh sách `event_type` | 5 giá trị: `engagement`, `family_ceremony`, `religious_ceremony`, `reception`, `other`. Tên lễ (vu quy, thành hôn) suy ra từ `event_type` và `host_side` | Loại lễ và bên tổ chức là hai ý nghĩa, mỗi ý một trường; không tạo được tổ hợp vô lý | Enum gộp bên như `vu_quy`, `thanh_hon`: cho phép dữ liệu mâu thuẫn kiểu "vu quy do nhà trai tổ chức" |
| 4 | Các trường lời văn | `greeting`, `invitation_message`, `guest_notes` (thay `additional_notes`) và `love_story` dạng danh sách mốc. Câu báo hỷ của gia đình do template tự sinh | Mỗi trường có một vị trí và một giọng văn cố định (định nghĩa ở mục Mô hình dữ liệu) | `additional_notes`: tên quá chung, mỗi template sẽ hiểu một kiểu |
| 5 | Tham chiếu ảnh bìa, nhạc nền | Cột thật `cover_media_id`, `music_media_id` với khóa ngoại kép `(id, cover_media_id)` trỏ tới `media (invitation_id, id)` | Database bảo đảm file tồn tại và thuộc đúng thiệp; xoá file thì cột tự về `null`. Đã chạy thử trên PostgreSQL 16 | Để trong JSONB: database không kiểm tra được, dễ trỏ tới file đã xoá hoặc của thiệp khác |

### Quyết định phụ

| Vấn đề | Chọn | Lý do |
| --- | --- | --- |
| Sự kiện lưu ở đâu | Bảng `events`, không nằm trong JSONB | Đây là dữ liệu nghiệp vụ: cần kiểu DATE/TIME, ràng buộc CHECK, và RSVP sau này cần `event_id` để tham chiếu |
| Ngày chính của thiệp | Không lưu cột riêng; lấy ngày sớm nhất trong `events` | Tránh lặp dữ liệu rồi lệch nhau |
| Giờ sự kiện | `event_date` + `start_time` + `end_time` + `timezone` (múi giờ IANA) | Khách cần giờ tại địa điểm, không cần một thời điểm UTC |
| Ngày âm lịch | Hệ thống tự tính khi trả trang public; bỏ trường cho người dùng gõ | Dữ liệu tính được thì không lưu; gõ tay dễ sai |
| Giao diện | `palette_key`, `font_key`, `background_key` chọn từ danh sách template cho phép; `sections` là danh sách section hiển thị theo thứ tự | Tập giá trị cố định, không ra thiệp vỡ bố cục. Màu tự chọn để dành cho gói trả phí |
| Mừng cưới | `bank_bin` theo danh sách ngân hàng của VietQR, số tài khoản dạng chuỗi chữ số; mã QR do template sinh | Không gõ tên ngân hàng tự do, không upload ảnh QR |
| Nhạc nền | Cặp đôi upload file âm thanh (bảng `media`, `kind = audio`) | Dùng lại luồng upload sẵn có. Thư viện nhạc có bản quyền để sau |
| Kiểu dữ liệu ở API | Kiểu chặt: số phải là số JSON, boolean phải là `true`/`false`; không tự đổi `"2"` thành `2` | Một chuẩn duy nhất từ API tới database; chuyển đổi là việc của giao diện |
| Sửa thiệp | `PATCH` theo JSON Merge Patch (RFC 7386), kèm `revision` để chống ghi đè | Không gửi là giữ nguyên, gửi `null` là xoá. Hai tab cùng sửa không đè mất dữ liệu của nhau |
| Định dạng lỗi | Mọi lỗi, kể cả 422, cùng một dạng `{"error": {code, message, details}}` | FE xử lý lỗi ở một chỗ |
| Version nội dung | Cột `content_schema_version` | Nguyên tắc 10 |
| Phiên bản PostgreSQL | Tối thiểu 15 (docker-compose đang dùng 16) | Cú pháp `ON DELETE SET NULL (cột)` có từ bản 15 |

Liên quan: 02-nguyen-tac-va-quy-chuan.md, 03-mo-hinh-du-lieu.md
