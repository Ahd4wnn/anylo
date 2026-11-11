import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import (
    auth,
    books,
    catalogue,
    finance,
    meta,
    money,
    people,
    purchasing,
    sales,
    shop,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Anylo API", version="0.1.0", openapi_url="/v1/openapi.json", docs_url="/v1/docs"
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "Idempotent-Replay"],
    )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    install_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(meta.router)
    app.include_router(shop.router)
    app.include_router(catalogue.router)
    app.include_router(sales.router)
    app.include_router(people.router)
    app.include_router(money.router)
    app.include_router(purchasing.router)
    app.include_router(finance.router)
    app.include_router(books.router)
    if settings.env == "dev":  # production: nginx serves /media
        Path(settings.media_root).mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=settings.media_root), name="media")

    @app.get("/v1/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
