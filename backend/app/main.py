"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import repository as repo
from app.api.routes import router
from app.config import get_settings
from app.database import warehouse
from app.models.schemas import HealthResponse
from app.utils.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)

DESCRIPTION = """
Operational decision intelligence for NHS elective waiting list management,
built on **publicly available NHS England aggregate statistics**.

The API converts published Referral to Treatment (RTT) data into descriptive,
diagnostic, predictive and scenario-based intelligence, with a transparent and
fully decomposable operational priority score.

**This is an independent portfolio prototype.** It is not affiliated with or
endorsed by NHS England, is not a clinical decision support system, and uses no
patient-level data. Forecasts and scenario outputs are modelled estimates, not
observed effects.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the read caches at startup so the first request is not slow."""
    if warehouse.warehouse_exists():
        try:
            repo.load_metadata()
            repo.load_providers()
            repo.load_specialties()
            repo.load_snapshot()
            # The quality report takes a few seconds over ~60k rows; computing
            # it here keeps the first Data Quality page view fast.
            repo.load_quality_report()
            meta = repo.load_metadata()
            logger.info(
                "Warehouse loaded: %s data, latest month %s, %s fact rows",
                meta.get("data_source_type"),
                meta.get("latest_reporting_month"),
                meta.get("fact_rows"),
            )
        except Exception:
            logger.exception("Failed to warm warehouse caches")
    else:
        logger.warning(
            "No warehouse found at %s. The API will start, but analytics "
            "endpoints will return 503 until 'make data' has been run.",
            settings.warehouse_path,
        )
    yield


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(repo.WarehouseUnavailable)
async def warehouse_unavailable_handler(
    request: Request, exc: repo.WarehouseUnavailable
) -> JSONResponse:
    """Return an actionable 503 rather than a stack trace."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": str(exc),
            "remedy": [
                "Run 'make data' to ingest official NHS England data.",
                "Or run 'make demo' to load the clearly-labelled demo dataset.",
            ],
        },
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(
    request: Request, exc: FileNotFoundError
) -> JSONResponse:
    logger.error("Missing file during request %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Required data files are missing. Build the warehouse with "
                "'make data'."
            ),
            "error": str(exc),
        },
    )


@app.get("/health", response_model=HealthResponse, tags=["metadata"])
def health() -> HealthResponse:
    """Liveness and warehouse readiness."""
    available = warehouse.warehouse_exists()
    tables: dict[str, int] = {}
    message = ""
    if available:
        try:
            tables = warehouse.table_row_counts()
        except Exception as exc:
            available = False
            message = f"Warehouse present but unreadable: {exc}"
    else:
        message = (
            "No warehouse built. Run 'make data' for official NHS England data "
            "or 'make demo' for the synthetic demonstration dataset."
        )

    mode = "unknown"
    if available:
        try:
            mode = str(repo.load_metadata().get("data_source_type") or "unknown")
        except Exception:
            mode = "unknown"

    return HealthResponse(
        status="ok" if available else "degraded",
        app_version=settings.app_version,
        warehouse_available=available,
        data_mode=mode,
        tables=tables,
        message=message,
    )


@app.get("/", tags=["metadata"])
def root() -> dict:
    """Service banner."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_prefix,
        "disclaimer": (
            "Independent portfolio prototype using publicly available NHS "
            "England data. Not affiliated with or endorsed by NHS England. "
            "Not a clinical decision support system."
        ),
    }


app.include_router(router, prefix=settings.api_prefix)
