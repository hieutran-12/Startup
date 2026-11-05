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
Liên quan: 01-quyet-dinh.md, 03-mo-hinh-du-lieu.md
