## Kế hoạch triển khai

Giao cho Claude Code từng bước một, theo đúng thứ tự dưới đây. Bước nào cũng phải có test và qua `uv run pytest` cùng `uv run ruff check .` trước khi commit. Bước 0 làm trước hết, vì khung hiện tại chưa từng được chạy.

| Bước | Việc cần làm | Tiêu chí nghiệm thu | Đọc |
| --- | --- | --- | --- |
| 0 | Chạy khung hiện tại: `docker compose up -d`, `uv sync`, `alembic upgrade head`, `pytest`; sửa lỗi nếu có | 28 test hiện có đều qua; app khởi động được và `/docs` mở được | 01-quyet-dinh.md |
| 1 | Tầng chuẩn hóa: `app/core/types.py` (văn bản một dòng, nhiều dòng, chuỗi chữ số, giờ `HH:MM`, múi giờ), base model strict với `extra="forbid"`, handler lỗi 422 theo định dạng chung | Test: chuỗi NFD lưu ra NFC; `""` thành `null`; `"2"` bị từ chối ở trường số; trường lạ trả `unknown_field`; lỗi 422 có `details` đúng đường dẫn | 02-nguyen-tac-va-quy-chuan.md, 04-nghiep-vu.md (Chuẩn hóa chuỗi), 05-api.md (Định dạng lỗi) |
| 2 | Viết lại model và migration `0001` theo mục Mô hình dữ liệu, kể cả khóa ngoại kép và các `CHECK` | `alembic upgrade head` chạy trên PostgreSQL 16; `alembic revision --autogenerate` không sinh thay đổi nào; test database: gắn ảnh của thiệp khác bị từ chối, xoá ảnh thì cột về `null`, xoá thiệp không lỗi | 03-mo-hinh-du-lieu.md, 02-nguyen-tac-va-quy-chuan.md, 01-quyet-dinh.md |
| 3 | Manifest template: schema `TemplateManifest`, seed lại 4 mẫu với key snake_case | Seed chạy lại nhiều lần vẫn đúng; manifest sai cấu trúc thì seed báo lỗi; `GET /templates` trả manifest | 03-mo-hinh-du-lieu.md (templates, appearance), 02-nguyen-tac-va-quy-chuan.md (Quy ước đặt tên) |
| 4 | Schema `content` v1; tạo thiệp với nội dung mặc định; `PATCH` theo Merge Patch, `revision`, `ETag`, `If-Match`; quy tắc đổi template; kiểm tra tham chiếu media | Test: không gửi trường thì giữ nguyên, gửi `null` thì xoá, danh sách bị thay nguyên; thiếu `If-Match` trả 428, sai revision trả 409; đổi template thì key giao diện không hợp lệ về `null`; hai request tạo thiệp đồng thời không vượt giới hạn 5 | 03-mo-hinh-du-lieu.md (invitations, Nội dung thiệp), 04-nghiep-vu.md (Tạo thiệp, Sửa thiệp, Đổi template, Tham chiếu media), 05-api.md, 02-nguyen-tac-va-quy-chuan.md (NULL, rỗng và mặc định) |
| 5 | Module `events`: CRUD, tên mặc định, thứ tự, giới hạn 10, `If-Match` | Test mọi `CHECK` (lễ gia tiên không nhận `both`, `other` bắt buộc có tên, giờ kết thúc sau giờ bắt đầu, tọa độ đủ cặp); bảng tên mặc định đúng từng ô | 03-mo-hinh-du-lieu.md (events), 04-nghiep-vu.md (Sự kiện, Sửa thiệp), 05-api.md |
| 6 | Quy tắc publish và `breaks_published_invitation` | Test từng điều kiện thiếu xuất hiện trong `details`; sửa thiệp đã publish mà xoá tên cô dâu thì bị từ chối | 04-nghiep-vu.md (Publish), 03-mo-hinh-du-lieu.md (Nội dung thiệp, events), 05-api.md (Định dạng lỗi) |
| 7 | Media: cột `kind`, file âm thanh, giới hạn theo loại, xoá file thì dọn tham chiếu trong `love_story` | Test: upload mp3 cho `music_media_id` được, gán ảnh vào `music_media_id` bị từ chối; xoá ảnh đang dùng ở `love_story` thì `media_id` ở đó về `null` | 03-mo-hinh-du-lieu.md (invitations, media), 04-nghiep-vu.md (Tham chiếu media), 05-api.md |
| 8 | Danh sách ngân hàng: file tĩnh, `GET /banks`, kiểm tra `gifts` | `bank_bin` không có trong danh sách bị từ chối; số tài khoản có chữ hoặc khoảng trắng bị từ chối | 03-mo-hinh-du-lieu.md (gifts), 05-api.md (GET /banks), 02-nguyen-tac-va-quy-chuan.md (Mã định danh toàn chữ số) |
| 9 | Âm lịch: `app/core/lunar.py` theo lịch Việt Nam UTC+7 | Test ngày 21/01/1985 là mùng 1 tháng Giêng năm Ất Sửu; thêm ít nhất 5 ngày đối chiếu với lịch vạn niên Việt Nam, trong đó có một ngày thuộc tháng nhuận | 04-nghiep-vu.md (Ngày âm lịch), 07-ngoai-pham-vi.md (Nguồn) |
| 10 | Response public mới: lọc theo `side`, `display_name`, `lunar_date`, `media_by_id` | Test: `?side=bride` không trả sự kiện hay tài khoản của nhà trai; response không có `owner_id` | 05-api.md (Response của trang public), 04-nghiep-vu.md (Link theo bên, Sự kiện, Ngày âm lịch), 03-mo-hinh-du-lieu.md |
| 11 | Cập nhật README theo đặc tả; xoá code và test không còn dùng | Toàn bộ test qua, ruff sạch, README không còn nhắc tới `event_date` của thiệp, `theme` hay `lunar_date_text` | 01-quyet-dinh.md, 03-mo-hinh-du-lieu.md, 05-api.md |

Mẫu câu giao việc cho từng bước:

```text
Làm Bước <số> trong docs/spec/06-ke-hoach.md, không làm sang bước khác. Đọc các file ghi ở cột "Đọc" của bước đó.
Viết test theo "Tiêu chí nghiệm thu" trước, rồi mới viết code cho test qua.
Chỗ nào đặc tả chưa quy định thì dừng lại và hỏi tôi, không tự quyết.
Xong thì chạy uv run pytest và uv run ruff check ., báo kết quả, rồi commit.
```

Liên quan: 01-quyet-dinh.md; từng bước đọc thêm các file ghi ở cột "Đọc" của bước đó
