from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Business error with a plain-language message and a stable machine code."""

    def __init__(
        self, code: str, detail: str, status: int = 400, fields: dict[str, Any] | None = None
    ) -> None:
        super().__init__(detail)
        self.code, self.detail, self.status, self.fields = code, detail, status, fields


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {"detail": exc.detail, "code": exc.code}
        if exc.fields:
            body["fields"] = exc.fields
        return JSONResponse(body, status_code=exc.status)
