import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl

from app.modules.invitations.slugs import slug_error

ShortText = Annotated[str | None, Field(max_length=200)]


# ---------- Nội dung thiệp (lưu trong cột JSONB `content`) ----------


class Person(BaseModel):
    full_name: ShortText = None
    short_name: str | None = Field(default=None, max_length=60)  # tên gọi trên thiệp: "Nam"
    father_name: ShortText = None
    mother_name: ShortText = None
    hometown: ShortText = None


class Couple(BaseModel):
    groom: Person = Field(default_factory=Person)
    bride: Person = Field(default_factory=Person)


class Event(BaseModel):
    kind: Literal["engagement", "ceremony", "reception", "other"] = "ceremony"
    title: ShortText = None  # "Lễ vu quy", "Tiệc cưới nhà trai"...
    starts_at: datetime | None = None
    lunar_date_text: str | None = Field(
        default=None, max_length=100
    )  # "Tức ngày 15 tháng 10 năm Bính Ngọ"
    venue_name: ShortText = None
    address: str | None = Field(default=None, max_length=500)
    map_url: HttpUrl | None = None


class BankAccount(BaseModel):
    owner: Literal["groom", "bride", "other"] = "other"
    bank_name: str = Field(max_length=100)
    account_number: str = Field(max_length=50)
    account_holder: str = Field(max_length=120)
    qr_media_id: uuid.UUID | None = None


class InvitationContent(BaseModel):
    # Cho phép thêm trường riêng của từng template mà không phải sửa backend
    model_config = ConfigDict(extra="allow")

    couple: Couple = Field(default_factory=Couple)
    greeting: str | None = Field(default=None, max_length=2000)  # lời ngỏ
    love_story: str | None = Field(default=None, max_length=10000)
    events: list[Event] = Field(default_factory=list, max_length=10)
    cover_media_id: uuid.UUID | None = None
    music_url: HttpUrl | None = None
    bank_accounts: list[BankAccount] = Field(default_factory=list, max_length=6)
    theme: dict[str, str] = Field(default_factory=dict, max_length=20)


# ---------- Request / response ----------


def _validate_slug(value: str) -> str:
    value = value.strip().lower()
    if reason := slug_error(value):
        raise ValueError(reason)
    return value


Slug = Annotated[str, AfterValidator(_validate_slug)]


class InvitationCreate(BaseModel):
    template_key: str = Field(max_length=64)
    title: str | None = Field(default=None, max_length=120)
    slug: Slug | None = None  # bỏ trống thì hệ thống tự sinh từ tên cô dâu chú rể
    content: InvitationContent = Field(default_factory=InvitationContent)


class InvitationUpdate(BaseModel):
    """PATCH: chỉ các trường được gửi lên mới bị thay đổi. `content` được thay thế toàn bộ."""

    template_key: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    slug: Slug | None = None
    content: InvitationContent | None = None


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    status: str
    template_key: str
    content: dict[str, Any]
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SlugAvailability(BaseModel):
    slug: str
    available: bool
    reason: str | None = None


class PublicAlbum(BaseModel):
    id: uuid.UUID
    title: str
    position: int


class PublicMedia(BaseModel):
    id: uuid.UUID
    album_id: uuid.UUID | None
    url: str
    width: int | None
    height: int | None


class PublicInvitationOut(BaseModel):
    slug: str
    template_key: str
    content: dict[str, Any]
    published_at: datetime | None
    updated_at: datetime
    albums: list[PublicAlbum]
    media: list[PublicMedia]
