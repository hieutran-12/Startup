"""Danh sách ngân hàng: file tĩnh `banks.json`, nạp và kiểm tra một lần lúc import.

Nguồn: https://api.vietqr.io/v2/banks (lấy ngày 2026-11-06, đủ 76 mục, giữ thứ tự của nguồn).
File sai thì import lỗi, nên app không khởi động. Cách tạo lại file: docs/modules/banks.md.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.errors import error_details
from app.modules.banks.schemas import BankResponse

BANKS_FILE = Path(__file__).with_name("banks.json")


class BankListError(Exception):
    """File danh sách ngân hàng sai. `errors`: [{index, field, code, message}]."""

    def __init__(self, path: Path, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        lines = [
            f"  [{e['index']}] {e['field'] or '(dòng)'}: {e['code']} — {e['message']}"
            if e["index"] is not None
            else f"  {e['code']} — {e['message']}"
            for e in errors
        ]
        super().__init__(f"Danh sách ngân hàng {path} không hợp lệ:\n" + "\n".join(lines))


def _file_error(code: str, message: str) -> dict[str, Any]:
    return {"index": None, "field": "", "code": code, "message": message}


def load_banks(path: Path = BANKS_FILE) -> tuple[BankResponse, ...]:
    """Đọc và kiểm tra file: mảng không rỗng; mỗi dòng đúng 3 trường, đã chuẩn hóa; BIN không trùng.

    Sai thì raise `BankListError` liệt kê mọi lỗi.
    """
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BankListError(path, [_file_error("invalid_format", f"JSON hỏng: {exc}")]) from exc
    if not isinstance(rows, list):
        raise BankListError(path, [_file_error("invalid_format", "Phải là một mảng")])
    if not rows:
        raise BankListError(path, [_file_error("out_of_range", "Cần ít nhất 1 ngân hàng")])

    banks: list[BankResponse] = []
    errors: list[dict[str, Any]] = []
    first_index: dict[str, int] = {}
    for index, row in enumerate(rows):
        try:
            bank = BankResponse.model_validate(row)
        except ValidationError as exc:
            errors += [{"index": index, **d} for d in error_details(exc.errors())]
            continue
        # File phải lưu sẵn dạng đã chuẩn hóa (nguyên tắc 12), không dựa vào lúc nạp để sửa
        unnormalized = [field for field, value in bank.model_dump().items() if value != row[field]]
        errors += [
            {
                "index": index,
                "field": field,
                "code": "invalid_format",
                "message": "Chưa chuẩn hóa (NFC, trim, gộp khoảng trắng)",
            }
            for field in unnormalized
        ]
        if bank.bin in first_index:
            message = f"Bị trùng với ngân hàng [{first_index[bank.bin]}]"
            errors.append(
                {"index": index, "field": "bin", "code": "invalid_format", "message": message}
            )
            continue
        first_index[bank.bin] = index
        banks.append(bank)
    if errors:
        raise BankListError(path, errors)
    return tuple(banks)


_BANKS = load_banks()
_BANK_BINS = frozenset(bank.bin for bank in _BANKS)


def list_banks() -> tuple[BankResponse, ...]:
    """Mọi ngân hàng, theo thứ tự trong file."""
    return _BANKS


def is_known_bin(bank_bin: str) -> bool:
    return bank_bin in _BANK_BINS
