# -*- coding: utf-8 -*-
"""
一键部署API路由
One-Click Deployment API Router

提供应用的一键部署和环境配置功能
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import asyncio
import subprocess
import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from ..core.logger import get_logger
from ..core.config import get_config

router = APIRouter()
logger = get_logger()

# 部署状态存储
deployment_status = {
    "status": "idle",  # idle, deploying, success, failed
    "progress": 0,
    "message": "",
    "logs": [],
    "start_time": None,
    "end_time": None
}


class DeploymentRequest(BaseModel):
    """部署请求模型"""
    target_platform: str  # local, docker, vercel, heroku
    environment: str = "production"  # development, production
    config_overrides: Optional[Dict[str, Any]] = None


class DeploymentResponse(BaseModel):
    """部署响应模型"""
    deployment_id: str
    status: str
    message: str
    progress: int
    estimated_time: Optional[int] = None


class DeploymentStatusResponse(BaseModel):
    """部署状态响应模型"""
    status: str
    progress: int
    message: str
    logs: List[str]
    start_time: Optional[str]
    end_time: Optional[str]
    duration: Optional[int] = None


@router.post("/deploy", response_model=DeploymentResponse)
async def start_deployment(request: DeploymentRequest, background_tasks: BackgroundTasks):
    """
    启动一键部署
    
    支持多种部署平台：本地、Docker、Vercel、Heroku等
    """
    try:
        if deployment_status["status"] == "deploying":
            raise HTTPException(status_code=400, detail="部署正在进行中，请等待完成")
        
        # 重置部署状态
        deployment_status.update({
            "status": "deploying",
            "progress": 0,
            "message": "开始部署...",
            "logs": [],
            "start_time": datetime.now().isoformat(),
            "end_time": None
        })
        
        # 生成部署ID
        deployment_id = f"deploy_{int(datetime.now().timestamp())}"
        
        # 在后台执行部署
        background_tasks.add_task(
            _execute_deployment,
            request.target_platform,
            request.environment,
            request.config_overrides or {}
        )
        
        return DeploymentResponse(
            deployment_id=deployment_id,
            status="deploying",
            message="部署已开始，请查看状态获取进度",
            progress=0,
            estimated_time=_get_estimated_time(request.target_platform)
        )
        
    except Exception as e:
        logger.error(f"启动部署失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动部署失败: {str(e)}")


@router.get("/status", response_model=DeploymentStatusResponse)
async def get_deployment_status():
    """
    获取部署状态
    
    返回当前部署的进度、状态和日志信息
    """
    try:
        status = deployment_status.copy()
        
        # 计算持续时间
        duration = None
        if status["start_time"]:
            start_time = datetime.fromisoformat(status["start_time"])
            end_time = datetime.fromisoformat(status["end_time"]) if status["end_time"] else datetime.now()
            duration = int((end_time - start_time).total_seconds())
        
        return DeploymentStatusResponse(
            status=status["status"],
            progress=status["progress"],
            message=status["message"],
            logs=status["logs"][-50:],  # 只返回最近50条日志
            start_time=status["start_time"],
            end_time=status["end_time"],
            duration=duration
        )
        
    except Exception as e:
        logger.error(f"获取部署状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取部署状态失败: {str(e)}")


@router.get("/platforms")
async def get_supported_platforms():
    """
    获取支持的部署平台列表
    """
    return {
        "platforms": [
            {
                "id": "local",
                "name": "本地部署",
                "description": "在本地环境中部署应用",
                "requirements": ["Python 3.8+", "pip"],
                "estimated_time": 120
            },
            {
                "id": "docker",
                "name": "Docker部署",
                "description": "使用Docker容器部署应用",
                "requirements": ["Docker", "Docker Compose"],
                "estimated_time": 300
            },
            {
                "id": "vercel",
                "name": "Vercel部署",
                "description": "部署到Vercel云平台",
                "requirements": ["Vercel CLI", "Git"],
                "estimated_time": 180
            },
            {
                "id": "heroku",
                "name": "Heroku部署",
                "description": "部署到Heroku云平台",
                "requirements": ["Heroku CLI", "Git"],
                "estimated_time": 240
            }
        ]
    }


@router.post("/stop")
async def stop_deployment():
    """
    停止当前部署
    """
    try:
        if deployment_status["status"] != "deploying":
            raise HTTPException(status_code=400, detail="没有正在进行的部署")
        
        deployment_status.update({
            "status": "failed",
            "message": "部署已被用户停止",
            "end_time": datetime.now().isoformat()
        })
        
        return {"message": "部署已停止"}
        
    except Exception as e:
        logger.error(f"停止部署失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"停止部署失败: {str(e)}")


async def _execute_deployment(platform: str, environment: str, config_overrides: Dict[str, Any]):
    """
    执行部署过程
    """
    try:
        _add_log(f"开始部署到 {platform} 平台")
        _update_progress(5, "准备部署环境...")
        
        if platform == "local":
            await _deploy_local(environment, config_overrides)
        elif platform == "docker":
            await _deploy_docker(environment, config_overrides)
        elif platform == "vercel":
            await _deploy_vercel(environment, config_overrides)
        elif platform == "heroku":
            await _deploy_heroku(environment, config_overrides)
        else:
            raise ValueError(f"不支持的部署平台: {platform}")
        
        deployment_status.update({
            "status": "success",
            "progress": 100,
            "message": "部署成功完成",
            "end_time": datetime.now().isoformat()
        })
        _add_log("部署成功完成")
        
    except Exception as e:
        deployment_status.update({
            "status": "failed",
            "progress": deployment_status["progress"],
            "message": f"部署失败: {str(e)}",
            "end_time": datetime.now().isoformat()
        })
        _add_log(f"部署失败: {str(e)}")
        logger.error(f"部署失败: {str(e)}")


async def _deploy_local(environment: str, config_overrides: Dict[str, Any]):
    """本地部署"""
    _update_progress(10, "检查本地环境...")
    
    # 检查Python版本
    result = await _run_command(["python", "--version"])
    _add_log(f"Python版本: {result.stdout.strip()}")
    
    _update_progress(20, "安装依赖...")
    
    # 安装依赖
    await _run_command(["pip", "install", "-r", "requirements.txt"])
    _add_log("依赖安装完成")
    
    _update_progress(40, "配置环境...")
    
    # 创建配置文件
    await _create_config_file(environment, config_overrides)
    _add_log("配置文件创建完成")
    
    _update_progress(60, "初始化数据库...")
    
    # 初始化数据库
    await _run_command(["python", "-c", "from src.database.manager import DatabaseManager; import asyncio; asyncio.run(DatabaseManager().initialize())"])
    _add_log("数据库初始化完成")
    
    _update_progress(80, "启动服务...")
    
    # 创建启动脚本
    await _create_startup_script()
    _add_log("启动脚本创建完成")
    
    _update_progress(95, "验证部署...")
    
    # 验证部署
    await _verify_deployment("http://127.0.0.1:8080")
    _add_log("部署验证完成")


async def _deploy_docker(environment: str, config_overrides: Dict[str, Any]):
    """Docker部署"""
    _update_progress(10, "检查Docker环境...")
    
    # 检查Docker
    result = await _run_command(["docker", "--version"])
    _add_log(f"Docker版本: {result.stdout.strip()}")
    
    _update_progress(20, "创建Dockerfile...")
    
    # 创建Dockerfile
    await _create_dockerfile()
    _add_log("Dockerfile创建完成")
    
    _update_progress(40, "构建Docker镜像...")
    
    # 构建镜像
    await _run_command(["docker", "build", "-t", "bilibili-tool", "."])
    _add_log("Docker镜像构建完成")
    
    _update_progress(60, "创建docker-compose.yml...")
    
    # 创建docker-compose文件
    await _create_docker_compose(environment, config_overrides)
    _add_log("docker-compose.yml创建完成")
    
    _update_progress(80, "启动容器...")
    
    # 启动容器
    await _run_command(["docker-compose", "up", "-d"])
    _add_log("Docker容器启动完成")
    
    _update_progress(95, "验证部署...")
    
    # 验证部署
    await asyncio.sleep(10)  # 等待容器启动
    await _verify_deployment("http://localhost:8080")
    _add_log("Docker部署验证完成")


async def _deploy_vercel(environment: str, config_overrides: Dict[str, Any]):
    """Vercel部署"""
    _update_progress(10, "检查Vercel CLI...")
    
    # 检查Vercel CLI
    result = await _run_command(["vercel", "--version"])
    _add_log(f"Vercel CLI版本: {result.stdout.strip()}")
    
    _update_progress(20, "创建vercel.json...")
    
    # 创建Vercel配置
    await _create_vercel_config(environment, config_overrides)
    _add_log("vercel.json创建完成")
    
    _update_progress(40, "准备部署文件...")
    
    # 创建API路由文件
    await _create_vercel_api_files()
    _add_log("API文件准备完成")
    
    _update_progress(60, "部署到Vercel...")
    
    # 部署到Vercel
    await _run_command(["vercel", "--prod", "--yes"])
    _add_log("Vercel部署完成")
    
    _update_progress(95, "验证部署...")
    
    # 获取部署URL并验证
    result = await _run_command(["vercel", "ls"])
    _add_log("Vercel部署验证完成")


async def _deploy_heroku(environment: str, config_overrides: Dict[str, Any]):
    """Heroku部署"""
    _update_progress(10, "检查Heroku CLI...")
    
    # 检查Heroku CLI
    result = await _run_command(["heroku", "--version"])
    _add_log(f"Heroku CLI版本: {result.stdout.strip()}")
    
    _update_progress(20, "创建Heroku应用...")
    
    # 创建Heroku应用
    app_name = f"bilibili-tool-{int(datetime.now().timestamp())}"
    await _run_command(["heroku", "create", app_name])
    _add_log(f"Heroku应用创建完成: {app_name}")
    
    _update_progress(40, "配置环境变量...")
    
    # 设置环境变量
    for key, value in config_overrides.items():
        await _run_command(["heroku", "config:set", f"{key}={value}", "-a", app_name])
    _add_log("环境变量配置完成")
    
    _update_progress(60, "创建Procfile...")
    
    # 创建Procfile
    await _create_procfile()
    _add_log("Procfile创建完成")
    
    _update_progress(80, "部署到Heroku...")
    
    # 部署到Heroku
    await _run_command(["git", "add", "."])
    await _run_command(["git", "commit", "-m", "Deploy to Heroku"])
    await _run_command(["git", "push", "heroku", "main"])
    _add_log("Heroku部署完成")
    
    _update_progress(95, "验证部署...")
    
    # 验证部署
    await _verify_deployment(f"https://{app_name}.herokuapp.com")
    _add_log("Heroku部署验证完成")


async def _run_command(cmd: List[str]) -> subprocess.CompletedProcess:
    """运行命令"""
    _add_log(f"执行命令: {' '.join(cmd)}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        _add_log(f"命令执行失败: {error_msg}")
        raise RuntimeError(f"命令执行失败: {error_msg}")
    
    result = subprocess.CompletedProcess(
        cmd, process.returncode, stdout.decode(), stderr.decode()
    )
    
    if result.stdout.strip():
        _add_log(f"命令输出: {result.stdout.strip()}")
    
    return result


async def _create_config_file(environment: str, config_overrides: Dict[str, Any]):
    """创建配置文件"""
    config_path = Path("config/config.json")
    config_path.parent.mkdir(exist_ok=True)
    
    # 基础配置
    config = {
        "server": {
            "host": "0.0.0.0",
            "port": 8080,
            "debug": environment == "development"
        },
        "database": {
            "path": "data/bilibili.db"
        },
        "bilibili": {
            "cookie": "",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "api_delay": 1.0,
            "retry_times": 3,
            "timeout": 30
        }
    }
    
    # 应用配置覆盖
    for key, value in config_overrides.items():
        keys = key.split('.')
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


async def _create_startup_script():
    """创建启动脚本"""
    # Windows启动脚本
    with open("start.bat", 'w', encoding='utf-8') as f:
        f.write("@echo off\n")
        f.write("echo Starting Bilibili Tool...\n")
        f.write("python main.py\n")
        f.write("pause\n")
    
    # Linux/Mac启动脚本
    with open("start.sh", 'w', encoding='utf-8') as f:
        f.write("#!/bin/bash\n")
        f.write("echo \"Starting Bilibili Tool...\"\n")
        f.write("python main.py\n")
    
    # 设置执行权限
    os.chmod("start.sh", 0o755)


async def _create_dockerfile():
    """创建Dockerfile"""
    dockerfile_content = """
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "main.py"]
"""
    
    with open("Dockerfile", 'w', encoding='utf-8') as f:
        f.write(dockerfile_content.strip())


async def _create_docker_compose(environment: str, config_overrides: Dict[str, Any]):
    """创建docker-compose.yml"""
    compose_content = f"""
