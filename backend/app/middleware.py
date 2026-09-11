"""ASGI middleware: cap incoming request bodies.

FastAPI/uvicorn do not enforce a body size by default, so an authenticated or
anonymous client could exhaust memory with an unbounded JSON payload. This
middleware rejects oversized bodies up front (Content-Length when present) and
counts streamed bytes otherwise.
"""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse


class BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: Any, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = dict(scope.get("headers") or {}).get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    response = JSONResponse(
                        {"detail": "Request body too large"}, status_code=413
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def counting_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLargeError()
            return message

        try:
            await self.app(scope, counting_receive, send)
        except BodyTooLargeError:
            response = JSONResponse({"detail": "Request body too large"}, status_code=413)
            await response(scope, receive, send)
