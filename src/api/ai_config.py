# -*- coding: utf-8 -*-
"""
AI配置API路由
AI Configuration API Router

提供AI模型配置和管理相关的API接口
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..ai.llm_service import llm_service, LLMProvider
from ..ai.analysis_engine import AIAnalysisEngine
from ..core.logger import get_logger

router = APIRouter()
logger = get_logger()
ai_engine = AIAnalysisEngine()


class AIConfigRequest(BaseModel):
    """AI配置请求模型"""
    enabled: bool = True
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.7
    timeout: int = 30


class AIConfigResponse(BaseModel):
    """AI配置响应模型"""
    configured: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    enabled: bool = False
    last_updated: Optional[str] = None


class AITestResponse(BaseModel):
    """AI连接测试响应模型"""
    success: bool
    message: str
    error: Optional[str] = None
    response_time: Optional[float] = None


class AIProvidersResponse(BaseModel):
    """AI提供商列表响应模型"""
    providers: List[Dict[str, Any]]


@router.get("/status", response_model=AIConfigResponse)
async def get_ai_status():
    """
    获取AI配置状态
    
    返回当前AI服务的配置状态和基本信息
    """
    try:
        config_info = llm_service.get_config_info()
        
        return AIConfigResponse(
            configured=config_info.get('configured', False),
            provider=config_info.get('provider'),
            model=config_info.get('model'),
            max_tokens=config_info.get('max_tokens'),
            temperature=config_info.get('temperature'),
            enabled=config_info.get('configured', False),
            last_updated=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"获取AI状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取AI状态失败: {str(e)}")


@router.get("/providers", response_model=AIProvidersResponse)
async def get_ai_providers():
    """
    获取支持的AI提供商列表
    
    返回所有支持的AI模型提供商及其配置信息
    """
    try:
        providers = [
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "description": "DeepSeek AI - 高性价比的中文大语言模型",
                "default_base_url": "https://api.deepseek.com",
                "default_model": "deepseek-chat",
                "supported_models": [
                    {"id": "deepseek-chat", "name": "DeepSeek Chat", "description": "通用对话模型"},
                    {"id": "deepseek-coder", "name": "DeepSeek Coder", "description": "代码专用模型"}
                ],
                "pricing": "¥0.001/1K tokens",
                "features": ["中文优化", "高性价比", "快速响应"]
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "description": "OpenAI GPT系列模型",
                "default_base_url": "https://api.openai.com/v1",
                "default_model": "gpt-3.5-turbo",
                "supported_models": [
                    {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "description": "快速且经济的模型"},
                    {"id": "gpt-4", "name": "GPT-4", "description": "最强大的模型"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "优化版GPT-4"}
                ],
                "pricing": "$0.002/1K tokens",
                "features": ["全球领先", "功能强大", "生态完善"]
            },
            {
                "id": "claude",
                "name": "Anthropic Claude",
                "description": "Anthropic Claude系列模型",
                "default_base_url": "https://api.anthropic.com",
                "default_model": "claude-3-sonnet-20240229",
                "supported_models": [
                    {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet", "description": "平衡性能和成本"},
                    {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "description": "最强性能模型"}
                ],
                "pricing": "$0.003/1K tokens",
                "features": ["安全可靠", "长文本", "推理能力强"]
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "description": "Google Gemini系列模型",
                "default_base_url": "https://generativelanguage.googleapis.com/v1",
                "default_model": "gemini-pro",
                "supported_models": [
                    {"id": "gemini-pro", "name": "Gemini Pro", "description": "专业级模型"},
                    {"id": "gemini-pro-vision", "name": "Gemini Pro Vision", "description": "支持图像理解"}
                ],
                "pricing": "免费额度 + 付费",
                "features": ["多模态", "免费额度", "Google生态"]
            },
            {
                "id": "qwen",
                "name": "阿里云通义千问",
                "description": "阿里云通义千问大语言模型",
                "default_base_url": "https://dashscope.aliyuncs.com/api/v1",
                "default_model": "qwen-turbo",
                "supported_models": [
                    {"id": "qwen-turbo", "name": "通义千问-Turbo", "description": "快速响应模型"},
                    {"id": "qwen-plus", "name": "通义千问-Plus", "description": "增强版模型"},
                    {"id": "qwen-max", "name": "通义千问-Max", "description": "最强性能模型"}
                ],
                "pricing": "¥0.0008/1K tokens",
                "features": ["中文优化", "阿里云生态", "企业级"]
            }
        ]
        
        return AIProvidersResponse(providers=providers)
        
    except Exception as e:
        logger.error(f"获取AI提供商列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取AI提供商列表失败: {str(e)}")


@router.post("/config")
async def update_ai_config(config: AIConfigRequest):
    """
    更新AI配置
    
    更新AI模型提供商、API密钥和相关参数
    """
    try:
        # 验证提供商
        try:
            LLMProvider(config.provider)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"不支持的AI提供商: {config.provider}")
        
        # 验证参数范围
        if not (0.0 <= config.temperature <= 2.0):
            raise HTTPException(status_code=400, detail="temperature参数必须在0.0-2.0之间")
        
        if not (100 <= config.max_tokens <= 32000):
            raise HTTPException(status_code=400, detail="max_tokens参数必须在100-32000之间")
        
        if not (5 <= config.timeout <= 300):
            raise HTTPException(status_code=400, detail="timeout参数必须在5-300秒之间")
        
        # 更新配置
        config_data = {
            'enabled': config.enabled,
            'provider': config.provider,
            'api_key': config.api_key,
            'base_url': config.base_url,
            'model': config.model,
            'max_tokens': config.max_tokens,
            'temperature': config.temperature,
            'timeout': config.timeout
        }
        
        success = await llm_service.update_config(config_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="配置更新失败")
        
        logger.info(f"AI配置更新成功: {config.provider}")
        
        return {
            "success": True,
            "message": "AI配置更新成功",
            "provider": config.provider,
            "model": config.model or f"默认模型",
            "updated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新AI配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新AI配置失败: {str(e)}")


@router.post("/test", response_model=AITestResponse)
async def test_ai_connection():
    """
    测试AI连接
    
    测试当前配置的AI服务是否可用
    """
    try:
        if not llm_service.is_configured():
            return AITestResponse(
                success=False,
                message="AI服务未配置",
                error="请先配置AI模型和API密钥"
            )
        
        # 记录开始时间
        start_time = datetime.now()
        
        # 执行连接测试
        test_result = await llm_service.test_connection()
        
        # 计算响应时间
        response_time = (datetime.now() - start_time).total_seconds()
        
        return AITestResponse(
            success=test_result['success'],
            message=test_result.get('message', '测试完成'),
            error=test_result.get('error'),
            response_time=response_time
        )
        
    except Exception as e:
        logger.error(f"AI连接测试失败: {str(e)}")
        return AITestResponse(
            success=False,
            message="连接测试失败",
            error=str(e)
        )


@router.delete("/config")
async def clear_ai_config():
    """
    清除AI配置
    
    删除当前的AI配置信息
    """
    try:
        # 清除配置
        success = await llm_service.clear_config()
        
        if not success:
            raise HTTPException(status_code=500, detail="配置清除失败")
        
        logger.info("AI配置已清除")
        
        return {
            "success": True,
            "message": "AI配置已清除",
            "cleared_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除AI配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清除AI配置失败: {str(e)}")


# AI智能分析相关端点

@router.get("/profile-analysis")
async def get_profile_analysis(request: Request):
    """
    获取AI用户画像深度分析
    
    基于用户关注数据进行AI驱动的深度分析
    """
    try:
        if not llm_service.is_configured():
            raise HTTPException(status_code=503, detail="AI服务未配置")
        
        db_manager = request.app.state.db_manager
        
        # 获取用户数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 准备分析数据
        user_data = {
            'total_following': len(following_users),
            'following_users': following_users,
            'category_distribution': {},
            'activity_patterns': {},
            'content_preferences': {}
        }
        
        # 分析关注分布
        category_count = {}
        for user in following_users:
            category = user.get('category', '其他')
            category_count[category] = category_count.get(category, 0) + 1
        
        user_data['category_distribution'] = category_count
        
        # 执行AI分析
        analysis_result = await ai_engine.analyze_user_profile(user_data)
        
        return {
            "success": True,
            "data": analysis_result,
            "analyzed_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户画像分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取用户画像分析失败: {str(e)}")


@router.get("/interest-tags")
async def get_interest_tags(request: Request):
    """
    获取AI智能兴趣标签
    
    基于用户关注数据生成智能兴趣标签
    """
    try:
        if not llm_service.is_configured():
            raise HTTPException(status_code=503, detail="AI服务未配置")
        
        db_manager = request.app.state.db_manager
        
        # 获取用户数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 准备分析数据
        user_data = {
            'total_following': len(following_users),
            'following_users': following_users,
            'category_distribution': {}
        }
        
        # 分析关注分布
        category_count = {}
        for user in following_users:
            category = user.get('category', '其他')
            category_count[category] = category_count.get(category, 0) + 1
        
        user_data['category_distribution'] = category_count
        
        # 生成兴趣标签
        tags_result = await ai_engine.generate_interest_tags(user_data)
        
        return {
            "success": True,
            "data": tags_result,
            "generated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取兴趣标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取兴趣标签失败: {str(e)}")


@router.get("/recommendations")
async def get_recommendations(request: Request):
    """
    获取AI智能推荐
    
    基于用户画像生成个性化推荐
    """
    try:
        if not llm_service.is_configured():
            raise HTTPException(status_code=503, detail="AI服务未配置")
        
        db_manager = request.app.state.db_manager
        
        # 获取用户数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 准备分析数据
        user_data = {
            'total_following': len(following_users),
            'following_users': following_users,
            'category_distribution': {},
            'preferences': {}
        }
        
        # 分析关注分布
        category_count = {}
        for user in following_users:
            category = user.get('category', '其他')
            category_count[category] = category_count.get(category, 0) + 1
        
        user_data['category_distribution'] = category_count
        
        # 生成推荐
        recommendations = await ai_engine.generate_recommendations(user_data)
        
        return {
            "success": True,
            "data": recommendations,
            "generated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能推荐失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取智能推荐失败: {str(e)}")


@router.get("/analysis-report")
async def get_analysis_report(request: Request):
    """
    获取AI自然语言分析报告
    
    生成详细的用户画像分析报告
    """
    try:
        if not llm_service.is_configured():
            raise HTTPException(status_code=503, detail="AI服务未配置")
        
        db_manager = request.app.state.db_manager
        
        # 获取用户数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 准备分析数据
        user_data = {
            'total_following': len(following_users),
            'following_users': following_users,
            'category_distribution': {},
            'analysis_date': datetime.now().isoformat()
        }
        
        # 分析关注分布
        category_count = {}
        for user in following_users:
            category = user.get('category', '其他')
            category_count[category] = category_count.get(category, 0) + 1
        
        user_data['category_distribution'] = category_count
        
        # 生成分析报告
        report = await ai_engine.generate_analysis_report(user_data)
        
        return {
            "success": True,
            "data": {
                "report": report,
                "summary": f"基于 {len(following_users)} 个关注用户的深度分析报告",
                "analysis_date": datetime.now().isoformat(),
                "total_following": len(following_users),
                "main_categories": list(category_count.keys())[:5]
            },
            "generated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分析报告失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取分析报告失败: {str(e)}")