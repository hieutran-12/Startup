"""Schema của module banks: một ngân hàng trong danh sách tĩnh (spec 03 › Nội dung thiệp, gifts)."""

from app.core.schemas import StrictModel
from app.core.types import RequiredDigits, RequiredSingleLine


class BankResponse(StrictModel):
    """Một dòng của `banks.json`, cũng là phần tử của `GET /banks`.

    Kiểu chuẩn hóa dùng để kiểm tra file lúc nạp; độ dài tối đa chỉ là chặn file hỏng, spec không
    quy định.
    """

    bin: RequiredDigits(6, 6)
    short_name: RequiredSingleLine(50)
    name: RequiredSingleLine(200)
