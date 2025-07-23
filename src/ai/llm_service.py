# -*- coding: utf-8 -*-
"""
LLM服务管理模块
LLM Service Management Module

支持多种大语言模型API的统一调用接口
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import aiohttp
from datetime import datetime

from ..core.logger import get_logger
from ..core.config import ConfigManager

logger = get_logger()


class LLMProvider(Enum):
    """支持的LLM提供商"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    QWEN = "qwen"


class LLMConfig:
    """LLM配置类"""
    
    def __init__(self, provider: LLMProvider, api_key: str, base_url: str = None, model: str = None):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url or self._get_default_base_url(provider)
        self.model = model or self._get_default_model(provider)
        self.max_tokens = 4000
        self.temperature = 0.7
        self.timeout = 30
    
    def _get_default_base_url(self, provider: LLMProvider) -> str:
        """获取默认API地址"""
        urls = {
            LLMProvider.DEEPSEEK: "https://api.deepseek.com",
            LLMProvider.OPENAI: "https://api.openai.com/v1",
            LLMProvider.CLAUDE: "https://api.anthropic.com",
            LLMProvider.GEMINI: "https://generativelanguage.googleapis.com/v1",
            LLMProvider.QWEN: "https://dashscope.aliyuncs.com/api/v1"
        }
        return urls.get(provider, "")
    
    def _get_default_model(self, provider: LLMProvider) -> str:
        """获取默认模型"""
        models = {
            LLMProvider.DEEPSEEK: "deepseek-chat",
            LLMProvider.OPENAI: "gpt-3.5-turbo",
            LLMProvider.CLAUDE: "claude-3-sonnet-20240229",
            LLMProvider.GEMINI: "gemini-pro",
            LLMProvider.QWEN: "qwen-turbo"
        }
        return models.get(provider, "")


class LLMService:
    """LLM服务管理类"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_config: Optional[LLMConfig] = None
        self._load_config()
    
    def _load_config(self):
        """加载AI配置"""
        try:
            ai_config = self.config_manager.get('ai', {})
            if ai_config.get('enabled', False):
                provider = LLMProvider(ai_config.get('provider', 'deepseek'))
                api_key = ai_config.get('api_key', '')
                base_url = ai_config.get('base_url')
                model = ai_config.get('model')
                
                if api_key:
                    self.current_config = LLMConfig(provider, api_key, base_url, model)
                    self.current_config.max_tokens = ai_config.get('max_tokens', 4000)
                    self.current_config.temperature = ai_config.get('temperature', 0.7)
                    self.current_config.timeout = ai_config.get('timeout', 30)
                    logger.info(f"AI配置加载成功: {provider.value}")
        except Exception as e:
            logger.error(f"加载AI配置失败: {str(e)}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取HTTP会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.current_config.timeout if self.current_config else 30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return self.current_config is not None and bool(self.current_config.api_key)
    
    def get_config_info(self) -> Dict[str, Any]:
        """获取配置信息"""
        if not self.current_config:
            return {'configured': False}
        
        return {
            'configured': True,
            'provider': self.current_config.provider.value,
            'model': self.current_config.model,
            'max_tokens': self.current_config.max_tokens,
            'temperature': self.current_config.temperature
        }
    
    async def update_config(self, config_data: Dict[str, Any]) -> bool:
        """更新配置"""
        try:
            # 验证配置
            provider = LLMProvider(config_data.get('provider', 'deepseek'))
            api_key = config_data.get('api_key', '').strip()
            
            if not api_key:
                raise ValueError("API密钥不能为空")
            
            # 更新配置文件
            ai_config = {
                'enabled': config_data.get('enabled', True),
                'provider': provider.value,
                'api_key': api_key,
                'base_url': config_data.get('base_url', '').strip() or None,
                'model': config_data.get('model', '').strip() or None,
                'max_tokens': int(config_data.get('max_tokens', 4000)),
                'temperature': float(config_data.get('temperature', 0.7)),
                'timeout': int(config_data.get('timeout', 30))
            }
            
            self.config_manager.set('ai', ai_config)
            self.config_manager.save()
            
            # 重新加载配置
            self._load_config()
            
            logger.info(f"AI配置更新成功: {provider.value}")
            return True
            
        except Exception as e:
            logger.error(f"更新AI配置失败: {str(e)}")
            return False
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        if not self.is_configured():
            return {'success': False, 'error': '未配置AI服务'}
        
        try:
            # 发送简单的测试请求
            response = await self.chat([
                {'role': 'user', 'content': '你好，请回复"连接测试成功"'}
            ])
            
            if response and '连接测试成功' in response:
                return {'success': True, 'message': '连接测试成功'}
            else:
                return {'success': True, 'message': '连接正常，但响应异常'}
                
        except Exception as e:
            logger.error(f"AI连接测试失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        """发送聊天请求"""
        if not self.is_configured():
            raise ValueError("AI服务未配置")
        
        try:
            session = await self._get_session()
            
            # 根据不同提供商构建请求
            if self.current_config.provider == LLMProvider.DEEPSEEK:
                return await self._chat_deepseek(session, messages, **kwargs)
            elif self.current_config.provider == LLMProvider.OPENAI:
                return await self._chat_openai(session, messages, **kwargs)
            else:
                raise ValueError(f"暂不支持的提供商: {self.current_config.provider.value}")
                
        except Exception as e:
            logger.error(f"AI聊天请求失败: {str(e)}")
            raise
    
    async def _chat_deepseek(self, session: aiohttp.ClientSession, messages: List[Dict[str, str]], **kwargs) -> str:
        """DeepSeek API调用"""
        url = f"{self.current_config.base_url}/chat/completions"
        headers = {
            'Authorization': f'Bearer {self.current_config.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.current_config.model,
            'messages': messages,
            'max_tokens': kwargs.get('max_tokens', self.current_config.max_tokens),
            'temperature': kwargs.get('temperature', self.current_config.temperature),
            'stream': False
        }
        
        async with session.post(url, headers=headers, json=data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API请求失败 ({response.status}): {error_text}")
            
            result = await response.json()
            return result['choices'][0]['message']['content']
    
    async def _chat_openai(self, session: aiohttp.ClientSession, messages: List[Dict[str, str]], **kwargs) -> str:
        """OpenAI API调用"""
        url = f"{self.current_config.base_url}/chat/completions"
        headers = {
            'Authorization': f'Bearer {self.current_config.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.current_config.model,
            'messages': messages,
            'max_tokens': kwargs.get('max_tokens', self.current_config.max_tokens),
            'temperature': kwargs.get('temperature', self.current_config.temperature)
        }
        
        async with session.post(url, headers=headers, json=data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API请求失败 ({response.status}): {error_text}")
            
            result = await response.json()
            return result['choices'][0]['message']['content']


# 全局LLM服务实例
llm_service = LLMService()