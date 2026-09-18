"""FastAPI entrypoint and HTTP endpoint definitions for GridWise."""

import logging
import time
import uuid
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError as FastAPIRequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import settings
from app.errors import GridWiseError, RequestValidationError
from app.schemas.request import OptimizationRequest
from app.schemas.response import OptimizationResponse
from app.services.optimization_service import optimization_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gridwise.api")

app = FastAPI(
    title="GridWise LLM Energy Optimizer",
    description="Optimal 24-hour campus energy scheduling with natural language operator directive parsing.",
    version="1.0.0",
)


@app.exception_handler(FastAPIRequestValidationError)
async def fastapi_validation_exception_handler(request: Request, exc: FastAPIRequestValidationError):
    """Formats Pydantic/FastAPI validation errors into a controlled HTTP 400 response."""
    error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    logger.warning(f"Request validation failure on {request.url.path}: {error_messages}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "RequestValidationError",
            "message": "The request body failed structural schema validation.",
            "details": error_messages,
        },
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Formats internal model validation errors into HTTP 400."""
    error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    logger.warning(f"Internal validation failure on {request.url.path}: {error_messages}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "RequestValidationError",
            "message": "Validation failed on input models.",
            "details": error_messages,
        },
    )


@app.exception_handler(GridWiseError)
async def gridwise_custom_exception_handler(request: Request, exc: GridWiseError):
    """Handles controlled domain errors without exposing stack traces or secrets."""
    logger.error(f"Domain error on {request.url.path} [{exc.status_code}]: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Guarantees no raw stack traces or internal secrets are ever exposed publicly."""
    logger.exception(f"Unhandled internal failure on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An internal operational error occurred during processing.",
        },
    )


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Deterministic, lightweight health check endpoint required by official judging."""
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizationResponse, status_code=status.HTTP_200_OK)
async def optimize_energy(
    request: Request,
    body: OptimizationRequest,
    response: Response,
):
    """Core energy optimization endpoint: parses operator notes, solves 24h LP, and returns valid plan."""
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())[:8]
    response.headers["X-Request-ID"] = req_id

    client_ip = request.client.host if request.client else "unknown"
    t_start = time.perf_counter()

    logger.info(
        f"[{req_id}] INCOMING POST /optimize-energy | scenario_id={body.scenario_id} "
        f"notes_count={len(body.operator_notes)} client={client_ip}"
    )

    try:
        res = await optimization_service.optimize(body, request_id=req_id)
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        logger.info(
            f"[{req_id}] COMPLETED POST /optimize-energy | status=200 in {elapsed_ms:.1f}ms | "
            f"scenario={res.scenario_id} cost_bdt={res.total_cost_bdt:.2f} "
            f"grid_kwh={res.total_grid_kwh:.2f} peak_grid={res.peak_grid_kwh:.2f} "
            f"directives_count={len(res.directive_interpretation)}"
        )
        return res

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        logger.error(
            f"[{req_id}] FAILED POST /optimize-energy | after {elapsed_ms:.1f}ms | "
            f"scenario={body.scenario_id} error={type(exc).__name__}: {exc}"
        )
        raise exc
