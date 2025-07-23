# -*- coding: utf-8 -*-
"""
AI分析引擎模块
AI Analysis Engine Module

提供AI驱动的用户画像深度分析和智能推荐
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter

from .llm_service import llm_service
from .prompt_templates import PromptTemplates
from ..core.logger import get_logger

logger = get_logger()


class AIAnalysisEngine:
    """AI分析引擎"""
    
    def __init__(self):
        self.prompt_templates = PromptTemplates()
    
    async def analyze_user_profile(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI驱动的用户画像深度分析"""
        try:
            if not llm_service.is_configured():
                return self._fallback_analysis(user_data)
            
            # 准备分析数据
            analysis_data = self._prepare_analysis_data(user_data)
            
            # 构建提示词
            prompt = self.prompt_templates.get_user_profile_prompt(analysis_data)
            
            # 调用AI分析
            messages = [
                {'role': 'system', 'content': self.prompt_templates.SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt}
            ]
            
            response = await llm_service.chat(messages)
            
            # 解析AI响应
            ai_analysis = self._parse_ai_response(response)
            
            # 合并基础分析和AI分析
            return self._merge_analysis_results(user_data, ai_analysis)
            
        except Exception as e:
            logger.error(f"AI用户画像分析失败: {str(e)}")
            return self._fallback_analysis(user_data)
    
    async def generate_interest_tags(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成智能兴趣标签"""
        try:
            if not llm_service.is_configured():
                return self._fallback_tags(user_data)
            
            # 构建标签生成提示词
            prompt = self.prompt_templates.get_interest_tags_prompt(user_data)
            
            messages = [
                {'role': 'system', 'content': self.prompt_templates.TAG_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt}
            ]
            
            response = await llm_service.chat(messages)
            
            # 解析标签响应
            tags_data = self._parse_tags_response(response)
            
            return tags_data
            
        except Exception as e:
            logger.error(f"AI兴趣标签生成失败: {str(e)}")
            return self._fallback_tags(user_data)
    
    async def generate_recommendations(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成智能推荐"""
        try:
            if not llm_service.is_configured():
                return self._fallback_recommendations(user_data)
            
            # 构建推荐提示词
            prompt = self.prompt_templates.get_recommendation_prompt(user_data)
            
            messages = [
                {'role': 'system', 'content': self.prompt_templates.RECOMMENDATION_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt}
            ]
            
            response = await llm_service.chat(messages)
            
            # 解析推荐响应
            recommendations = self._parse_recommendations_response(response)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"AI推荐生成失败: {str(e)}")
            return self._fallback_recommendations(user_data)
    
    async def generate_analysis_report(self, user_data: Dict[str, Any]) -> str:
        """生成自然语言分析报告"""
        try:
            if not llm_service.is_configured():
                return self._fallback_report(user_data)
            
            # 构建报告生成提示词
            prompt = self.prompt_templates.get_report_prompt(user_data)
            
            messages = [
                {'role': 'system', 'content': self.prompt_templates.REPORT_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt}
            ]
            
            response = await llm_service.chat(messages, max_tokens=2000)
            
            return response or self._fallback_report(user_data)
            
        except Exception as e:
            logger.error(f"AI分析报告生成失败: {str(e)}")
            return self._fallback_report(user_data)
    
    def _prepare_analysis_data(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """准备分析数据"""
        following_users = user_data.get('following_users', [])
        category_distribution = user_data.get('category_distribution', {})
        
        # 计算统计信息
        total_following = len(following_users)
        top_categories = sorted(category_distribution.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 分析关注时间分布
        follow_times = []
        for user in following_users:
            if user.get('follow_time'):
                follow_times.append(user['follow_time'])
        
        return {
            'total_following': total_following,
            'category_distribution': category_distribution,
            'top_categories': top_categories,
            'follow_times': follow_times,
            'sample_users': following_users[:10]  # 取样本用户
        }
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """解析AI响应"""
        try:
            # 尝试解析JSON格式的响应
            if '{' in response and '}' in response:
                start = response.find('{')
                end = response.rfind('}') + 1
                json_str = response[start:end]
                return json.loads(json_str)
            
            # 如果不是JSON格式，进行文本解析
            return self._parse_text_response(response)
            
        except Exception as e:
            logger.warning(f"解析AI响应失败: {str(e)}")
            return {'analysis': response}
    
    def _parse_text_response(self, response: str) -> Dict[str, Any]:
        """解析文本格式的AI响应"""
        lines = response.strip().split('\n')
        result = {
            'personality_traits': [],
            'interest_depth': 'medium',
            'activity_pattern': 'regular',
            'content_preference': [],
            'growth_potential': 'high'
        }
        
        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if '性格特征' in line or '个性特点' in line:
                current_section = 'personality_traits'
            elif '兴趣深度' in line:
                if '深' in line:
                    result['interest_depth'] = 'deep'
                elif '浅' in line:
                    result['interest_depth'] = 'shallow'
            elif '活动模式' in line or '活跃模式' in line:
                if '高频' in line or '活跃' in line:
                    result['activity_pattern'] = 'active'
                elif '低频' in line or '不活跃' in line:
                    result['activity_pattern'] = 'inactive'
            elif current_section == 'personality_traits' and ('·' in line or '-' in line or '•' in line):
                trait = line.replace('·', '').replace('-', '').replace('•', '').strip()
                if trait:
                    result['personality_traits'].append(trait)
        
        return result
    
    def _parse_tags_response(self, response: str) -> Dict[str, Any]:
        """解析标签响应"""
        try:
            if '{' in response and '}' in response:
                start = response.find('{')
                end = response.rfind('}') + 1
                json_str = response[start:end]
                return json.loads(json_str)
            
            # 文本解析
            lines = response.strip().split('\n')
            result = {
                'primary_tags': [],
                'secondary_tags': [],
                'emerging_tags': [],
                'tag_weights': {}
            }
            
            current_section = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if '主要标签' in line or '核心标签' in line:
                    current_section = 'primary_tags'
                elif '次要标签' in line or '辅助标签' in line:
                    current_section = 'secondary_tags'
                elif '新兴标签' in line or '潜在标签' in line:
                    current_section = 'emerging_tags'
                elif current_section and ('·' in line or '-' in line or '•' in line):
                    tag = line.replace('·', '').replace('-', '').replace('•', '').strip()
                    if tag and current_section in result:
                        result[current_section].append(tag)
            
            return result
            
        except Exception as e:
            logger.warning(f"解析标签响应失败: {str(e)}")
            return {'primary_tags': [], 'secondary_tags': [], 'emerging_tags': [], 'tag_weights': {}}
    
    def _parse_recommendations_response(self, response: str) -> Dict[str, Any]:
        """解析推荐响应"""
        try:
            if '{' in response and '}' in response:
                start = response.find('{')
                end = response.rfind('}') + 1
                json_str = response[start:end]
                return json.loads(json_str)
            
            return {
                'category_recommendations': [],
                'content_recommendations': [],
                'follow_suggestions': [],
                'reasoning': response
            }
            
        except Exception as e:
            logger.warning(f"解析推荐响应失败: {str(e)}")
            return {'category_recommendations': [], 'content_recommendations': [], 'follow_suggestions': [], 'reasoning': response}
    
    def _merge_analysis_results(self, user_data: Dict[str, Any], ai_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """合并基础分析和AI分析结果"""
        result = user_data.copy()
        
        # 添加AI分析结果
        result['ai_analysis'] = ai_analysis
        result['enhanced'] = True
        result['analysis_time'] = datetime.now().isoformat()
        
        # 增强现有字段
        if 'personality_traits' in ai_analysis:
            result['personality_traits'] = ai_analysis['personality_traits']
        
        if 'interest_depth' in ai_analysis:
            result['interest_depth'] = ai_analysis['interest_depth']
        
        if 'activity_pattern' in ai_analysis:
            result['activity_pattern'] = ai_analysis['activity_pattern']
        
        return result
    
    def _fallback_analysis(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """回退分析（当AI不可用时）"""
        category_distribution = user_data.get('category_distribution', {})
        total_following = user_data.get('total_following', 0)
        
        # 基础分析
        top_category = max(category_distribution.items(), key=lambda x: x[1])[0] if category_distribution else '未知'
        diversity_score = len(category_distribution) / max(total_following, 1) * 100
        
        return {
            'enhanced': False,
            'personality_traits': [f'{top_category}爱好者', '内容消费者'],
            'interest_depth': 'medium' if diversity_score > 20 else 'shallow',
            'activity_pattern': 'regular',
            'content_preference': list(category_distribution.keys())[:3],
            'growth_potential': 'medium',
            'analysis_time': datetime.now().isoformat()
        }
    
    def _fallback_tags(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """回退标签生成"""
        category_distribution = user_data.get('category_distribution', {})
        
        primary_tags = list(category_distribution.keys())[:3]
        secondary_tags = list(category_distribution.keys())[3:6]
        
        return {
            'primary_tags': primary_tags,
            'secondary_tags': secondary_tags,
            'emerging_tags': [],
            'tag_weights': {tag: 1.0 for tag in primary_tags}
        }
    
    def _fallback_recommendations(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """回退推荐生成"""
        category_distribution = user_data.get('category_distribution', {})
        
        # 推荐缺少的热门类别
        popular_categories = ['科技', '游戏', '知识', '生活', '娱乐']
        missing_categories = [cat for cat in popular_categories if cat not in category_distribution]
        
        return {
            'category_recommendations': missing_categories[:3],
            'content_recommendations': ['优质内容创作者', '知识分享者', '技术博主'],
            'follow_suggestions': [],
            'reasoning': '基于热门类别的基础推荐'
        }
    
    def _fallback_report(self, user_data: Dict[str, Any]) -> str:
        """回退分析报告"""
        total_following = user_data.get('total_following', 0)
        category_distribution = user_data.get('category_distribution', {})
        
        top_category = max(category_distribution.items(), key=lambda x: x[1])[0] if category_distribution else '未知'
        
        return f"""用户画像分析报告

您当前关注了 {total_following} 个UP主，主要兴趣集中在 {top_category} 领域。

从关注分布来看，您是一个对 {top_category} 内容有较强偏好的用户。建议您可以：
1. 探索更多 {top_category} 相关的优质创作者
2. 适当关注其他领域，增加内容多样性
3. 定期整理关注列表，保持内容质量

注：此为基础分析报告，启用AI功能后可获得更详细的个性化分析。"""


# 全局AI分析引擎实例
ai_analysis_engine = AIAnalysisEngine()