"""Client S3 chạy được với storage tự chạy (RustFS, local và VPS) và với AWS S3 dùng IAM role.

Không gọi mạng: chỉ tạo client và ký presigned URL.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.storage import S3Storage
from app.scripts import init_storage

KEY = "invitations/abc/photo.jpg"


@pytest.fixture(autouse=True)
def _isolate_aws_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Credential, profile hay config AWS trên máy dev không được ảnh hưởng tới test."""
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_S3",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(settings, "s3_bucket", "thiepcuoi-media")


def _use(monkeypatch: pytest.MonkeyPatch, **values: object) -> None:
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


def _query(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


def test_local_storage_uses_path_style_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(
        monkeypatch,
        s3_endpoint_url="http://localhost:9000",
        s3_region="auto",
        s3_access_key_id="thiepcuoi",
        s3_secret_access_key="thiepcuoi-secret",
    )

    url = S3Storage().presign_put(KEY, "image/jpeg")

    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == "http://localhost:9000"
    assert parts.path == f"/thiepcuoi-media/{KEY}"
    assert _query(url)["X-Amz-Credential"].startswith("thiepcuoi/")


def test_aws_s3_uses_virtual_hosted_url_in_bucket_region(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(
        monkeypatch,
        s3_endpoint_url=None,
        s3_region="ap-southeast-2",
        s3_access_key_id="AKIAEXAMPLE",
        s3_secret_access_key="example-secret",
    )

    url = S3Storage().presign_put(KEY, "image/jpeg")

    parts = urlsplit(url)
    assert parts.scheme == "https"
    assert parts.netloc == "thiepcuoi-media.s3.ap-southeast-2.amazonaws.com"
    assert parts.path == f"/{KEY}"
    credential = _query(url)["X-Amz-Credential"]
    assert credential.startswith("AKIAEXAMPLE/")
    assert credential.endswith("/ap-southeast-2/s3/aws4_request")


def test_aws_s3_without_keys_uses_default_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # Biến môi trường AWS_* đứng thay cho IAM role: boto3 đọc cả hai theo cùng một chuỗi mặc định
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ASIAROLEEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "role-secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "role-session-token")
    _use(
        monkeypatch,
        s3_endpoint_url=None,
        s3_region="ap-southeast-2",
        s3_access_key_id=None,
        s3_secret_access_key=None,
    )

    query = _query(S3Storage().presign_put(KEY, "image/jpeg"))

    assert query["X-Amz-Credential"].startswith("ASIAROLEEXAMPLE/")
    assert query["X-Amz-Security-Token"] == "role-session-token"


def test_default_settings_point_to_local_storage() -> None:
    config = Settings(_env_file=None)

    assert config.s3_endpoint_url == "http://localhost:9000"
    assert config.s3_access_key_id == "thiepcuoi"
    assert config.s3_secret_access_key == "thiepcuoi-secret"


def test_empty_endpoint_and_keys_mean_aws_s3_with_default_credentials() -> None:
    config = Settings(
        _env_file=None,
        s3_endpoint_url="",
        s3_region="ap-southeast-2",
        s3_access_key_id="",
        s3_secret_access_key="  ",
    )

    assert config.s3_endpoint_url is None
    assert config.s3_access_key_id is None
    assert config.s3_secret_access_key is None


@pytest.mark.parametrize("empty_key", ["s3_access_key_id", "s3_secret_access_key"])
def test_storage_keys_must_be_set_together(empty_key: str) -> None:
    with pytest.raises(ValidationError, match="S3_ACCESS_KEY_ID"):
        Settings(_env_file=None, **{empty_key: ""})


def test_aws_s3_requires_bucket_region() -> None:
    with pytest.raises(ValidationError, match="S3_REGION"):
        Settings(_env_file=None, s3_endpoint_url="", s3_access_key_id="", s3_secret_access_key="")


def test_init_storage_refuses_aws_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, s3_endpoint_url=None, s3_region="ap-southeast-2")

    with pytest.raises(SystemExit, match="S3_ENDPOINT_URL"):
        init_storage.main()


def test_init_storage_runs_in_production_with_own_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production trên VPS dùng storage tự chạy (có endpoint): script vẫn phải tạo được bucket."""

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def head_bucket(self, **_: object) -> None:
            self.calls.append("head_bucket")

        def put_bucket_cors(self, **_: object) -> None:
            self.calls.append("put_bucket_cors")

        def put_bucket_policy(self, **_: object) -> None:
            self.calls.append("put_bucket_policy")

    class FakeStorage:
        bucket = "thiepcuoi-media"
        client = FakeClient()

    _use(monkeypatch, app_env="production", s3_endpoint_url="https://media.example.com")
    monkeypatch.setattr(init_storage, "S3Storage", FakeStorage)

    init_storage.main()

    assert FakeStorage.client.calls == ["head_bucket", "put_bucket_cors", "put_bucket_policy"]
