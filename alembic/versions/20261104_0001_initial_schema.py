"""initial schema: users, refresh_tokens, templates, invitations, albums, media, events

Viết lại theo docs/spec/03-mo-hinh-du-lieu.md (Bước 2). Chưa có dữ liệu production nên sửa
thẳng migration đầu tiên, không thêm migration sửa đổi. Cần PostgreSQL >= 15 vì cú pháp
ON DELETE SET NULL (cột).

Revision ID: 0001
Revises:
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Bốn cột tham chiếu file cố định của thiệp, mỗi cột một khóa ngoại kép tới media
MEDIA_REFERENCE_COLUMNS = (
    "cover_media_id",
    "groom_photo_media_id",
    "bride_photo_media_id",
    "music_media_id",
)


def _id() -> sa.Column:
    return sa.Column("id", sa.UUID(), nullable=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _media_fk_name(column: str) -> str:
    return f"fk_invitations_{column.removesuffix('_id')}"


def upgrade() -> None:
    op.create_table(
        "users",
        _id(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        _id(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "templates",
        _id(),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=2048), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("is_premium", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "category IN ('classic', 'minimal', 'floral', 'vintage', 'modern')",
            name=op.f("ck_templates_category_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_templates")),
        sa.UniqueConstraint("key", name=op.f("uq_templates_key")),
    )
    op.create_index(op.f("ix_templates_category"), "templates", ["category"], unique=False)

    op.create_table(
        "invitations",
        _id(),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "content_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *(sa.Column(column, sa.UUID(), nullable=True) for column in MEDIA_REFERENCE_COLUMNS),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name=op.f("ck_invitations_status_valid")
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) BETWEEN 3 AND 60",
            name=op.f("ck_invitations_slug_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'published') = (published_at IS NOT NULL)",
            name=op.f("ck_invitations_published_at_matches_status"),
        ),
        sa.CheckConstraint(
            "content_schema_version > 0",
            name=op.f("ck_invitations_content_schema_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_invitations_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
            name=op.f("fk_invitations_template_id_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("slug", name=op.f("uq_invitations_slug")),
    )
    op.create_index(op.f("ix_invitations_owner_id"), "invitations", ["owner_id"], unique=False)
    op.create_index(
        op.f("ix_invitations_template_id"), "invitations", ["template_id"], unique=False
    )

    op.create_table(
        "albums",
        _id(),
        sa.Column("invitation_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["invitations.id"],
            name=op.f("fk_albums_invitation_id_invitations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_albums")),
    )
    op.create_index(op.f("ix_albums_invitation_id"), "albums", ["invitation_id"], unique=False)

    op.create_table(
        "media",
        _id(),
        sa.Column("invitation_id", sa.UUID(), nullable=False),
        sa.Column("album_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('pending', 'ready')", name=op.f("ck_media_status_valid")),
        sa.CheckConstraint("kind IN ('image', 'audio')", name=op.f("ck_media_kind_valid")),
        sa.CheckConstraint(
            "kind = 'image' OR (width IS NULL AND height IS NULL AND album_id IS NULL)",
            name=op.f("ck_media_audio_has_no_image_fields"),
        ),
        sa.ForeignKeyConstraint(
            ["album_id"], ["albums.id"], name=op.f("fk_media_album_id_albums"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["invitations.id"],
            name=op.f("fk_media_invitation_id_invitations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_media_storage_key")),
        sa.UniqueConstraint("invitation_id", "id", name=op.f("uq_media_invitation_id")),
    )
    op.create_index(op.f("ix_media_album_id"), "media", ["album_id"], unique=False)
    op.create_index(
        "ix_media_invitation_position", "media", ["invitation_id", "position"], unique=False
    )

    op.create_table(
        "events",
        _id(),
        sa.Column("invitation_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("host_side", sa.String(length=8), nullable=False),
        sa.Column("event_name", sa.String(length=120), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("start_time", postgresql.TIME(precision=0), nullable=True),
        sa.Column("end_time", postgresql.TIME(precision=0), nullable=True),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Ho_Chi_Minh'"),
            nullable=False,
        ),
        sa.Column("venue_name", sa.String(length=200), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("maps_url", sa.String(length=2048), nullable=True),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "event_type IN ('engagement', 'family_ceremony', 'religious_ceremony', "
            "'reception', 'other')",
            name=op.f("ck_events_event_type_valid"),
        ),
        sa.CheckConstraint(
            "host_side IN ('groom', 'bride', 'both')", name=op.f("ck_events_host_side_valid")
        ),
        sa.CheckConstraint(
            "event_type <> 'family_ceremony' OR host_side <> 'both'",
            name=op.f("ck_events_family_ceremony_single_side"),
        ),
        sa.CheckConstraint(
            "event_type <> 'other' OR event_name IS NOT NULL",
            name=op.f("ck_events_other_has_name"),
        ),
        sa.CheckConstraint(
            "end_time IS NULL OR (start_time IS NOT NULL AND end_time > start_time)",
            name=op.f("ck_events_end_time_after_start_time"),
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name=op.f("ck_events_coordinates_paired"),
        ),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name=op.f("ck_events_latitude_range")),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name=op.f("ck_events_longitude_range")
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["invitations.id"],
            name=op.f("fk_events_invitation_id_invitations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(
        "ix_events_invitation_position", "events", ["invitation_id", "position"], unique=False
    )

    # invitations và media trỏ vào nhau: thêm khóa ngoại kép sau khi cả hai bảng đã có
    for column in MEDIA_REFERENCE_COLUMNS:
        op.create_foreign_key(
            op.f(_media_fk_name(column)),
            "invitations",
            "media",
            ["id", column],
            ["invitation_id", "id"],
            ondelete=f"SET NULL ({column})",
        )


def downgrade() -> None:
    for column in MEDIA_REFERENCE_COLUMNS:
        op.drop_constraint(op.f(_media_fk_name(column)), "invitations", type_="foreignkey")
    op.drop_table("events")
    op.drop_table("media")
    op.drop_table("albums")
    op.drop_table("invitations")
    op.drop_table("templates")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