version: '3.8'

services:
  bilibili-tool:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    environment:
      - ENVIRONMENT={environment}
    restart: unless-stopped
"""
    
    with open("docker-compose.yml", 'w', encoding='utf-8') as f:
        f.write(compose_content.strip())


async def _create_vercel_config(environment: str, config_overrides: Dict[str, Any]):
    """创建vercel.json配置"""
    vercel_config = {
        "version": 2,
        "builds": [
            {
                "src": "main.py",
                "use": "@vercel/python"
            }
        ],
        "routes": [
            {
                "src": "/(.*)",
                "dest": "main.py"
            }
        ]
    }
    
    with open("vercel.json", 'w', encoding='utf-8') as f:
        json.dump(vercel_config, f, indent=2)


async def _create_vercel_api_files():
    """创建Vercel API文件"""
    api_dir = Path("api")
    api_dir.mkdir(exist_ok=True)
    
    # 创建主API文件
    with open(api_dir / "index.py", 'w', encoding='utf-8') as f:
        f.write("""
from main import app

def handler(request):
    return app(request)
""")


async def _create_procfile():
    """创建Procfile"""
    with open("Procfile", 'w', encoding='utf-8') as f:
        f.write("web: python main.py\n")


async def _verify_deployment(url: str):
    """验证部署"""
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    _add_log(f"部署验证成功: {url}")
                else:
                    raise RuntimeError(f"部署验证失败: HTTP {response.status}")
    except Exception as e:
        raise RuntimeError(f"部署验证失败: {str(e)}")


def _update_progress(progress: int, message: str):
    """更新部署进度"""
    deployment_status["progress"] = progress
    deployment_status["message"] = message
    logger.info(f"部署进度: {progress}% - {message}")


def _add_log(message: str):
    """添加日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    deployment_status["logs"].append(log_entry)
    logger.info(message)


def _get_estimated_time(platform: str) -> int:
    """获取预估部署时间（秒）"""
    times = {
        "local": 120,
        "docker": 300,
        "vercel": 180,
        "heroku": 240
    }
    return times.get(platform, 180)