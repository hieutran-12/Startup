import re
import secrets
import unicodedata

SLUG_MIN_LENGTH = 3
SLUG_MAX_LENGTH = 60
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Slug nằm ngay sau domain (thiepcuoi.vn/<slug>) nên phải tránh trùng route của Next.js
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "app",
        "auth",
        "dashboard",
        "login",
        "logout",
        "register",
        "signup",
        "signin",
        "me",
        "settings",
        "account",
        "templates",
        "mau-thiep",
        "pricing",
        "bang-gia",
        "about",
        "help",
        "support",
        "terms",
        "privacy",
        "static",
        "assets",
        "_next",
        "public",
        "media",
        "www",
        "blog",
    }
)


def slugify(text: str) -> str:
    """'Nguyễn Văn Nam & Trần Thị Lan' -> 'nguyen-van-nam-tran-thi-lan'"""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:SLUG_MAX_LENGTH].strip("-")


def slug_error(slug: str) -> str | None:
    """Trả về lý do slug không hợp lệ, hoặc None nếu hợp lệ."""
    if not SLUG_MIN_LENGTH <= len(slug) <= SLUG_MAX_LENGTH:
        return f"Đường dẫn phải dài từ {SLUG_MIN_LENGTH} đến {SLUG_MAX_LENGTH} ký tự"
    if not SLUG_PATTERN.match(slug):
        return "Đường dẫn chỉ gồm chữ thường không dấu, số và dấu gạch ngang"
    if slug in RESERVED_SLUGS:
        return "Đường dẫn này đã được hệ thống sử dụng"
    return None


def with_random_suffix(base: str) -> str:
    suffix = secrets.token_hex(2)  # 4 ký tự hex
    base = base[: SLUG_MAX_LENGTH - len(suffix) - 1].strip("-")
    return f"{base}-{suffix}" if base else f"thiep-{suffix}"
