import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ["APP_ENV"] = "test"

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


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> None:
    async def run() -> None:
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
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


@pytest.fixture
async def templates(session_maker: async_sessionmaker) -> dict[str, Template]:
    items = {
        "classic-01": Template(key="classic-01", name="Cổ điển", category="classic"),
        "minimal-01": Template(key="minimal-01", name="Tối giản", category="minimal"),
        "vintage-01": Template(
            key="vintage-01", name="Hoài cổ", category="vintage", is_premium=True
        ),
        "old-01": Template(key="old-01", name="Ngừng dùng", category="classic", is_active=False),
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
