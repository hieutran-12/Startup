## Nguyên tắc bắt buộc

Mọi thay đổi code phải thỏa 14 nguyên tắc dưới đây. Nguyên tắc 1–10 là bộ gốc, 11–14 là phần bổ sung.

1. Một trường dữ liệu chỉ mang một ý nghĩa.
2. Một trường dữ liệu chỉ có một kiểu dữ liệu chuẩn.
3. Không lưu đơn vị đo trong giá trị số. Đơn vị nằm trong tên trường: `size_bytes`, `amount_vnd`.
4. Không dùng chuỗi tự do cho dữ liệu có tập giá trị xác định.
5. Tách dữ liệu nghiệp vụ khỏi dữ liệu hiển thị. Dữ liệu cần truy vấn, ràng buộc hoặc được nơi khác tham chiếu thì là cột hoặc bảng; dữ liệu chỉ để hiển thị thì nằm trong JSONB có schema.
6. Không lặp dữ liệu. Dữ liệu tính được (số ảnh trong album, ngày âm lịch, ngày chính của thiệp) thì tính khi trả về, không lưu.
7. Quy định rõ `NULL`, `DEFAULT` và `NOT NULL` cho từng cột và từng trường JSON.
8. Validation hai tầng. Database giữ kiểu, `NOT NULL`, `UNIQUE`, khóa ngoại và `CHECK` trên cột thường. Tầng API giữ schema của JSONB và các quy tắc nghiệp vụ.
9. Thống nhất quy ước đặt tên trên toàn dự án.
10. Dữ liệu có cấu trúc linh hoạt phải có số version.
11. API không đoán ý người dùng. Dữ liệu sai chuẩn thì từ chối kèm mã lỗi rõ ràng, không tự sửa.
12. Mọi chuỗi đều được trim và chuẩn hóa Unicode về dạng NFC trước khi lưu.
13. Tham chiếu tới tài nguyên khác bằng ID, không sao chép URL hay tên của tài nguyên đó.
14. Mã định danh gồm toàn chữ số (số tài khoản, mã ngân hàng, số điện thoại) là chuỗi, không phải số nguyên, vì số 0 ở đầu có ý nghĩa và không ai cộng trừ chúng.

## Quy chuẩn dữ liệu

Mỗi loại dữ liệu có đúng một kiểu lưu trong database và một định dạng trên API. Giao diện có thể linh hoạt, nhưng dữ liệu gửi lên API phải đúng chuẩn này.

### Kiểu dữ liệu

| Loại | Kiểu PostgreSQL | Định dạng trên API | Quy tắc |
| --- | --- | --- | --- |
| ID | `UUID` | Chuỗi UUID chữ thường | Backend sinh, client không gửi |
| Văn bản một dòng (tên, địa điểm) | `VARCHAR(n)` | Chuỗi | Trim, NFC, gộp khoảng trắng liên tiếp thành một; không chứa xuống dòng hay ký tự điều khiển |
| Văn bản nhiều dòng (lời ngỏ, câu chuyện) | `TEXT` | Chuỗi | Trim hai đầu, NFC, đổi `\r\n` thành `\n`, tối đa 2 dòng trống liền nhau |
| Email | `VARCHAR(320)` | Chuỗi | Trim, chữ thường, kiểm tra định dạng |
| Số lượng | `INTEGER` | Số nguyên JSON | Không nhận chuỗi; ≥ 0 trừ khi quy định khác |
| Tiền | `BIGINT` | Số nguyên JSON | Đơn vị là đồng, tên trường có hậu tố `_vnd`. Cần nhiều loại tiền thì thêm cột `currency` (ISO 4217) |
| Phần trăm | `NUMERIC(5,2)` | Số JSON | Không dùng `FLOAT` |
| Ngày | `DATE` | `"YYYY-MM-DD"` |  |
| Giờ địa phương của sự kiện | `TIME(0)` | `"HH:MM"`, 24 giờ | Luôn đi kèm `timezone` của sự kiện |
| Thời điểm hệ thống ghi nhận | `TIMESTAMPTZ` | ISO 8601 theo UTC, ví dụ `"2026-11-05T06:30:00Z"` | Dùng cho `created_at`, `published_at`… |
| Múi giờ | `VARCHAR(64)` | Tên IANA, ví dụ `"Asia/Ho_Chi_Minh"` | Phải nằm trong cơ sở dữ liệu múi giờ IANA |
| Trạng thái, loại | `VARCHAR` + `CHECK` | Chuỗi snake_case chữ thường | Tập giá trị cố định, khai báo bằng `StrEnum` trong code |
| Boolean | `BOOLEAN NOT NULL` | `true`/`false` | Không bao giờ `null`, luôn có mặc định. Tên bắt đầu bằng `is_` hoặc `has_` |
| URL | `VARCHAR(2048)` | Chuỗi | Chỉ `http` hoặc `https` |
| Kích thước file | `BIGINT` | Số nguyên JSON | Đơn vị byte, tên trường có hậu tố `_bytes` |
| Thứ tự hiển thị | `INTEGER` | Số nguyên JSON | Bắt đầu từ 0, liên tục sau mỗi lần sắp xếp |
| Tọa độ | `NUMERIC(9,6)` | Số JSON | `latitude` trong [-90, 90], `longitude` trong [-180, 180]; có cả hai hoặc không có cái nào |
| Số điện thoại | `VARCHAR(16)` | Chuỗi E.164, ví dụ `"+84912345678"` | Giao diện đổi `0912 345 678` sang E.164 trước khi gửi |
| Mã định danh toàn chữ số | `VARCHAR(n)` | Chuỗi chỉ gồm `0-9` | Số tài khoản 6–19 chữ số, BIN ngân hàng 6 chữ số |
| Nội dung linh hoạt | `JSONB NOT NULL` | Object | Có schema kiểm tra và `content_schema_version` |

