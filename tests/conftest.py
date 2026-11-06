import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ["APP_ENV"] = "test"

ROOT = Path(__file__).resolve().parent.parent

from app.core.config import settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.storage import ObjectInfo, get_storage  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base, Template  # noqa: E402

TEST_DATABASE_URL = (
    settings.test_database_url
    or "postgresql+asyncpg://thiepcuoi:thiepcuoi@localhost:5432/thiepcuoi_test"
)

# Chặn trường hợp lỡ trỏ test vào database đang dùng để dev (test sẽ TRUNCATE mọi bảng)
if settings.database_url == TEST_DATABASE_URL or "test" not in TEST_DATABASE_URL.rsplit("/", 1)[-1]:
    raise RuntimeError("TEST_DATABASE_URL phải trỏ tới database riêng có chữ 'test' trong tên")


class FakeStorage:
    """Giả lập S3/R2 trong bộ nhớ."""

    def __init__(self) -> None:
        self.objects: dict[str, ObjectInfo] = {}
        self.deleted: list[str] = []

    def presign_put(self, key: str, content_type: str) -> str:
        return f"https://storage.test/{key}?X-Amz-Signature=fake"

    async def head(self, key: str) -> ObjectInfo | None:
        return self.objects.get(key)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)

    def public_url(self, key: str) -> str:
        return f"https://cdn.test/{key}"

    # Dùng trong test: giả vờ trình duyệt đã PUT file lên upload_url
    def simulate_upload(self, upload_url: str, size_bytes: int, content_type: str) -> str:
        key = upload_url.removeprefix("https://storage.test/").split("?", 1)[0]
        self.objects[key] = ObjectInfo(size_bytes=size_bytes, content_type=content_type)
        return key


def _upgrade_to_head(connection: Connection) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    # env.py chạy migration trên connection này thay vì tự mở kết nối tới DATABASE_URL
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> None:
    """Dựng schema bằng migration (không dùng create_all) để test kiểm tra luôn migration 0001."""

    async def run() -> None:
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.run_sync(_upgrade_to_head)
        await engine.dispose()

    asyncio.run(run())


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
def session_maker(db_engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)


def make_manifest(**overrides: Any) -> dict[str, Any]:
    """Manifest hợp lệ, nhỏ gọn (schema TemplateManifest). Trả bản mới mỗi lần gọi."""
    manifest: dict[str, Any] = {
        "sections": ["cover", "greeting", "couple", "events", "gallery"],
        "default_sections": ["cover", "couple", "events"],
        "palettes": [
            {
                "key": "ivory_gold",
                "name": "Ngà – vàng đồng",
                "primary": "#B08D57",
                "secondary": "#E8DCC4",
                "background": "#FBF7EF",
                "text": "#3A2E22",
            },
            {
                "key": "burgundy",
                "name": "Đỏ rượu vang",
                "primary": "#A3485A",
                "secondary": "#E9C9CF",
                "background": "#FCF6F4",
                "text": "#3B1F25",
            },
        ],
        "fonts": [{"key": "playfair_display", "name": "Playfair Display"}],
        "backgrounds": [{"key": "plain", "name": "Trơn"}, {"key": "paper", "name": "Giấy dó"}],
        "defaults": {
            "palette_key": "ivory_gold",
            "font_key": "playfair_display",
            "background_key": "plain",
        },
        "max_gallery_images": 30,
    }
    return {**manifest, **overrides}


EMPTY_PERSON: dict[str, Any] = {
    "full_name": None,
    "display_name": None,
    "birth_order": None,
    "bio": None,
    "father": {"full_name": None, "is_deceased": False},
    "mother": {"full_name": None, "is_deceased": False},
    "family_address": None,
}


def empty_content(sections: list[str]) -> dict[str, Any]:
    """Content v1 đầy đủ với mọi trường để trống: dạng service ghi khi tạo thiệp."""
    return {
        "couple": {"groom": EMPTY_PERSON, "bride": EMPTY_PERSON},
        "messages": {"greeting": None, "invitation_message": None, "guest_notes": None},
        "love_story": [],
        "gifts": [],
        "appearance": {
            "palette_key": None,
            "font_key": None,
            "background_key": None,
            "sections": list(sections),
        },
    }


def make_minimal_manifest() -> dict[str, Any]:
    """Manifest của `minimal_01` trong fixture: khác `make_manifest()` để test đổi template.

    Giữ: section cover, events, gallery; palette burgundy; nền plain.
    Không có: greeting, couple; palette ivory_gold; font playfair_display; nền paper.
    """
    burgundy = make_manifest()["palettes"][1]
    charcoal = {
        "key": "charcoal",
        "name": "Than chì",
        "primary": "#1F1F1F",
        "secondary": "#BDBDBD",
        "background": "#FFFFFF",
        "text": "#1F1F1F",
    }
    return make_manifest(
        sections=["cover", "events", "gallery", "gifts"],
        default_sections=["cover", "events"],
        palettes=[charcoal, burgundy],
        fonts=[{"key": "be_vietnam_pro", "name": "Be Vietnam Pro"}],
        backgrounds=[{"key": "plain", "name": "Trơn"}],
        defaults={
            "palette_key": "charcoal",
            "font_key": "be_vietnam_pro",
            "background_key": "plain",
        },
    )


@pytest.fixture
async def templates(session_maker: async_sessionmaker) -> dict[str, Template]:
    items = {
        "classic_01": Template(
            key="classic_01", name="Cổ điển", category="classic", manifest=make_manifest()
        ),
        "minimal_01": Template(
            key="minimal_01",
            name="Tối giản",
            category="minimal",
            manifest=make_minimal_manifest(),
        ),
        "vintage_01": Template(
            key="vintage_01",
            name="Hoài cổ",
            category="vintage",
            is_premium=True,
            manifest=make_manifest(),
        ),
        "old_01": Template(
            key="old_01",
            name="Ngừng dùng",
            category="classic",
            is_active=False,
            manifest=make_manifest(),
        ),
    }
    async with session_maker() as db:
        db.add_all(items.values())
        await db.commit()
    return items


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
async def client(
    session_maker: async_sessionmaker, fake_storage: FakeStorage
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: fake_storage

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def register_user(
    client: AsyncClient, email: str = "nam@example.com", password: str = "matkhau123"
) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": "Nguyễn Văn Nam"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def auth(client: AsyncClient) -> dict[str, str]:
    return await register_user(client)


@pytest.fixture
async def other_auth(client: AsyncClient) -> dict[str, str]:
    return await register_user(client, email="khac@example.com")
