"""Import mọi model để Base.metadata đầy đủ (Alembic autogenerate và test dùng file này)."""

from app.core.db import Base
from app.modules.auth.models import RefreshToken, User
from app.modules.events.models import Event
from app.modules.invitations.models import Invitation
from app.modules.media.models import Album, Media
from app.modules.templates.models import Template

__all__ = ["Album", "Base", "Event", "Invitation", "Media", "RefreshToken", "Template", "User"]
