"""Báo Next.js build lại trang thiệp (ISR on-demand) mỗi khi thiệp thay đổi."""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def revalidate_invitation(*slugs: str) -> None:
    """Chạy trong BackgroundTasks; lỗi chỉ ghi log, không làm hỏng request chính."""
    if not settings.frontend_revalidate_url or not slugs:
        return
    payload = {"slugs": [s for s in slugs if s]}
    headers = {"x-revalidate-secret": settings.frontend_revalidate_secret or ""}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                settings.frontend_revalidate_url, json=payload, headers=headers
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Revalidate thất bại cho %s: %s", payload["slugs"], exc)
