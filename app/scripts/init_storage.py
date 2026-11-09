"""Chuẩn bị bucket cho môi trường LOCAL (RustFS): tạo bucket, bật CORS, cho phép đọc công khai.

    uv run python -m app.scripts.init_storage

Không chạy với AWS S3: bucket production giữ chặn truy cập công khai, đọc ảnh qua CloudFront,
CORS cấu hình trên AWS console (README › Lên production).
"""

import json

from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.storage import S3Storage


def main() -> None:
    # Không có endpoint nghĩa là đang trỏ tới AWS S3: script sẽ mở đọc công khai cho bucket thật
    if settings.is_production or settings.s3_endpoint_url is None:
        raise SystemExit("Script này chỉ dành cho storage local (RustFS)")

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
