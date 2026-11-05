from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base model cho schema request (spec 02 › Quy tắc trên API).

    - strict=True: số và boolean không nhận chuỗi ("2", "02", "true" bị từ chối).
    - extra="forbid": trường không có trong schema trả 422, mã `unknown_field`.

    Chuỗi phải khai báo bằng kiểu trong app/core/types.py để được trim và chuẩn hóa NFC.
    UUID, ngày, giờ và enum cũng dùng kiểu ở đó (Uuid, IsoDate, LocalTime, Choice), vì strict
    ở chế độ Python từ chối các giá trị này khi chúng ở dạng chuỗi.
    """

    model_config = ConfigDict(strict=True, extra="forbid")
