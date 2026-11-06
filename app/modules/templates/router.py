from fastapi import APIRouter

from app.core.deps import DbSession
from app.modules.templates import service
from app.modules.templates.schemas import TemplateResponse

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateResponse])
async def list_templates(db: DbSession, category: str | None = None) -> list[TemplateResponse]:
    templates = await service.list_active(db, category)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.get("/{key}", response_model=TemplateResponse)
async def get_template(key: str, db: DbSession) -> TemplateResponse:
    return TemplateResponse.model_validate(await service.get_by_key(db, key))
