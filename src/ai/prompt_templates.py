# -*- coding: utf-8 -*-
"""
AI提示词模板模块
AI Prompt Templates Module

提供各种AI分析任务的提示词模板
"""

from typing import Dict, Any, List


class PromptTemplates:
    """AI提示词模板类"""
    
    # 系统提示词
    SYSTEM_PROMPT = """
你是一个专业的用户画像分析师，擅长从用户的关注行为中分析其兴趣偏好、性格特征和内容消费习惯。
请基于提供的数据进行深度分析，给出专业、准确、有洞察力的分析结果。
回复格式要求：使用JSON格式，包含具体的分析维度和结果。
"""
    
    # 标签生成系统提示词
    TAG_SYSTEM_PROMPT = """
你是一个智能标签生成专家，能够根据用户的关注数据生成精准的兴趣标签。
请生成主要标签、次要标签和新兴标签，并给出标签权重。
回复格式：JSON格式，包含不同层级的标签分类。
"""
    
    # 推荐系统提示词
    RECOMMENDATION_SYSTEM_PROMPT = """
你是一个个性化推荐专家，能够基于用户画像提供精准的内容和关注推荐。
请分析用户的兴趣缺口，推荐合适的内容类别和创作者类型。
回复格式：JSON格式，包含推荐理由和具体建议。
"""
    
    # 报告生成系统提示词
    REPORT_SYSTEM_PROMPT = """
你是一个专业的数据分析报告撰写专家，能够将复杂的用户数据转化为易懂的自然语言报告。
请生成一份详细的用户画像分析报告，包含关键发现、行为模式和建议。
语言要求：中文，专业但易懂，结构清晰。
"""
    
    def get_user_profile_prompt(self, analysis_data: Dict[str, Any]) -> str:
        """获取用户画像分析提示词"""
        total_following = analysis_data.get('total_following', 0)
        category_distribution = analysis_data.get('category_distribution', {})
        top_categories = analysis_data.get('top_categories', [])
        sample_users = analysis_data.get('sample_users', [])
        
        prompt = f"""
请分析以下用户的关注数据，生成详细的用户画像：

基础数据：
- 总关注数：{total_following}
- 类别分布：{dict(category_distribution)}
- 主要兴趣类别：{[cat[0] for cat in top_categories[:3]]}

样本关注用户（前10个）：
"""
        
        for i, user in enumerate(sample_users[:5], 1):
            prompt += f"{i}. {user.get('name', '未知')} - {user.get('category', '未分类')}\n"
        
        prompt += """

请从以下维度进行分析，并以JSON格式返回结果：
{
  "personality_traits": ["性格特征1", "性格特征2", "性格特征3"],
  "interest_depth": "deep/medium/shallow",
  "activity_pattern": "active/regular/inactive",
  "content_preference": ["偏好类型1", "偏好类型2"],
  "growth_potential": "high/medium/low",
  "behavioral_insights": "行为洞察描述",
  "recommendation_direction": "推荐方向建议"
}

分析要点：
1. 根据关注类别分布判断兴趣广度和深度
2. 分析用户的内容消费偏好
3. 评估用户的活跃度和成长潜力
4. 提供个性化的发展建议
"""
        
        return prompt
    
    def get_interest_tags_prompt(self, user_data: Dict[str, Any]) -> str:
        """获取兴趣标签生成提示词"""
        category_distribution = user_data.get('category_distribution', {})
        total_following = user_data.get('total_following', 0)
        
        prompt = f"""
基于以下用户关注数据，生成精准的兴趣标签：

关注数据：
- 总关注数：{total_following}
- 类别分布：{dict(category_distribution)}

请生成以下格式的标签分类（JSON格式）：
{
  "primary_tags": ["核心兴趣标签1", "核心兴趣标签2", "核心兴趣标签3"],
  "secondary_tags": ["次要兴趣标签1", "次要兴趣标签2"],
  "emerging_tags": ["新兴兴趣标签1", "新兴兴趣标签2"],
  "tag_weights": {
    "标签1": 0.8,
    "标签2": 0.6,
    "标签3": 0.4
  },
  "tag_explanations": {
    "标签1": "标签含义解释",
    "标签2": "标签含义解释"
  }
}

标签生成要求：
1. 主要标签：反映用户最核心的3-4个兴趣领域
2. 次要标签：用户有一定关注但不是主要兴趣的领域
3. 新兴标签：基于数据推测的潜在兴趣方向
4. 标签权重：0-1之间，反映兴趣强度
5. 标签要具体、准确、有区分度
"""
        
        return prompt
    
    def get_recommendation_prompt(self, user_data: Dict[str, Any]) -> str:
        """获取推荐生成提示词"""
        category_distribution = user_data.get('category_distribution', {})
        total_following = user_data.get('total_following', 0)
        
        # 计算多样性得分
        diversity_score = len(category_distribution) / max(total_following, 1) * 100
        
        prompt = f"""
基于用户画像数据，生成个性化推荐：

用户数据：
- 总关注数：{total_following}
- 类别分布：{dict(category_distribution)}
- 多样性得分：{diversity_score:.1f}%

请生成以下格式的推荐结果（JSON格式）：
{
  "category_recommendations": [
    {
      "category": "推荐类别名",
      "reason": "推荐理由",
      "priority": "high/medium/low"
    }
  ],
  "content_recommendations": [
    {
      "type": "内容类型",
      "description": "内容描述",
      "examples": ["示例1", "示例2"]
    }
  ],
  "follow_suggestions": [
    {
      "creator_type": "创作者类型",
      "characteristics": "特征描述",
      "benefit": "关注收益"
    }
  ],
  "optimization_advice": {
    "diversity_improvement": "多样性提升建议",
    "quality_enhancement": "质量优化建议",
    "engagement_tips": "互动建议"
  }
}

推荐策略：
1. 分析用户兴趣缺口，推荐互补类别
2. 基于现有偏好，推荐相关优质内容
3. 考虑用户成长需求，推荐提升类内容
4. 平衡娱乐性和教育性内容
"""
        
        return prompt
    
    def get_report_prompt(self, user_data: Dict[str, Any]) -> str:
        """获取分析报告生成提示词"""
        category_distribution = user_data.get('category_distribution', {})
        total_following = user_data.get('total_following', 0)
        
        # 获取主要类别
        top_categories = sorted(category_distribution.items(), key=lambda x: x[1], reverse=True)[:3]
        
        prompt = f"""
请为以下用户生成一份详细的画像分析报告：

用户数据概览：
- 总关注数：{total_following}
- 主要兴趣类别：{[cat[0] for cat in top_categories]}
- 类别分布：{dict(category_distribution)}

请生成一份结构化的中文分析报告，包含以下部分：

1. **用户画像概述**
   - 用户类型定义
   - 核心特征总结

2. **兴趣偏好分析**
   - 主要兴趣领域
   - 兴趣深度评估
   - 内容偏好特点

3. **行为模式洞察**
   - 关注行为特征
   - 内容消费习惯
   - 活跃度评估

4. **成长潜力评估**
   - 学习能力分析
   - 兴趣拓展可能性
   - 内容创作潜力

5. **个性化建议**
   - 内容推荐方向
   - 关注优化建议
   - 个人发展建议

报告要求：
- 语言专业但易懂
- 结构清晰，逻辑性强
- 提供具体可行的建议
- 字数控制在800-1200字
- 避免过于技术性的术语
"""
        
        return prompt
    
    def get_trend_analysis_prompt(self, trend_data: List[Dict[str, Any]]) -> str:
        """获取趋势分析提示词"""
        prompt = f"""
基于以下时间序列数据，分析用户兴趣变化趋势：

趋势数据：{trend_data}

请分析并返回JSON格式结果：
{
  "trend_direction": "上升/下降/稳定/波动",
  "key_changes": ["变化点1", "变化点2"],
  "stability_score": 0.85,
  "future_prediction": {
    "direction": "预测方向",
    "confidence": 0.75,
    "reasoning": "预测理由"
  },
  "recommendations": ["建议1", "建议2"]
}

分析要点：
1. 识别关键变化节点
2. 评估趋势稳定性
3. 预测未来发展方向
4. 提供优化建议
"""
        
        return prompt