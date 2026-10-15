from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import PandaError
from app.core.logging import get_logger

log = get_logger("api.errors")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PandaError)
    async def handle_panda_error(_: Request, exc: PandaError) -> JSONResponse:
        status = 400 if exc.user_facing else 500
        if status == 500:
            log.error("unhandled domain error: %s", exc.message)
        return JSONResponse({"code": exc.code, "message": exc.message if exc.user_facing else "Internal error"}, status_code=status)
