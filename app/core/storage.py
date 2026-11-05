"""Lớp truy cập object storage qua S3 API (RustFS khi chạy local, Cloudflare R2 khi production)."""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ObjectInfo:
    size_bytes: int
    content_type: str | None


class Storage(Protocol):
    def presign_put(self, key: str, content_type: str) -> str: ...
    async def head(self, key: str) -> ObjectInfo | None: ...
    async def delete(self, key: str) -> None: ...
    def public_url(self, key: str) -> str: ...


class S3Storage:
    def __init__(self) -> None:
        self.bucket = settings.s3_bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def presign_put(self, key: str, content_type: str) -> str:
        # Ký cả Content-Type: trình duyệt phải gửi đúng header này khi PUT, không đổi được loại file
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=settings.presigned_url_ttl_seconds,
            HttpMethod="PUT",
        )

    async def head(self, key: str) -> ObjectInfo | None:
        try:
            resp = await run_in_threadpool(self.client.head_object, Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectInfo(size_bytes=resp["ContentLength"], content_type=resp.get("ContentType"))

    async def delete(self, key: str) -> None:
        # Thường chạy trong background task: lỗi chỉ ghi log, file mồ côi dọn sau cũng được
        try:
            await run_in_threadpool(self.client.delete_object, Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            logger.warning("Không xoá được object %s: %s", key, exc)

    def public_url(self, key: str) -> str:
        return f"{settings.media_public_base_url}/{key}"


@lru_cache
def get_storage() -> Storage:
    return S3Storage()
