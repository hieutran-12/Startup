import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None
    thumbnail_url: str | None
    category: str
    is_premium: bool
    field_schema: dict[str, Any]
