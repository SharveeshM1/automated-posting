import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.platforms import build_platforms
from app.schemas import PostingRequest, PostingResponse, ValidationErrorResponse
from app.services.posting_service import PostingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs full request URLs at INFO, which may contain credentials for some APIs.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout_seconds),
        follow_redirects=True,
        headers={"User-Agent": "automated-posting/1.0"},
    )
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Automated Multi-Platform Posting System",
    description="Publishes one short message with a single CTA link to several platforms via their APIs.",
    version="1.0.0",
    lifespan=lifespan,
)


def get_service(request: Request) -> PostingService:
    settings = get_settings()
    platforms = build_platforms(settings, request.app.state.http_client)
    return PostingService(platforms, timeout=settings.platform_timeout_seconds)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for err in exc.errors():
        parts = [str(p) for p in err["loc"][1:] if not isinstance(p, int)]
        message = err["msg"]
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        errors.append({"field": ".".join(parts) or "body", "error": message})
    return JSONResponse(status_code=422, content={"success": False, "errors": errors})


@app.post(
    "/posting",
    response_model=PostingResponse,
    summary="Publish a message to all platforms",
    responses={422: {"model": ValidationErrorResponse, "description": "Invalid message"}},
)
async def posting(payload: PostingRequest, service: PostingService = Depends(get_service)):
    return await service.post(payload.message)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
