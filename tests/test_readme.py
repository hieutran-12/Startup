"""Bước 11: README khớp đặc tả và khớp code (spec 06 › Bước 11)."""

import re
from pathlib import Path

import pytest

from app.main import app

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

# Endpoint trong README viết dạng `METHOD /đường/dẫn` (tham số query đặt ngoài cặp backtick)
_ENDPOINT = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/[^`\s?]*)")


@pytest.mark.parametrize(
    "pattern",
    [
        # Cột event_date của thiệp đã bỏ (spec 03 › invitations); primary_event_date không bị bắt
        r"\bevent_date\b",
        r"\btheme",
        r"lunar_date_text",
        # Trường content của khung cũ
        r"\bmusic_url\b",
        r"\bbank_accounts\b",
        r"\badditional_notes\b",
        r"\bfield_schema\b",
        r"\bsort_order\b",
    ],
)
def test_readme_does_not_mention_old_fields(pattern: str) -> None:
    assert not re.search(pattern, README, flags=re.IGNORECASE), pattern


def _app_endpoints() -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def test_readme_lists_every_endpoint_of_the_app() -> None:
    listed = set(_ENDPOINT.findall(README))

    assert sorted(_app_endpoints() - listed) == []


def test_readme_lists_no_endpoint_the_app_does_not_have() -> None:
    listed = set(_ENDPOINT.findall(README))

    assert sorted(listed - _app_endpoints()) == []
