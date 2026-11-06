"""JSON Merge Patch (RFC 7386) theo quy ước null của spec.

Spec: 04 › Sửa thiệp (object gộp đệ quy, danh sách bị thay nguyên); 02 › NULL, rỗng và mặc định.
Khác RFC ở một điểm: null không xoá key mà là "không có giá trị". Giá trị cũ là danh sách thì
thành [], còn lại thành None; schema kiểm tra sau đó trả `required` cho trường không nhận null
(boolean, nhóm object). Nhờ vậy kết quả luôn đủ key để kiểm tra lại toàn bộ.
"""

from typing import Any


def merge_patch(target: Any, patch: Any) -> Any:
    """Gộp `patch` vào `target`, trả object mới (không sửa `target`)."""
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result[key] = [] if isinstance(result.get(key), list) else None
        else:
            result[key] = merge_patch(result.get(key), value)
    return result
