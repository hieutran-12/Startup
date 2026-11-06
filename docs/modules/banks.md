# banks

## Mục đích
Danh sách ngân hàng tĩnh (bin, short_name, name) cho dropdown mục mừng cưới và để kiểm tra `content.gifts[].bank_bin`. Không có bảng, không migration (Bước 8).

## File code chính
- `app/modules/banks/banks.json`: 76 ngân hàng, mỗi dòng một object `{"bin", "short_name", "name"}`
- `app/modules/banks/schemas.py`: `BankResponse` (`RequiredDigits(6, 6)`, `RequiredSingleLine(50)`, `RequiredSingleLine(200)`): kiểm tra dòng của file và là phần tử của `GET /banks`. Độ dài tối đa chỉ để chặn file hỏng, spec không quy định
- `app/modules/banks/service.py`: nạp và kiểm tra file một lần lúc import
- `app/modules/banks/router.py`: `GET /banks`

## API công khai
- `GET /banks`: không cần đăng nhập, trả mảng `[{bin, short_name, name}]` theo thứ tự trong file. Không tham số, không Cache-Control/ETag
- `list_banks()` → `tuple[BankResponse, ...]`; `is_known_bin(bank_bin)` → bool
- `load_banks(path=BANKS_FILE)`: sai thì raise `BankListError` (`errors`: `[{index, field, code, message}]`, `index` null khi lỗi cả file). Từ chối: JSON hỏng, không phải mảng, mảng rỗng (`out_of_range`), dòng sai kiểu/thiếu/thừa trường, giá trị chưa chuẩn hóa (NFC, trim, gộp khoảng trắng → `invalid_format`), BIN trùng (`invalid_format` tại dòng sau). File sai thì import lỗi nên app không khởi động

## Phụ thuộc
- Dùng: core (`StrictModel`, `RequiredDigits`, `RequiredSingleLine`, `error_details`)
- Được dùng bởi: invitations (`Gift._bank_in_list` gọi `is_known_bin`), `app/main.py`

## Quy tắc spec đang áp dụng
- File tĩnh lấy từ danh sách công khai của VietQR, trả qua `GET /banks`; `bank_bin` phải có trong danh sách → `docs/spec/03-mo-hinh-du-lieu.md` › Nội dung thiệp (gifts); `docs/spec/05-api.md` › Endpoint mới
- BIN 6 chữ số, số tài khoản 6–19 chữ số, đều là chuỗi → 02 › Mã định danh toàn chữ số; nguyên tắc 12, 14

## Quy tắc phụ chốt ở Bước 8 (người dùng duyệt 9 đề xuất, 2026-11-06)
1. Module `app/modules/banks/` (không có `models.py`).
2. Lấy đủ 76 mục của VietQR, gồm ví điện tử (MoMo, ZaloPay, ViettelMoney, VNPTMoney), MAFC, chi nhánh ngân hàng nước ngoài. Không lọc theo `transferSupported` (48/76 có cờ này; HSBC, Standard Chartered, Citibank… có cờ 0).
3. Chỉ giữ `bin`, `short_name` (từ `shortName`), `name`. Chuỗi chuẩn hóa như `SingleLine` lúc tạo file; `short_name` giữ cách viết của nguồn (`VietCapitalBank`, `BacABank`).
4. Thứ tự giữ như nguồn (VietinBank, Vietcombank, BIDV, Agribank…).
5. `GET /banks` không cần đăng nhập, như `GET /templates`.
6. BIN đúng dạng mà không có trong danh sách → 422 `validation_error`, `content.gifts[i].bank_bin`, `invalid_choice`, "Không có ngân hàng với mã BIN này". Sai dạng chỉ báo `invalid_format`.
7. Kiểm tra mỗi lần content được kiểm tra theo request (POST, PATCH có `content` hoặc đổi template), cả danh sách `gifts` sau khi gộp, cùng lượt với lỗi schema. Đọc content đã lưu (response, trang public) không kiểm tra.
8. Số tài khoản: giữ quy tắc Bước 4 (`RequiredDigits(6, 19)`, chỉ `0-9` ASCII, trim hai đầu), chỉ thêm test API.
9. Không có script tải lại trong repo (xem cách tạo lại bên dưới).

## Tạo lại file từ nguồn
Nguồn: `https://api.vietqr.io/v2/banks`, lấy ngày 2026-11-06 (`desc`: "Total 76 banks", BIN không trùng, `shortName` = `short_name` ở mọi dòng). Cách chuyển: lấy mảng `data`, mỗi dòng `{"bin": bin, "short_name": shortName, "name": name}`, chạy qua `BankResponse.model_validate(...).model_dump()` để chuẩn hóa, giữ thứ tự, ghi UTF-8 (`ensure_ascii=False`), mỗi object một dòng. Lần lấy này chuẩn hóa 8 tên: 7 tên NFD (Vietcombank, VietCapitalBank, VIB, PVcomBank, SeABank, IBKHN, IBKHCM), MAFC có dấu cách cuối. Lấy lại xong thì sửa số dòng và các dòng mẫu trong `tests/test_banks.py`.

## Lưu ý
- Bỏ một BIN khỏi file: thiệp đã lưu BIN đó vẫn đọc được; lần sửa content kế tiếp (kể cả sửa `greeting`, đổi template) bị 422 tại gift đó tới khi sửa. PATCH không có `content` (chỉ `title`, `slug`, media) không bị ảnh hưởng.
- `Gift._bank_in_list` coi "có context" là validate request; chỗ nào validate content của request phải truyền context (hiện chỉ `_parse_content`).
- Test: `tests/test_banks.py` (file, loader, `GET /banks`, gifts qua API, số tài khoản), `tests/test_invitation_content.py` (schema).
