# -*- coding: utf-8 -*-
"""
哔哩哔哩关注列表批量管理工具 - 主程序入口
Bilibili Following List Batch Management Tool - Main Entry Point

作者: Bilibili Batch Operation Tool Team
版本: 1.0.0
许可证: Apache 2.0
"""

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
import os
import sys
import socket
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent))

from src.api import bilibili_router, data_router, analysis_router
from src.core.config import get_config
from src.core.logger import setup_logger
from src.database.manager import DatabaseManager

# 初始化日志
logger = setup_logger()

# 初始化数据库
db_manager = DatabaseManager()


def get_db_manager():
    """获取数据库管理器实例"""
    return db_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时的初始化操作
    try:
        # 创建必要的目录
        os.makedirs("data", exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        os.makedirs("config", exist_ok=True)
        
        # 初始化数据库
        await db_manager.initialize()
        
        # 将数据库管理器添加到应用状态中
        app.state.db_manager = db_manager
        
        logger.info("应用启动成功")
        yield
    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        raise
    finally:
        # 关闭时的清理操作
        try:
            await db_manager.close()
            logger.info("应用关闭成功")
        except Exception as e:
            logger.error(f"应用关闭时出错: {e}")


# 创建FastAPI应用实例
app = FastAPI(
    title="哔哩哔哩关注列表管理工具",
    description="一个功能强大的哔哩哔哩关注列表管理工具，支持批量操作、数据可视化和智能分类",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 设置静态文件服务
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# 设置模板引擎
templates = Jinja2Templates(directory="web/templates")


# 注册API路由
app.include_router(bilibili_router, prefix="/api/bilibili", tags=["哔哩哔哩API"])
app.include_router(data_router, prefix="/api/data", tags=["数据管理"])
app.include_router(analysis_router, prefix="/api/analysis", tags=["数据分析"])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/following", response_class=HTMLResponse)
async def following_page(request: Request):
    """关注列表页面"""
    return templates.TemplateResponse("following.html", {"request": request})


@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    """数据分析页面"""
    return templates.TemplateResponse("analysis.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """设置页面"""
    return templates.TemplateResponse("settings.html", {"request": request})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理器"""
    logger.error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "服务器内部错误",
            "status_code": 500
        }
    )


def main():
    """主函数"""
    try:
        # 获取配置
        config = get_config()
        host = config.get("server", {}).get("host", "127.0.0.1")
        port = config.get("server", {}).get("port", 8080)
        debug = config.get("server", {}).get("debug", False)
        
        # 检查端口是否被占用，如果被占用则尝试其他端口
        def is_port_in_use(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('localhost', port)) == 0
        
        original_port = port
        while is_port_in_use(port) and port < original_port + 10:
            port += 1
            logger.warning(f"端口 {port-1} 被占用，尝试端口 {port}")
        
        if port != original_port:
            logger.info(f"使用端口 {port} 替代默认端口 {original_port}")
        
        logger.info(f"启动服务器: http://{host}:{port}")
        
        # 启动服务
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=debug,
            log_level="info"
        )
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 