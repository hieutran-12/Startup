"""Smoke test: chạy luồng thật của người dùng vào một môi trường đã deploy.

    python3 -I scripts/smoke_test.py https://api-staging.ketduyen.me

Job smoke-staging của .gitlab-ci.yml chạy sau mỗi lần deploy staging. Chỉ dùng thư viện chuẩn
(không cần `uv sync`). Luồng: health → đăng ký → refresh bằng cookie → tạo thiệp → sự kiện →
upload ảnh lên S3 → complete → gắn ảnh bìa → publish → trang public → đọc ảnh qua CloudFront →
xoá ảnh, xoá thiệp. User thử (email e2e-...@example.com) ở lại vì API không có endpoint xoá
tài khoản; chạy vào production thì phải xoá tay (README › Lên production).
Thoát mã 0 khi mọi bước đúng, 1 khi có bước sai.
"""

import json
import secrets
import struct
import sys
import urllib.error
import urllib.request
import zlib
from typing import Any

TIMEOUT_SECONDS = 30


class Api:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.failed = False

    def request(
        self,
        method: str,
        url: str,
        body: Any = None,
        headers: dict[str, str] | None = None,
        raw: bytes | None = None,
    ) -> tuple[int, Any, Any]:
        if not url.startswith("http"):
            url = self.base_url + url
        sent_headers = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            sent_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, method=method, headers=sent_headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                status, resp_headers, text = resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as exc:
            status, resp_headers, text = exc.code, exc.headers, exc.read()
        try:
            payload = json.loads(text) if text else None
        except ValueError:
            payload = None
        return status, resp_headers, payload

    def check(self, name: str, ok: bool, detail: Any = "") -> bool:
        self.failed |= not ok
        print(("OK  " if ok else "FAIL"), name, detail if detail != "" else "")
        return ok


def tiny_png(width: int, height: int) -> bytes:
    """Ảnh PNG nhỏ hợp lệ, không cần thư viện ảnh."""
    raw = b"".join(b"\x00" + b"\xff\x80\x80" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def run(api: Api) -> None:
    status, _, body = api.request("GET", "/health")
    if not api.check("health", status == 200 and body == {"status": "ok"}, status):
        return

    email = f"e2e-{secrets.token_hex(4)}@example.com"
    status, headers, body = api.request(
        "POST",
        "/auth/register",
        {"email": email, "password": "smoke-test-" + secrets.token_hex(8), "full_name": "Smoke"},
    )
    if not api.check("đăng ký", status == 201, f"{status} {email}"):
        return
    cookie = (headers.get("set-cookie") or "").split(";")[0]
    status, _, body = api.request("POST", "/auth/refresh", headers={"Cookie": cookie})
    if not api.check("refresh bằng cookie", status == 200, status):
        return
    auth = {"Authorization": f"Bearer {body['access_token']}"}

    status, _, templates = api.request("GET", "/templates")
    if not api.check("danh sách mẫu", status == 200 and len(templates) > 0, status):
        return
    content = {
        "couple": {
            "groom": {"full_name": "Nguyễn Văn Thử"},
            "bride": {"full_name": "Trần Thị Thử"},
        }
    }
    status, headers, invitation = api.request(
        "POST", "/invitations", {"template_key": templates[0]["key"], "content": content}, auth
    )
    if not api.check("tạo thiệp", status == 201, f"{status} {templates[0]['key']}"):
        return
    invitation_id, etag = invitation["id"], headers.get("etag")

    try:
        event = {
            "event_type": "reception",
            "host_side": "both",
            "event_date": "2027-01-10",
            "start_time": "11:00",
            "address": "1 Đường Thử, Hà Nội",
        }
        status, headers, _ = api.request(
            "POST", f"/invitations/{invitation_id}/events", event, {**auth, "If-Match": etag}
        )
        if not api.check("thêm sự kiện", status == 201, status):
            return
        etag = headers.get("etag")

        image = tiny_png(4, 3)
        status, _, ticket = api.request(
            "POST",
            f"/invitations/{invitation_id}/media/upload-url",
            {"filename": "smoke.png", "content_type": "image/png", "size_bytes": len(image)},
            auth,
        )
        if not api.check("xin link upload", status == 200, status):
            return
        status, _, _ = api.request(
            "PUT", ticket["upload_url"], headers=ticket["headers"], raw=image
        )
        if not api.check("PUT ảnh lên S3", status == 200, status):
            return
        media_id = ticket["media_id"]
        status, _, media = api.request(
            "POST",
            f"/invitations/{invitation_id}/media/{media_id}/complete",
            {"width": 4, "height": 3},
            auth,
        )
        if not api.check("complete", status == 200 and media["status"] == "ready", status):
            return
        status, _, _ = api.request(
            "PATCH",
            f"/invitations/{invitation_id}",
            {"cover_media_id": media_id},
            {**auth, "If-Match": etag},
        )
        if not api.check("gắn ảnh bìa", status == 200, status):
            return

        status, _, published = api.request(
            "POST", f"/invitations/{invitation_id}/publish", {}, auth
        )
        if not api.check("publish", status == 200, status):
            return
        status, _, public = api.request(
            "GET", f"/public/invitations/{published['slug']}?side=groom"
        )
        ok = status == 200 and public["events"][0]["lunar_date"] is not None
        if not api.check("trang public ?side=groom", ok, status):
            return
        image_url = public["media_by_id"][media_id]["url"]
        status, _, _ = api.request("GET", image_url)
        api.check("đọc ảnh qua CloudFront", status == 200, status)

        status, _, _ = api.request(
            "DELETE", f"/invitations/{invitation_id}/media/{media_id}", headers=auth
        )
        api.check("xoá ảnh", status == 204, status)
    finally:
        status, _, _ = api.request("DELETE", f"/invitations/{invitation_id}", headers=auth)
        api.check("xoá thiệp", status == 204, status)


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print("Cách dùng: python3 -I scripts/smoke_test.py https://<domain API>", file=sys.stderr)
        return 2
    api = Api(sys.argv[1])
    run(api)
    print("Smoke test:", "LỖI" if api.failed else "ĐẠT")
    return 1 if api.failed else 0


if __name__ == "__main__":
    sys.exit(main())
