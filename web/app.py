from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from web.pages.login import app as LoginApp
from web.pages.chat import app as ChatApp

from agent.tools.tool_registry import load_builtin_tools, close_mcp_tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await load_builtin_tools()
        yield
    finally:
        await close_mcp_tools()

app = FastAPI(lifespan=lifespan)
app.include_router(LoginApp)
app.include_router(ChatApp)

@app.exception_handler(HTTPException)
async def http_exception_handler(
    request:Request,
    exc: HTTPException
):
    if exc.status_code == 401:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail
        }
    )