### NULL, rỗng và mặc định

| Loại trường | "Không có giá trị" được biểu diễn là | Ghi chú |
| --- | --- | --- |
| Văn bản không bắt buộc | `null` | Chuỗi rỗng hoặc chỉ có khoảng trắng thì lưu `null` |
| Văn bản bắt buộc | Không được thiếu | Rỗng sau khi trim thì trả 422, mã `required` |
| Số | `null` là chưa biết, `0` là bằng không | Không tự đổi qua lại giữa hai giá trị |
| Boolean | Luôn `true` hoặc `false` | Gửi `null` thì trả 422 |
| Danh sách | `[]` | Không bao giờ `null`; trong `PATCH`, gửi `null` cho danh sách nghĩa là đặt về `[]` |
| Nhóm object (`couple`, `groom`, `father`…) | Luôn có mặt | Các trường con có thể là `null` |

Không lưu chữ thay cho giá trị rỗng như "Không có", "N/A" hay "-". Giao diện để trống ô thì gửi `null`.

### Quy tắc trên API

- **Kiểu chặt:** số và boolean dùng chế độ strict của Pydantic. `"2"`, `"02"`, `"2 người"`, `"true"` đều bị từ chối.
- **Ngày giờ** chỉ nhận đúng định dạng ở bảng trên. Không nhận `"20/12/2026"` hay `"11h"`.
- **Trường lạ:** mọi schema đặt `extra="forbid"`. Gửi trường không có trong đặc tả thì trả 422, mã `unknown_field`.
- **Response đầy đủ:** response luôn trả mọi trường đã khai báo, kể cả trường có giá trị `null`, để FE không phải phân biệt "thiếu" với "rỗng".
- **Không tự đổi chữ hoa thường** của tên người hay địa danh. Chỉ email, slug và giá trị enum được chuẩn hóa về chữ thường.

## Quy ước đặt tên

Toàn dự án dùng snake_case, trừ tên class (PascalCase), đường dẫn URL nhiều từ (kebab-case) và biến môi trường (UPPER_SNAKE_CASE).

| Thành phần | Quy ước | Ví dụ |
| --- | --- | --- |
| Bảng database | snake_case, số nhiều | `invitations`, `events` |
| Cột | snake_case | `created_at` |
| Khóa ngoại | `<danh từ số ít>_id` | `invitation_id`, `cover_media_id` |
| Constraint, index | Tiền tố `pk_`, `uq_`, `fk_`, `ck_`, `ix_` theo naming convention đã có trong `app/core/db.py` | `ck_events_event_type_valid` |
| Biến, hàm Python | snake_case | `create_invitation()` |
| Class Python | PascalCase | `Invitation` |
| Schema Pydantic | PascalCase + hậu tố theo vai trò: `Create`, `Update`, `Response` | `InvitationCreate`, `InvitationResponse` (thay cho hậu tố `Out` hiện có) |
| Service | Hàm trong `service.py` của từng module, không viết thành class | `invitations.service.publish(db, owner, invitation_id)` |
| Endpoint | Chữ thường, danh từ số nhiều; nhiều từ thì dùng kebab-case | `/invitations/{invitation_id}/events`, `/media/upload-url` |
| Hành động nghiệp vụ không phải CRUD | `POST` với động từ đặt sau tài nguyên | `POST /invitations/{invitation_id}/publish` |
| Query param, key JSON | snake_case | `album_id`, `event_date` |
| Giá trị enum, key của template, palette, font | snake_case chữ thường | `family_ceremony`, `classic_01`, `ivory_gold` |
| Mã lỗi | snake_case | `slug_taken` |
| Biến môi trường | UPPER_SNAKE_CASE | `DATABASE_URL` |

Hậu tố của tên trường cho biết kiểu dữ liệu:

- `_at` là `TIMESTAMPTZ`, `_date` là `DATE`, `_time` là `TIME`.
- `_id` là khóa, `_count` là số đếm, `_bytes` là dung lượng, `_vnd` là tiền.
- Boolean bắt đầu bằng `is_` hoặc `has_`.

Key của template đổi từ kebab-case sang snake_case (`classic-01` thành `classic_01`) để cùng quy ước với các key khác. Slug của thiệp vẫn là kebab-case vì nằm trên URL.

Liên quan: 03-mo-hinh-du-lieu.md, 04-nghiep-vu.md
