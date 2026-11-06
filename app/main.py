from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.banks.router import router as banks_router
from app.modules.events.router import router as events_router
from app.modules.invitations.router import public_router
from app.modules.invitations.router import router as invitations_router
from app.modules.media.router import router as media_router
from app.modules.templates.router import router as templates_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        # Ẩn Swagger ở production
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # để trình duyệt gửi cookie refresh_token
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag"],  # để JS ở Next.js đọc được revision của thiệp
    )
    register_error_handlers(app)

    app.include_router(auth_router)
    app.include_router(templates_router)
    app.include_router(invitations_router)
    app.include_router(events_router)
    app.include_router(media_router)
    app.include_router(banks_router)
    app.include_router(public_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
