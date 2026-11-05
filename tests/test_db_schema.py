"""Bước 2: schema do migration 0001 tạo phải khớp model và giữ đúng các ràng buộc ở spec 03.

Test chạy trên schema dựng bằng `alembic upgrade head` (xem conftest), nên kiểm tra luôn migration.
"""

import uuid
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Table, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models import Base, Invitation

TABLES = Base.metadata.tables
MEDIA_COLUMNS = ("cover_media_id", "groom_photo_media_id", "bride_photo_media_id", "music_media_id")


async def _insert(engine: AsyncEngine, table: str, **values: Any) -> uuid.UUID:
    row_id = values.setdefault("id", uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(insert(TABLES[table]).values(**values))
    return row_id


async def _template(engine: AsyncEngine, **values: Any) -> uuid.UUID:
    base = {
        "key": f"t_{uuid.uuid4().hex[:8]}",
        "name": "Mẫu",
        "category": "classic",
        "manifest": {},
    }
    return await _insert(engine, "templates", **{**base, **values})


async def _invitation(
    engine: AsyncEngine, owner_id: uuid.UUID, template_id: uuid.UUID, **values: Any
) -> uuid.UUID:
    base = {
        "owner_id": owner_id,
        "template_id": template_id,
        "slug": f"thiep-{uuid.uuid4().hex[:8]}",
        "title": "Nam & Lan",
        "content": {},
    }
    return await _insert(engine, "invitations", **{**base, **values})


async def _media(engine: AsyncEngine, invitation_id: uuid.UUID, **values: Any) -> uuid.UUID:
    media_id = uuid.uuid4()
    base = {
        "id": media_id,
        "invitation_id": invitation_id,
        "storage_key": f"invitations/{invitation_id}/{media_id}",
        "mime_type": "image/jpeg",
        "size_bytes": 1000,
        "kind": "image",
    }
    return await _insert(engine, "media", **{**base, **values})


async def _event(engine: AsyncEngine, invitation_id: uuid.UUID, **values: Any) -> uuid.UUID:
    base = {"invitation_id": invitation_id, "event_type": "reception", "host_side": "both"}
    return await _insert(engine, "events", **{**base, **values})


async def _row(engine: AsyncEngine, table: str, row_id: uuid.UUID) -> dict[str, Any] | None:
    t: Table = TABLES[table]
    async with engine.connect() as conn:
        row = (await conn.execute(select(t).where(t.c.id == row_id))).mappings().first()
    return dict(row) if row else None


async def _count(engine: AsyncEngine, table: str, invitation_id: uuid.UUID) -> int:
    t: Table = TABLES[table]
    async with engine.connect() as conn:
        stmt = select(func.count()).select_from(t).where(t.c.invitation_id == invitation_id)
        return (await conn.execute(stmt)).scalar_one()


@dataclass
class Graph:
    owner_id: uuid.UUID
    template_id: uuid.UUID
    invitation_id: uuid.UUID
    other_invitation_id: uuid.UUID
    # Mỗi cột *_media_id một file riêng của thiệp chính
    media_by_column: dict[str, uuid.UUID]
    other_image_id: uuid.UUID
    other_audio_id: uuid.UUID


@pytest.fixture
async def graph(db_engine: AsyncEngine) -> Graph:
    owner_id = await _insert(
        db_engine, "users", email="nam@example.com", full_name="Nguyễn Văn Nam"
    )
    template_id = await _template(db_engine)
    invitation_id = await _invitation(db_engine, owner_id, template_id)
    other_invitation_id = await _invitation(db_engine, owner_id, template_id)
    media_by_column = {
        "cover_media_id": await _media(db_engine, invitation_id),
        "groom_photo_media_id": await _media(db_engine, invitation_id),
        "bride_photo_media_id": await _media(db_engine, invitation_id),
        "music_media_id": await _media(
            db_engine, invitation_id, kind="audio", mime_type="audio/mpeg"
        ),
    }
    return Graph(
        owner_id=owner_id,
        template_id=template_id,
        invitation_id=invitation_id,
        other_invitation_id=other_invitation_id,
        media_by_column=media_by_column,
        other_image_id=await _media(db_engine, other_invitation_id),
        other_audio_id=await _media(
            db_engine, other_invitation_id, kind="audio", mime_type="audio/mpeg"
        ),
    )


async def _set_invitation(engine: AsyncEngine, invitation_id: uuid.UUID, **values: Any) -> None:
    t = TABLES["invitations"]
    async with engine.begin() as conn:
        await conn.execute(update(t).where(t.c.id == invitation_id).values(**values))


# ---------- Migration khớp model ----------


async def test_migration_matches_models(db_engine: AsyncEngine) -> None:
    """Tương đương `alembic revision --autogenerate` không sinh thay đổi nào."""

    def diff(sync_conn) -> list:
        context = MigrationContext.configure(
            sync_conn, opts={"compare_type": True, "compare_server_default": True}
        )
        return compare_metadata(context, Base.metadata)

    async with db_engine.connect() as conn:
        assert await conn.run_sync(diff) == []


async def test_database_defaults(db_engine: AsyncEngine, graph: Graph) -> None:
    """DEFAULT nằm trong database, không chỉ ở phía Python."""
    async with db_engine.begin() as conn:
        template_id = (
            await conn.execute(
                text(
                    "INSERT INTO templates (id, key, name, category, manifest) "
                    "VALUES (gen_random_uuid(), 'classic_99', 'Mẫu', 'classic', '{}') RETURNING id"
                )
            )
        ).scalar_one()
        invitation_id = (
            await conn.execute(
                text(
                    "INSERT INTO invitations (id, owner_id, template_id, slug, title, content) "
                    "VALUES (gen_random_uuid(), :owner, :template, 'nam-lan', 'Nam', '{}') "
                    "RETURNING id"
                ),
                {"owner": graph.owner_id, "template": template_id},
            )
        ).scalar_one()
        event_id = (
            await conn.execute(
                text(
                    "INSERT INTO events (id, invitation_id, event_type, host_side) "
                    "VALUES (gen_random_uuid(), :inv, 'reception', 'both') RETURNING id"
                ),
                {"inv": invitation_id},
            )
        ).scalar_one()

    template = await _row(db_engine, "templates", template_id)
    assert template is not None
    assert (template["is_premium"], template["is_active"], template["position"]) == (
        False,
        True,
        0,
    )
    assert template["created_at"] is not None and template["updated_at"] is not None

    invitation = await _row(db_engine, "invitations", invitation_id)
    assert invitation is not None
    assert invitation["status"] == "draft"
    assert invitation["published_at"] is None
    assert invitation["content_schema_version"] == 1
    assert invitation["revision"] == 1
    assert all(invitation[c] is None for c in MEDIA_COLUMNS)

    event = await _row(db_engine, "events", event_id)
    assert event is not None
    assert event["timezone"] == "Asia/Ho_Chi_Minh"
    assert event["position"] == 0


# ---------- Khóa ngoại kép invitations -> media (tiêu chí nghiệm thu) ----------


@pytest.mark.parametrize("column", MEDIA_COLUMNS)
async def test_attach_own_media(db_engine: AsyncEngine, graph: Graph, column: str) -> None:
    media_id = graph.media_by_column[column]
    await _set_invitation(db_engine, graph.invitation_id, **{column: media_id})
    invitation = await _row(db_engine, "invitations", graph.invitation_id)
    assert invitation is not None and invitation[column] == media_id


@pytest.mark.parametrize("column", MEDIA_COLUMNS)
async def test_attach_media_of_other_invitation_rejected(
    db_engine: AsyncEngine, graph: Graph, column: str
) -> None:
    other = graph.other_audio_id if column == "music_media_id" else graph.other_image_id
    constraint = "fk_invitations_" + column.removesuffix("_id")
    with pytest.raises(IntegrityError, match=constraint):
        await _set_invitation(db_engine, graph.invitation_id, **{column: other})


async def test_attach_missing_media_rejected(db_engine: AsyncEngine, graph: Graph) -> None:
    with pytest.raises(IntegrityError, match="fk_invitations_cover_media"):
        await _set_invitation(db_engine, graph.invitation_id, cover_media_id=uuid.uuid4())


@pytest.mark.parametrize("column", MEDIA_COLUMNS)
async def test_delete_media_nulls_only_its_column(
    db_engine: AsyncEngine, graph: Graph, column: str
) -> None:
    await _set_invitation(db_engine, graph.invitation_id, **graph.media_by_column)

    media = TABLES["media"]
    async with db_engine.begin() as conn:
        await conn.execute(media.delete().where(media.c.id == graph.media_by_column[column]))

    invitation = await _row(db_engine, "invitations", graph.invitation_id)
    assert invitation is not None
    assert invitation["id"] == graph.invitation_id
    assert invitation[column] is None
    for other_column, media_id in graph.media_by_column.items():
        if other_column != column:
            assert invitation[other_column] == media_id


async def test_delete_invitation_with_references(
    db_engine: AsyncEngine, session_maker: async_sessionmaker, graph: Graph
) -> None:
    """Xoá thiệp đang gắn đủ 4 file, có album và sự kiện: không lỗi, dữ liệu con bị xoá theo."""
    await _set_invitation(db_engine, graph.invitation_id, **graph.media_by_column)
    album_id = await _insert(
        db_engine, "albums", invitation_id=graph.invitation_id, title="Album cưới"
    )
    await _media(db_engine, graph.invitation_id, album_id=album_id)
    await _event(db_engine, graph.invitation_id)
    # Thiệp khác gắn file của chính nó: không bị ảnh hưởng
    await _set_invitation(db_engine, graph.other_invitation_id, cover_media_id=graph.other_image_id)

    # Xoá qua ORM như service đang làm
    async with session_maker() as db:
        invitation = await db.get(Invitation, graph.invitation_id)
        assert invitation is not None
        await db.delete(invitation)
        await db.commit()

    assert await _row(db_engine, "invitations", graph.invitation_id) is None
    for table in ("media", "albums", "events"):
        assert await _count(db_engine, table, graph.invitation_id) == 0

    other = await _row(db_engine, "invitations", graph.other_invitation_id)
    assert other is not None and other["cover_media_id"] == graph.other_image_id
    assert await _count(db_engine, "media", graph.other_invitation_id) == 2


# ---------- CHECK ----------


async def test_template_category_check(db_engine: AsyncEngine) -> None:
    await _template(db_engine, category="modern")
    with pytest.raises(IntegrityError, match="ck_templates_category_valid"):
        await _template(db_engine, category="rustic")


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"status": "archived"}, "ck_invitations_status_valid"),
        ({"slug": "ab"}, "ck_invitations_slug_valid"),
        ({"slug": "Nam-Lan"}, "ck_invitations_slug_valid"),
        ({"slug": "nam--lan"}, "ck_invitations_slug_valid"),
        ({"slug": "-nam-lan"}, "ck_invitations_slug_valid"),
        ({"slug": "nam_lan"}, "ck_invitations_slug_valid"),
        ({"status": "published"}, "ck_invitations_published_at_matches_status"),
        ({"published_at": func.now()}, "ck_invitations_published_at_matches_status"),
        ({"content_schema_version": 0}, "ck_invitations_content_schema_version_positive"),
    ],
)
async def test_invitation_checks(
    db_engine: AsyncEngine, graph: Graph, values: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await _invitation(db_engine, graph.owner_id, graph.template_id, **values)


async def test_invitation_checks_accept_valid_rows(db_engine: AsyncEngine, graph: Graph) -> None:
    await _invitation(db_engine, graph.owner_id, graph.template_id, slug="abc")
    await _invitation(db_engine, graph.owner_id, graph.template_id, slug="a" * 60)
    await _invitation(db_engine, graph.owner_id, graph.template_id, slug="nam-lan-2026")
    await _invitation(
        db_engine,
        graph.owner_id,
        graph.template_id,
        status="published",
        published_at=func.now(),
    )


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"kind": "video"}, "ck_media_kind_valid"),
        ({"kind": "audio", "width": 100}, "ck_media_audio_has_no_image_fields"),
        ({"kind": "audio", "height": 100}, "ck_media_audio_has_no_image_fields"),
    ],
)
async def test_media_checks(
    db_engine: AsyncEngine, graph: Graph, values: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await _media(db_engine, graph.invitation_id, **values)


async def test_audio_cannot_be_in_album(db_engine: AsyncEngine, graph: Graph) -> None:
    album_id = await _insert(db_engine, "albums", invitation_id=graph.invitation_id, title="A")
    await _media(db_engine, graph.invitation_id, album_id=album_id, width=800, height=600)
    with pytest.raises(IntegrityError, match="ck_media_audio_has_no_image_fields"):
        await _media(db_engine, graph.invitation_id, kind="audio", album_id=album_id)


async def test_media_invitation_id_pair_is_unique(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'uq_media_invitation_id'"
            )
        )
        assert rows.scalar_one() == "UNIQUE (invitation_id, id)"


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"event_type": "wedding"}, "ck_events_event_type_valid"),
        ({"host_side": "guest"}, "ck_events_host_side_valid"),
        (
            {"event_type": "family_ceremony", "host_side": "both"},
            "ck_events_family_ceremony_single_side",
        ),
        ({"event_type": "other"}, "ck_events_other_has_name"),
        ({"end_time": time(12, 0)}, "ck_events_end_time_after_start_time"),
        (
            {"start_time": time(12, 0), "end_time": time(12, 0)},
            "ck_events_end_time_after_start_time",
        ),
        (
            {"start_time": time(22, 0), "end_time": time(1, 0)},
            "ck_events_end_time_after_start_time",
        ),
        ({"latitude": Decimal("21")}, "ck_events_coordinates_paired"),
        ({"longitude": Decimal("105")}, "ck_events_coordinates_paired"),
        (
            {"latitude": Decimal("90.000001"), "longitude": Decimal("105")},
            "ck_events_latitude_range",
        ),
        ({"latitude": Decimal("-91"), "longitude": Decimal("105")}, "ck_events_latitude_range"),
        (
            {"latitude": Decimal("21"), "longitude": Decimal("180.000001")},
            "ck_events_longitude_range",
        ),
        ({"latitude": Decimal("21"), "longitude": Decimal("-181")}, "ck_events_longitude_range"),
    ],
)
async def test_event_checks(
    db_engine: AsyncEngine, graph: Graph, values: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await _event(db_engine, graph.invitation_id, **values)


@pytest.mark.parametrize(
    "values",
    [
        {"event_type": "family_ceremony", "host_side": "groom"},
        {"event_type": "family_ceremony", "host_side": "bride"},
        {"event_type": "other", "host_side": "both", "event_name": "Lễ rước dâu"},
        {"start_time": time(11, 0)},
        {"start_time": time(11, 0), "end_time": time(13, 30)},
        {"latitude": Decimal("90"), "longitude": Decimal("-180")},
        {"latitude": Decimal("-90"), "longitude": Decimal("180")},
    ],
)
async def test_event_checks_accept_valid_rows(
    db_engine: AsyncEngine, graph: Graph, values: dict[str, Any]
) -> None:
    await _event(db_engine, graph.invitation_id, **values)
