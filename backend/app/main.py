from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core import startup
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging


def build_api_router() -> APIRouter:
    """Every module contributes one router; the prefix/version lives here only."""
    from app.modules.admin.router import router as admin_router
    from app.modules.auth.router import router as auth_router
    from app.modules.bookings.router import router as bookings_router
    from app.modules.notifications.router import router as notifications_router
    from app.modules.parking.router import router as parking_router
    from app.modules.payments.router import router as payments_router
    from app.modules.providers.router import router as providers_router
    from app.modules.reports.router import router as reports_router
    from app.modules.reviews.router import router as reviews_router
    from app.modules.users.router import router as users_router
    from app.modules.vehicles.router import router as vehicles_router

    api = APIRouter(prefix=settings.api_prefix)
    for module_router in (
        auth_router,
        users_router,
        vehicles_router,
        providers_router,
        parking_router,
        bookings_router,
        payments_router,
        reviews_router,
        reports_router,
        notifications_router,
        admin_router,
    ):
        api.include_router(module_router)
    return api


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from app.core import scheduler

    task = scheduler.start(app)
    try:
        yield
    finally:
        await scheduler.stop(task)


def create_app() -> FastAPI:
    # Before anything is wired up, so an insecure production process fails to
    # boot rather than coming up healthy and quietly doing the wrong thing.
    configure_logging()
    startup.verify(settings)

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Marketplace for listing and booking unused parking spaces.",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(build_api_router())

    if settings.storage_backend == "local":
        media_root = Path(settings.media_root)
        media_root.mkdir(parents=True, exist_ok=True)
        app.mount(settings.media_url, StaticFiles(directory=media_root), name="media")

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
