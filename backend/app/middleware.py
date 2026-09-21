"""Per-request context: a request id on every response and log line, and one access log entry."""

import re
import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
# Accept a caller's id only if it is short and plain, so it cannot forge log lines.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

log = structlog.get_logger("winnow.http")


class RequestContextMiddleware:
    """Pure ASGI middleware, so streaming responses (SSE) pass through untouched."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        status_code = 500
        started = time.perf_counter()

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                # API responses carry private data: never cache unless a route opts in.
                headers.setdefault("Cache-Control", "no-store")
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_headers)
            finally:
                route = scope.get("route")
                log.info(
                    "http.request",
                    method=scope["method"],
                    route=getattr(route, "path", "<unmatched>"),
                    status=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
