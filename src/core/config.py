# -*- coding: utf-8 -*-
"""
配置管理模块
Configuration Management Module

负责应用程序的配置加载和管理
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.config_path = Path("config/config.json")
        self.default_config_path = Path("config/config.example.json")
        self._config: Optional[Dict[str, Any]] = None
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config is not None:
            return self._config
        
        # 如果配置文件不存在，创建默认配置
        if not self.config_path.exists():
            self._create_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"配置文件加载失败: {e}")
            self._config = self._get_default_config()
        
        return self._config
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """保存配置文件"""
        try:
            os.makedirs(self.config_path.parent, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            self._config = config
            return True
        except Exception as e:
            print(f"配置文件保存失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        config = self.load_config()
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置项"""
        config = self.load_config()
        keys = key.split('.')
        current = config
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
        return self.save_config(config)
    
    def _create_default_config(self):
        """创建默认配置文件"""
        default_config = self._get_default_config()
        self.save_config(default_config)
        
        # 同时创建示例配置文件
        os.makedirs(self.default_config_path.parent, exist_ok=True)
        with open(self.default_config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=4)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "bilibili": {
                "cookie": "",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "api_delay": 1.0,
                "retry_times": 3,
                "timeout": 30
            },
            "database": {
                "path": "data/bilibili.db",
                "backup_enabled": True,
                "backup_interval": 24
            },
            "server": {
                "host": "127.0.0.1",
                "port": 8080,
                "debug": False
            },
            "logging": {
                "level": "INFO",
                "file_path": "logs/app.log",
                "max_file_size": "10MB",
                "backup_count": 5
            },
            "analysis": {
                "cache_enabled": True,
                "cache_duration": 3600,
                "batch_size": 50
            },
            "ui": {
                "theme": "light",
                "language": "zh-CN",
                "items_per_page": 20
            }
        }


# 全局配置管理器实例
_config_manager = ConfigManager()


def get_config() -> Dict[str, Any]:
    """获取配置"""
    return _config_manager.load_config()


def get_config_value(key: str, default: Any = None) -> Any:
    """获取配置值"""
    return _config_manager.get(key, default)


def set_config_value(key: str, value: Any) -> bool:
    """设置配置值"""
    return _config_manager.set(key, value)


def reload_config() -> Dict[str, Any]:
    """重新加载配置"""
    _config_manager._config = None
    return _config_manager.load_config() 