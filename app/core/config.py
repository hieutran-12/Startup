from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Thiệp Cưới API"
    app_env: Literal["local", "test", "staging", "production"] = "local"

    # Database
    database_url: str = "postgresql+asyncpg://thiepcuoi:thiepcuoi@localhost:5432/thiepcuoi"
    database_echo: bool = False
    test_database_url: str | None = None  # chỉ pytest dùng

    # Auth
    jwt_secret: str = "change-me-in-env-at-least-32-characters-long"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    refresh_cookie_name: str = "refresh_token"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    # CORS: danh sách origin của Next.js, phân tách bằng dấu phẩy trong .env
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Object storage (S3 API: RustFS ở local, Cloudflare R2 ở production)
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "auto"
    s3_access_key_id: str = "thiepcuoi"
    s3_secret_access_key: str = "thiepcuoi-secret"
    s3_bucket: str = "thiepcuoi-media"
    # URL công khai để đọc ảnh (domain CDN gắn với bucket R2).
    # Link ảnh = media_public_base_url + "/" + storage_key
    media_public_base_url: str = "http://localhost:9000/thiepcuoi-media"
    presigned_url_ttl_seconds: int = 600

    # Giới hạn upload
    max_upload_bytes: int = 15 * 1024 * 1024
    allowed_image_types: Annotated[list[str], NoDecode] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/avif",
    ]
    max_media_per_invitation: int = 200
    max_invitations_per_user: int = 5

    # Next.js on-demand revalidation (để trống thì bỏ qua)
    frontend_revalidate_url: str | None = None
    frontend_revalidate_secret: str | None = None

    @field_validator("cors_origins", "allowed_image_types", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "test_database_url",
        "cookie_domain",
        "s3_endpoint_url",
        "frontend_revalidate_url",
        "frontend_revalidate_secret",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        # Biến môi trường để trống (VAR=) được hiểu là "không cấu hình"
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("media_public_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def check_production_settings(self) -> "Settings":
        if self.app_env == "production":
            if self.jwt_secret.startswith("change-me") or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET phải được đặt (>= 32 ký tự) khi chạy production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE phải là true khi chạy production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
