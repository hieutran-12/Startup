from fastapi import APIRouter

from app.modules.banks import service
from app.modules.banks.schemas import BankResponse

router = APIRouter(prefix="/banks", tags=["banks"])


@router.get("", response_model=list[BankResponse])
async def list_banks() -> list[BankResponse]:
    """Danh sách ngân hàng cho dropdown ở mục mừng cưới. Không cần đăng nhập."""
    return list(service.list_banks())
