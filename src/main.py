import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app
from structlog import get_logger

from src.core.config import settings
from src.api.routes import router
from src.api.admin_routes import router as admin_router
from src.api.middleware import CorrelationIdMiddleware, PrometheusMiddleware
from src.worker.dispatcher import Dispatcher

logger = get_logger()
dispatcher = Dispatcher()
dispatch_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("startup")
    global dispatch_task
    dispatch_task = asyncio.create_task(dispatcher.run_loop())
    yield
    # Shutdown
    logger.info("shutdown")
    dispatcher.running = False
    if dispatch_task:
        dispatch_task.cancel()
        try:
            await dispatch_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Middleware (order matters – outermost first)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(CorrelationIdMiddleware)

# Routers
app.include_router(router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health():
    return {"status": "ok"}
