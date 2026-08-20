import logging
import time
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from product_agent.evaluation import evaluate_product_output
from product_agent.orchestrator import ProductIntelligenceOrchestrator
from product_agent.schemas import (
    BatchRequest,
    ComponentStatus,
    EvaluationRequest,
    EvaluationScore,
    ProductInput,
    ProductIntelligence,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Verify critical dependencies are reachable before accepting traffic."""
    logger.info("Starting Industrial Commerce Product AI Agent...")
    from product_agent.evaluation import configure_langsmith
    configure_langsmith()
    try:
        orchestrator.component_status()
        logger.info("Startup checks passed.")
    except Exception as exc:
        logger.error("Startup check failed: %s", exc)
        # Allow startup anyway — endpoints will surface errors per-request
    yield
    logger.info("Shutting down Industrial Commerce Product AI Agent.")


# ---------------------------------------------------------------------------
# App & singleton orchestrator
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Industrial Commerce Product AI Agent",
    description=(
        "AI-powered product intelligence API for industrial commerce. "
        "Extracts, enriches, and stores structured product data from minimal inputs."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

orchestrator = ProductIntelligenceOrchestrator()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware — request timing & correlation ID
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_request_metadata(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            "Unhandled error | request_id=%s path=%s elapsed_ms=%s error=%s",
            request_id, request.url.path, elapsed, exc,
        )
        raise
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Response-Time-Ms"] = str(elapsed)
    logger.info(
        "%s %s | status=%s request_id=%s elapsed_ms=%s",
        request.method, request.url.path, response.status_code, request_id, elapsed,
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured 422 with field-level detail instead of FastAPI's default."""
    errors = [
        {
            "field": " → ".join(str(loc) for loc in err["loc"]),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    logger.warning(
        "Validation error | request_id=%s path=%s errors=%s",
        getattr(request.state, "request_id", "n/a"), request.url.path, errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "detail": "One or more request fields failed validation.",
            "errors": errors,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Wrap HTTP exceptions with a consistent JSON envelope."""
    logger.warning(
        "HTTP %s | request_id=%s path=%s detail=%s",
        exc.status_code,
        getattr(request.state, "request_id", "n/a"),
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "status_code": exc.status_code,
            "detail": exc.detail,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unexpected server errors — log with traceback, return 500."""
    logger.error(
        "Unhandled exception | request_id=%s path=%s\n%s",
        getattr(request.state, "request_id", "n/a"),
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred. Please try again or contact support.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Operations"])
def health() -> dict:
    """Liveness probe — returns service status and component link summary."""
    try:
        components = orchestrator.component_status()
        all_linked = all(c.linked for c in components)
        return {
            "status": "ok" if all_linked else "degraded",
            "components": {c.name: {"linked": c.linked, "detail": c.detail} for c in components},
        }
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {exc}",
        )


@app.get("/components", response_model=list[ComponentStatus], tags=["Operations"])
def components() -> list[ComponentStatus]:
    """Return the link status of each internal orchestrator component."""
    try:
        return orchestrator.component_status()
    except Exception as exc:
        logger.error("component_status failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve component status.",
        )


@app.post(
    "/process-product",
    response_model=ProductIntelligence,
    status_code=status.HTTP_200_OK,
    tags=["Product Intelligence"],
)
def process_product(product: ProductInput) -> ProductIntelligence:
    """Build rich product intelligence from minimal product identifiers.

    Uses the deterministic regex baseline only for deployable, dependency-light processing.
    """
    try:
        return orchestrator.process_product(product)
    except ValueError as exc:
        logger.warning("Invalid product input: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid product data: {exc}",
        )
    except RuntimeError as exc:
        logger.error("Runtime error in process_product: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service dependency unavailable: {exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in process_product for MPN=%s", product.manufacturer_part_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process product. The error has been logged.",
        )


@app.post(
    "/batch",
    response_model=list[ProductIntelligence],
    status_code=status.HTTP_200_OK,
    tags=["Product Intelligence"],
)
def batch(request: BatchRequest) -> list[ProductIntelligence]:
    """Process a batch of products. Partial failures are surfaced per-item in quality_warnings."""
    if not request.products:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch request must contain at least one product.",
        )
    if len(request.products) > 50:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Batch size exceeds the maximum of 50 products per request.",
        )
    try:
        return orchestrator.batch(request.products)
    except RuntimeError as exc:
        logger.error("Runtime error in batch: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service dependency unavailable: {exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in batch (count=%d)", len(request.products))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch processing failed. The error has been logged.",
        )


@app.get(
    "/products",
    response_model=list[ProductIntelligence],
    tags=["Product Intelligence"],
)
def products(limit: int = 50) -> list[ProductIntelligence]:
    """List previously processed products stored in Supabase."""
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 200.",
        )
    try:
        return orchestrator.store.list_products(limit=limit)
    except RuntimeError as exc:
        logger.error("Storage error in list_products: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Storage unavailable: {exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in products listing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve products. The error has been logged.",
        )


@app.post(
    "/evaluate",
    response_model=list[EvaluationScore],
    tags=["Evaluation"],
)
def evaluate(request: EvaluationRequest) -> list[EvaluationScore]:
    """Score a ProductIntelligence output against the quality rubric."""
    try:
        scores = evaluate_product_output(request.product_input, request.output)
        return [
            EvaluationScore(key=score.key, score=score.score, comment=score.comment)
            for score in scores
        ]
    except ValueError as exc:
        logger.warning("Evaluation input error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid evaluation input: {exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in evaluate")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation failed. The error has been logged.",
        )
