"""Chuẩn bị bucket cho môi trường LOCAL (RustFS): tạo bucket, bật CORS, cho phép đọc công khai.

    uv run python -m app.scripts.init_storage

Ở production (Cloudflare R2) hãy cấu hình trong dashboard R2 thay vì chạy script này:
bật Public access qua custom domain và thêm CORS cho domain Next.js.
"""

import json

from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.storage import S3Storage


def main() -> None:
    if settings.is_production:
        raise SystemExit("Script này chỉ dành cho môi trường local")

    storage = S3Storage()
    client, bucket = storage.client, storage.bucket

    try:
        client.head_bucket(Bucket=bucket)
        print(f"Bucket '{bucket}' đã tồn tại")
    except ClientError:
        client.create_bucket(Bucket=bucket)
        print(f"Đã tạo bucket '{bucket}'")

    try:
        client.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": settings.cors_origins,
                        "AllowedMethods": ["GET", "PUT", "HEAD"],
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["ETag"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )
        print("Đã cấu hình CORS cho upload từ trình duyệt")
    except ClientError as exc:
        print(f"Bỏ qua CORS (storage không hỗ trợ hoặc lỗi): {exc}")

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }
    try:
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        print("Đã cho phép đọc ảnh công khai")
    except ClientError as exc:
        print(f"Bỏ qua bucket policy: {exc}")


if __name__ == "__main__":
    main()
