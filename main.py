from utils.logging_config import setup_logging
setup_logging() # 初始化日志

from web.app import app
import uvicorn as uv


if __name__ == '__main__':
    uv.run("main:app",port=8082,host="0.0.0.0",reload=True)