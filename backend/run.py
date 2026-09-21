"""后端启动入口：host/port 也从统一配置读取。

用法（两种启动方式等价，端口都取自 .env 的 BACKEND_PORT）：
    python run.py
    uvicorn app.main:app --host <BACKEND_HOST> --port <BACKEND_PORT>
"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.backend_host,
                port=settings.backend_port, log_level="info")
