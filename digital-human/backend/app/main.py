"""FastAPI 应用入口"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.websocket import router as websocket_router
from app.api.tingwu_ws import router as tingwu_router
from app.api.resume import router as resume_router

# 配置日志级别
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# 降低三方库的噪声日志（尤其是 websockets/urllib3 在 DEBUG 下会打印大量二进制帧，严重影响性能）
logging.getLogger("websockets").setLevel(logging.INFO)
logging.getLogger("websockets.client").setLevel(logging.INFO)
logging.getLogger("websockets.server").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="数字人应用后端 API",
    version="1.0.0",
    debug=settings.debug
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(websocket_router, prefix="/api")
app.include_router(tingwu_router, prefix="/api")
app.include_router(resume_router, prefix="/api")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Digital Human API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

