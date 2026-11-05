from fastapi import APIRouter

from app.core.deps import DbSession
from app.modules.templates import service
from app.modules.templates.schemas import TemplateOut

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
async def list_templates(db: DbSession, category: str | None = None) -> list[TemplateOut]:
    templates = await service.list_active(db, category)
    return [TemplateOut.model_validate(t) for t in templates]


@router.get("/{key}", response_model=TemplateOut)
async def get_template(key: str, db: DbSession) -> TemplateOut:
    return TemplateOut.model_validate(await service.get_by_key(db, key))
