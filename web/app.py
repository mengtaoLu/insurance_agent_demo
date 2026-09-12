from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from web.pages.login import app as LoginApp
from web.pages.chat import app as ChatApp

from agent.tools.tool_registry import load_builtin_tools, close_mcp_tools
from agent.llm.models import Model


@asynccontextmanager
async def lifespan(app: FastAPI):
    model = None
    try:
        await load_builtin_tools()
        model = Model("你是一个保险金融的agent助手，可以帮助用户处理保单咨询问题，理赔问题等。")
        app.state.model = model
        yield
    finally:
        try:
            if model is not None:
                await model.close()
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
