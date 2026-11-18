import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import init_db, get_sessionmaker
from app.core.init_seed import seed_database_if_empty
from app.core.exceptions import AttendAIException
from app.api.v1.api import api_router
from app.cache.redis_client import get_redis

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("attendai")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing AttendAI database tables...")
    await init_db()
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            await seed_database_if_empty(db)
            from app.core.policy_generator import seed_policies_if_needed
            await seed_policies_if_needed(db)
    except Exception as e:
        logger.error(f"Error during bootstrap seeding check: {e}", exc_info=True)
    logger.info("AttendAI backend startup complete.")
    yield
    logger.info("Shutting down AttendAI backend...")

app = FastAPI(
    title="AttendAI API",
    description="Intelligent Workforce. Smarter Decisions. Enterprise Time & Attendance Management.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits local development on any port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID & Logging Middleware
@app.middleware("http")
async def logging_and_request_id_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())
    request.state.request_id = req_id
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

    logger.info(
        f"[{req_id}] {request.method} {request.url.path} - {response.status_code} ({process_time:.2f}ms)"
    )
    return response

# Custom Exception Handlers
@app.exception_handler(AttendAIException)
async def attendai_exception_handler(request: Request, exc: AttendAIException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": True, "detail": exc.detail, "request_id": getattr(request.state, "request_id", None)}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": True, "detail": "Internal Server Error", "request_id": getattr(request.state, "request_id", None)}
    )

# Include API routes
app.include_router(api_router)

@app.get("/")
async def root():
    return {
        "app": "AttendAI",
        "tagline": "Intelligent Workforce. Smarter Decisions.",
        "status": "operational",
        "version": "1.0.0",
        "docs_url": "/docs"
    }
