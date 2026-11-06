## Quy tắc nghiệp vụ và validation

Mọi lần ghi đều chạy theo thứ tự: chuẩn hóa chuỗi, kiểm tra schema, kiểm tra quy tắc nghiệp vụ, rồi mới lưu. Thiệp đã publish còn phải luôn thỏa điều kiện publish sau mỗi lần sửa.

### Chuẩn hóa chuỗi

Viết thành các kiểu `Annotated` dùng lại được (ví dụ `SingleLine(max_length)`, `MultiLine(max_length)` và bản bắt buộc của chúng), áp dụng theo thứ tự:

1. Chuẩn hóa Unicode về NFC.
2. Trim hai đầu.
3. Văn bản một dòng: gộp khoảng trắng liên tiếp thành một; có xuống dòng hoặc ký tự điều khiển thì trả lỗi `invalid_characters`.
4. Văn bản nhiều dòng: đổi `\r\n` và `\r` thành `\n`, giữ tối đa 2 dòng trống liền nhau.
5. Rỗng: trường không bắt buộc thì thành `null`, trường bắt buộc thì trả lỗi `required`.
6. Kiểm tra độ dài, đếm bằng số ký tự sau khi đã chuẩn hóa.

### Tạo thiệp

- Tối đa 5 thiệp mỗi tài khoản. Khóa dòng `users` của chủ thiệp bằng `SELECT … FOR UPDATE` trước khi đếm, để hai request đồng thời không vượt giới hạn.
- Template phải đang hoạt động và không phải premium.
- Slug giữ nguyên quy tắc của khung hiện tại: tự sinh từ tên nếu không nhập, bỏ dấu tiếng Việt, thêm hậu tố khi trùng, chặn danh sách slug dành riêng.
- `content` khởi tạo là object v1 đầy đủ, với `appearance.sections` lấy từ `manifest.default_sections`. `content_schema_version = 1`, `revision = 1`.

### Sửa thiệp

- `PATCH /invitations/{invitation_id}` nhận body dạng JSON Merge Patch (RFC 7386) cho các trường `title`, `slug`, `template_key`, `content` và bốn cột `*_media_id`.
- Cách gộp: object được gộp đệ quy, danh sách bị thay nguyên, `null` nghĩa là "không có giá trị" theo bảng NULL ở mục Quy chuẩn dữ liệu. Gộp xong thì kiểm tra lại toàn bộ `content`.
- Chống ghi đè: response của thiệp có header `ETag: "<revision>"`. Mọi `PATCH` thiệp và mọi thao tác ghi sự kiện phải gửi `If-Match: "<revision>"`. Thiếu header thì trả 428 `revision_required`; khác revision hiện tại thì trả 409 `revision_conflict` kèm revision mới nhất.
- `revision` tăng khi `content`, sự kiện, `title`, `slug`, template hoặc cột `*_media_id` thay đổi. Thao tác trên album và thư viện ảnh không làm tăng `revision`.

### Đổi template

Khi `template_key` đổi, nội dung được giữ và chỉ phần giao diện được điều chỉnh, không trả lỗi:

- `palette_key`, `font_key`, `background_key` không có trong manifest mới thì về `null`.
- `sections` giữ các section template mới hỗ trợ, đúng thứ tự cũ. Nếu không còn section nào thì lấy `manifest.default_sections` của template mới.

### Sự kiện

- Tối đa 10 sự kiện mỗi thiệp.
- Thứ tự hiển thị: `event_date`, rồi `start_time`, rồi `position`. Sự kiện chưa có ngày xếp cuối.
- `timezone` phải là tên có trong cơ sở dữ liệu múi giờ IANA (kiểm tra bằng `zoneinfo`).
- Tên mặc định khi `event_name` là `null`:

| `event_type` | `groom` | `bride` | `both` |
| --- | --- | --- | --- |
| `engagement` | Lễ ăn hỏi | Lễ ăn hỏi | Lễ ăn hỏi |
| `family_ceremony` | Lễ thành hôn | Lễ vu quy | Không hợp lệ |
| `religious_ceremony` | Lễ cưới | Lễ cưới | Lễ cưới |
| `reception` | Tiệc cưới nhà trai | Tiệc cưới nhà gái | Tiệc cưới |
| `other` | Bắt buộc có `event_name` | Bắt buộc có `event_name` | Bắt buộc có `event_name` |

### Link theo bên

- `GET /public/invitations/{slug}` không có tham số thì trả mọi sự kiện và mọi tài khoản mừng cưới.
- Khi có `?side=groom` hoặc `?side=bride`: chỉ trả sự kiện có `host_side` bằng bên đó hoặc `both`, và tài khoản mừng cưới có `recipient_side` bằng bên đó. Response có trường `side` để template chọn câu báo hỷ và thứ tự hai gia đình.
- Next.js có ba đường dẫn cho mỗi thiệp: `/{slug}`, `/{slug}/nha-trai`, `/{slug}/nha-gai`. Webhook revalidate gửi slug, route phía Next.js tự build lại cả ba.

### Publish

Publish thành công khi đủ các điều kiện sau. Thiếu điều kiện nào thì trả 400 `not_ready_to_publish`, trong `details` liệt kê đường dẫn từng trường còn thiếu.

- Có `couple.groom.full_name` và `couple.bride.full_name`.
- Có ít nhất một sự kiện, và sự kiện nào cũng có `event_date`, `start_time`, `address`.
- `appearance.sections` có `cover` và `events`.

Sau khi publish, mọi lần sửa cũng phải giữ đủ các điều kiện trên, nếu không thì trả 400 `breaks_published_invitation`. Thay đổi trên thiệp đã publish hiện ngay cho khách (v1 chưa tách bản nháp khỏi bản đã đăng).

### Tham chiếu media

- Ba cột ảnh nhận file `kind = image`; `music_media_id` nhận file `kind = audio`. File phải ở trạng thái `ready`. Việc file thuộc đúng thiệp đã được khóa ngoại kép bảo đảm.
- `love_story[].media_id` không có khóa ngoại, nên service tự kiểm tra: ảnh, `ready`, thuộc chính thiệp.
- Khi xoá một file: database tự đưa các cột `*_media_id` về `null`; service xóa `media_id` đó khỏi `love_story` trong cùng transaction. Nếu file đó đang được thiệp tham chiếu, ở cột hoặc trong love_story, thì tăng `revision`.

### Ngày âm lịch

- Response public trả kèm mỗi sự kiện có ngày một object `lunar_date` gồm `day`, `month`, `year`, `is_leap_month` và `year_name` (ví dụ "Bính Ngọ"). Giá trị này tính khi trả về, không lưu.
- Phải tính theo lịch Việt Nam dùng múi giờ UTC+7. Không dùng thư viện âm lịch Trung Quốc, vì lịch Trung Quốc tính theo UTC+8 và có năm lệch cả tháng.
- Test bắt buộc: ngày 21/01/1985 là mùng 1 Tết Ất Sửu theo lịch Việt Nam, trong khi Tết theo lịch Trung Quốc năm đó là 20/02/1985 ([nguồn](https://www.wikiwand.com/en/articles/Vietnamese_calendar)).

Liên quan: 03-mo-hinh-du-lieu.md, 05-api.md, 02-nguyen-tac-va-quy-chuan.md
