# -*- coding: utf-8 -*-
"""
日志管理模块
Logging Management Module

提供统一的日志配置和管理功能
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

from .config import get_config_value


class LoggerManager:
    """日志管理器"""
    
    def __init__(self):
        self._logger: Optional[logging.Logger] = None
        self._setup_done = False
    
    def setup(self) -> logging.Logger:
        """设置日志"""
        if self._setup_done and self._logger:
            return self._logger
        
        # 获取配置
        log_level = get_config_value("logging.level", "INFO")
        log_file = get_config_value("logging.file_path", "logs/app.log")
        max_file_size = get_config_value("logging.max_file_size", "10MB")
        backup_count = get_config_value("logging.backup_count", 5)
        
        # 创建日志目录
        log_path = Path(log_file)
        os.makedirs(log_path.parent, exist_ok=True)
        
        # 创建logger
        self._logger = logging.getLogger("bilibili_tool")
        self._logger.setLevel(getattr(logging, log_level.upper()))
        
        # 避免重复添加handler
        if not self._logger.handlers:
            # 创建格式化器
            formatter = logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)
            
            # 文件处理器（支持轮转）
            try:
                # 解析文件大小
                if max_file_size.endswith("MB"):
                    max_bytes = int(max_file_size[:-2]) * 1024 * 1024
                elif max_file_size.endswith("KB"):
                    max_bytes = int(max_file_size[:-2]) * 1024
                else:
                    max_bytes = int(max_file_size)
                
                file_handler = logging.handlers.RotatingFileHandler(
                    filename=log_file,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(getattr(logging, log_level.upper()))
                file_handler.setFormatter(formatter)
                self._logger.addHandler(file_handler)
            except Exception as e:
                self._logger.error(f"创建文件日志处理器失败: {e}")
        
        self._setup_done = True
        return self._logger
    
    def get_logger(self) -> logging.Logger:
        """获取logger实例"""
        if not self._setup_done:
            return self.setup()
        return self._logger


# 全局日志管理器实例
_logger_manager = LoggerManager()


def setup_logger() -> logging.Logger:
    """设置并获取logger"""
    return _logger_manager.setup()


def get_logger() -> logging.Logger:
    """获取logger实例"""
    return _logger_manager.get_logger()


# 提供便捷的日志函数
def log_info(message: str):
    """记录信息日志"""
    get_logger().info(message)


def log_warning(message: str):
    """记录警告日志"""
    get_logger().warning(message)


def log_error(message: str):
    """记录错误日志"""
    get_logger().error(message)


def log_debug(message: str):
    """记录调试日志"""
    get_logger().debug(message) 