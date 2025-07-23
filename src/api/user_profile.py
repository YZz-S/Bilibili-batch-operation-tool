# -*- coding: utf-8 -*-
"""
用户画像分析API路由
User Profile Analysis API Router

提供用户画像分析和推荐相关的API接口
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import json
from collections import defaultdict, Counter
import math

# 从Request对象获取数据库管理器，避免循环导入
from ..bilibili.analyzer import FollowingAnalyzer
from ..recommendation.engine import RecommendationEngine, InterestAnalyzer
from ..core.logger import get_logger

router = APIRouter()
logger = get_logger()
analyzer = FollowingAnalyzer()
recommendation_engine = RecommendationEngine()
interest_analyzer = InterestAnalyzer()


class UserProfileResponse(BaseModel):
    """用户画像响应模型"""
    user_id: Optional[str] = None
    total_following: int
    category_distribution: Dict[str, int]
    interest_scores: Dict[str, float]
    top_interests: List[Dict[str, Any]]
    activity_level: str
    profile_tags: List[str]
    last_updated: str


class FollowSuggestionResponse(BaseModel):
    """关注建议响应模型"""
    suggested_categories: List[Dict[str, Any]]
    recommended_users: List[Dict[str, Any]]
    diversity_score: float
    suggestion_reason: str


class InterestTagsResponse(BaseModel):
    """兴趣标签响应模型"""
    primary_tags: List[str]
    secondary_tags: List[str]
    emerging_tags: List[str]
    tag_weights: Dict[str, float]


class PreferenceTrendResponse(BaseModel):
    """偏好趋势响应模型"""
    trend_data: List[Dict[str, Any]]
    trend_direction: str
    stability_score: float
    prediction: Dict[str, Any]


class InterestEvolutionResponse(BaseModel):
    """兴趣演化响应模型"""
    evolution_data: List[Dict[str, Any]]
    stability_score: float
    emerging_interests: List[str]
    future_prediction: Dict[str, Any]


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(request: Request):
    """
    获取用户画像分析
    
    分析用户关注的UP主类别分布，计算兴趣偏好得分，
    生成用户画像标签和活跃度评估
    """
    try:
        db_manager = request.app.state.db_manager
        
        # 获取所有关注用户数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 分析类别分布
        category_distribution = defaultdict(int)
        total_following = len(following_users)
        
        for user in following_users:
            category = user.get('category', '未分类')
            category_distribution[category] += 1
        
        # 计算兴趣得分（基于关注数量和权重）
        interest_scores = {}
        category_weights = {
            '科技': 1.2,
            '游戏': 1.1,
            '知识': 1.3,
            '生活': 1.0,
            '娱乐': 0.9,
            '音乐': 1.1,
            '美食': 1.0,
            '时尚': 0.9,
            '体育': 1.0,
            '动画': 1.1,
            '影视': 1.0,
            '其他': 0.8
        }
        
        for category, count in category_distribution.items():
            weight = category_weights.get(category, 1.0)
            score = (count / total_following) * weight * 100
            interest_scores[category] = round(score, 2)
        
        # 获取前5个兴趣
        top_interests = [
            {
                'category': category,
                'score': score,
                'count': category_distribution[category],
                'percentage': round((category_distribution[category] / total_following) * 100, 1)
            }
            for category, score in sorted(interest_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
        
        # 计算活跃度等级
        activity_level = _calculate_activity_level(total_following)
        
        # 生成画像标签
        profile_tags = _generate_profile_tags(category_distribution, total_following)
        
        return UserProfileResponse(
            total_following=total_following,
            category_distribution=dict(category_distribution),
            interest_scores=interest_scores,
            top_interests=top_interests,
            activity_level=activity_level,
            profile_tags=profile_tags,
            last_updated=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"获取用户画像失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取用户画像失败: {str(e)}")


@router.get("/suggestions", response_model=FollowSuggestionResponse)
async def get_follow_suggestions(request: Request):
    """
    获取关注建议
    
    基于用户当前的关注分布，推荐可能感兴趣的类别和用户
    """
    try:
        db_manager = request.app.state.db_manager
        
        # 获取用户画像
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 分析当前分布
        category_distribution = defaultdict(int)
        for user in following_users:
            category = user.get('category', '未分类')
            category_distribution[category] += 1
        
        total_following = len(following_users)
        
        # 使用推荐引擎计算多样性得分
        diversity_score = await recommendation_engine.calculate_diversity_score(category_distribution)
        
        # 准备用户数据
        user_data = {
            'category_distribution': category_distribution,
            'total_following': total_following,
            'top_interests': [
                {
                    'category': category,
                    'count': count,
                    'percentage': round((count / total_following) * 100, 1)
                }
                for category, count in sorted(category_distribution.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
        }
        
        # 使用推荐引擎生成建议
        suggested_categories = await recommendation_engine.get_category_recommendations(user_data)
        recommended_users = await recommendation_engine.get_user_recommendations(user_data)
        suggestion_reason = recommendation_engine.generate_suggestion_reason(diversity_score, category_distribution)
        
        return FollowSuggestionResponse(
            suggested_categories=suggested_categories,
            recommended_users=recommended_users,
            diversity_score=diversity_score,
            suggestion_reason=suggestion_reason
        )
        
    except Exception as e:
        logger.error(f"获取关注建议失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取关注建议失败: {str(e)}")


@router.get("/interest-tags", response_model=InterestTagsResponse)
async def get_interest_tags(request: Request):
    """
    获取兴趣标签分析
    
    基于关注分布生成主要、次要和新兴兴趣标签
    """
    try:
        db_manager = request.app.state.db_manager
        
        # 获取关注数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 分析标签
        category_distribution = defaultdict(int)
        for user in following_users:
            category = user.get('category', '未分类')
            category_distribution[category] += 1
        
        total_following = len(following_users)
        
        # 计算标签权重
        tag_weights = {}
        for category, count in category_distribution.items():
            weight = count / total_following
            tag_weights[category] = round(weight, 3)
        
        # 分类标签
        sorted_tags = sorted(tag_weights.items(), key=lambda x: x[1], reverse=True)
        
        primary_tags = [tag for tag, weight in sorted_tags if weight >= 0.15][:3]
        secondary_tags = [tag for tag, weight in sorted_tags if 0.05 <= weight < 0.15][:5]
        emerging_tags = [tag for tag, weight in sorted_tags if 0.02 <= weight < 0.05][:3]
        
        return InterestTagsResponse(
            primary_tags=primary_tags,
            secondary_tags=secondary_tags,
            emerging_tags=emerging_tags,
            tag_weights=tag_weights
        )
        
    except Exception as e:
        logger.error(f"获取兴趣标签失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取兴趣标签失败: {str(e)}")


@router.get("/preference-trends", response_model=PreferenceTrendResponse)
async def get_preference_trends(request: Request, days: int = 30):
    """
    获取偏好趋势分析
    
    分析用户关注偏好的变化趋势（基于关注时间）
    """
    try:
        db_manager = request.app.state.db_manager
        
        # 获取带时间戳的关注数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 模拟趋势数据（实际应用中需要真实的时间序列数据）
        trend_data = _generate_trend_data(following_users, days)
        
        # 计算趋势方向
        trend_direction = _calculate_trend_direction(trend_data)
        
        # 计算稳定性得分
        stability_score = _calculate_stability_score(trend_data)
        
        # 生成预测
        prediction = _generate_prediction(trend_data)
        
        return PreferenceTrendResponse(
            trend_data=trend_data,
            trend_direction=trend_direction,
            stability_score=stability_score,
            prediction=prediction
        )
        
    except Exception as e:
        logger.error(f"获取偏好趋势失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取偏好趋势失败: {str(e)}")


@router.get("/interest-evolution", response_model=InterestEvolutionResponse)
async def get_interest_evolution(request: Request, days: int = 30):
    """
    获取兴趣演化分析
    
    分析用户兴趣的演化趋势，识别新兴兴趣和预测未来发展
    """
    try:
        db_manager = request.app.state.db_manager
        
        # 获取用户数据
        following_users = await db_manager.get_following_list()
        
        if not following_users:
            raise HTTPException(status_code=404, detail="未找到关注数据")
        
        # 分析类别分布
        category_distribution = defaultdict(int)
        for user in following_users:
            category = user.get('category', '未分类')
            category_distribution[category] += 1
        
        total_following = len(following_users)
        
        # 准备用户数据
        user_data = {
            'category_distribution': dict(category_distribution),
            'total_following': total_following
        }
        
        # 使用兴趣分析器进行演化分析
        evolution_result = await interest_analyzer.analyze_interest_evolution(user_data, days)
        
        return InterestEvolutionResponse(
            evolution_data=evolution_result.get('evolution_data', []),
            stability_score=evolution_result.get('stability_score', 0.0),
            emerging_interests=evolution_result.get('emerging_interests', []),
            future_prediction=evolution_result.get('future_prediction', {})
        )
        
    except Exception as e:
        logger.error(f"获取兴趣演化分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取兴趣演化分析失败: {str(e)}")


def _calculate_activity_level(total_following: int) -> str:
    """计算活跃度等级"""
    if total_following >= 500:
        return "高度活跃"
    elif total_following >= 200:
        return "中度活跃"
    elif total_following >= 50:
        return "轻度活跃"
    else:
        return "低活跃"


def _generate_profile_tags(category_distribution: Dict[str, int], total_following: int) -> List[str]:
    """生成用户画像标签"""
    tags = []
    
    # 基于主要兴趣生成标签
    sorted_categories = sorted(category_distribution.items(), key=lambda x: x[1], reverse=True)
    
    if sorted_categories:
        top_category = sorted_categories[0][0]
        top_percentage = (sorted_categories[0][1] / total_following) * 100
        
        if top_percentage >= 30:
            tags.append(f"{top_category}爱好者")
        
        if len(sorted_categories) >= 3 and sorted_categories[2][1] / total_following >= 0.1:
            tags.append("兴趣广泛")
        
        if total_following >= 300:
            tags.append("资深用户")
        elif total_following >= 100:
            tags.append("活跃用户")
    
    # 基于多样性生成标签
    diversity = len([cat for cat, count in category_distribution.items() if count >= 3])
    if diversity >= 5:
        tags.append("多元化关注")
    
    return tags[:5]  # 最多返回5个标签


def _calculate_diversity_score(category_distribution: Dict[str, int], total_following: int) -> float:
    """计算关注多样性得分"""
    if total_following == 0:
        return 0.0
    
    # 使用香农熵计算多样性
    entropy = 0.0
    for count in category_distribution.values():
        if count > 0:
            p = count / total_following
            entropy -= p * math.log2(p)
    
    # 标准化到0-100分
    max_entropy = math.log2(len(category_distribution)) if category_distribution else 1
    diversity_score = (entropy / max_entropy) * 100 if max_entropy > 0 else 0
    
    return round(diversity_score, 2)


def _generate_category_suggestions(category_distribution: Dict[str, int], total_following: int) -> List[Dict[str, Any]]:
    """生成类别建议"""
    suggestions = []
    
    # 定义理想分布（可配置）
    ideal_distribution = {
        '知识': 0.25,
        '科技': 0.15,
        '生活': 0.15,
        '娱乐': 0.15,
        '游戏': 0.10,
        '音乐': 0.10,
        '其他': 0.10
    }
    
    current_distribution = {cat: count/total_following for cat, count in category_distribution.items()}
    
    for category, ideal_ratio in ideal_distribution.items():
        current_ratio = current_distribution.get(category, 0)
        gap = ideal_ratio - current_ratio
        
        if gap > 0.05:  # 如果差距超过5%
            suggestions.append({
                'category': category,
                'current_percentage': round(current_ratio * 100, 1),
                'suggested_percentage': round(ideal_ratio * 100, 1),
                'gap': round(gap * 100, 1),
                'priority': 'high' if gap > 0.15 else 'medium'
            })
    
    return sorted(suggestions, key=lambda x: x['gap'], reverse=True)[:5]


def _generate_user_recommendations(category_distribution: Dict[str, int]) -> List[Dict[str, Any]]:
    """生成用户推荐（模拟数据）"""
    # 这里返回模拟的推荐用户，实际应用中需要连接真实的推荐算法
    recommendations = [
        {
            'uid': 'demo_001',
            'name': '推荐UP主1',
            'category': '科技',
            'reason': '基于您对科技类内容的兴趣',
            'confidence': 0.85
        },
        {
            'uid': 'demo_002', 
            'name': '推荐UP主2',
            'category': '知识',
            'reason': '丰富您的知识类关注',
            'confidence': 0.78
        }
    ]
    
    return recommendations


def _generate_suggestion_reason(diversity_score: float, category_distribution: Dict[str, int]) -> str:
    """生成建议原因"""
    if diversity_score < 30:
        return "您的关注比较集中，建议增加其他类别的关注以丰富内容体验"
    elif diversity_score > 80:
        return "您的关注非常多样化，建议在感兴趣的领域深入关注优质创作者"
    else:
        return "您的关注分布较为均衡，建议根据个人兴趣适当调整关注重点"


def _generate_trend_data(following_users: List[Dict], days: int) -> List[Dict[str, Any]]:
    """生成趋势数据（模拟）"""
    # 模拟最近30天的趋势数据
    trend_data = []
    base_date = datetime.now() - timedelta(days=days)
    
    for i in range(days):
        date = base_date + timedelta(days=i)
        # 模拟数据，实际应用中需要真实的时间序列分析
        trend_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'new_follows': max(0, int(5 + 3 * math.sin(i * 0.2))),
            'category_changes': max(0, int(2 + math.sin(i * 0.3))),
            'diversity_score': max(30, min(90, 60 + 10 * math.sin(i * 0.1)))
        })
    
    return trend_data


def _calculate_trend_direction(trend_data: List[Dict[str, Any]]) -> str:
    """计算趋势方向"""
    if len(trend_data) < 2:
        return "稳定"
    
    recent_avg = sum(item['diversity_score'] for item in trend_data[-7:]) / 7
    earlier_avg = sum(item['diversity_score'] for item in trend_data[:7]) / 7
    
    diff = recent_avg - earlier_avg
    
    if diff > 5:
        return "上升"
    elif diff < -5:
        return "下降"
    else:
        return "稳定"


def _calculate_stability_score(trend_data: List[Dict[str, Any]]) -> float:
    """计算稳定性得分"""
    if len(trend_data) < 2:
        return 100.0
    
    scores = [item['diversity_score'] for item in trend_data]
    avg_score = sum(scores) / len(scores)
    variance = sum((score - avg_score) ** 2 for score in scores) / len(scores)
    
    # 将方差转换为稳定性得分（0-100）
    stability = max(0, 100 - variance)
    return round(stability, 2)


def _generate_prediction(trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """生成预测"""
    if len(trend_data) < 7:
        return {'message': '数据不足，无法生成预测'}
    
    recent_trend = [item['diversity_score'] for item in trend_data[-7:]]
    avg_recent = sum(recent_trend) / len(recent_trend)
    
    return {
        'next_week_diversity': round(avg_recent + (recent_trend[-1] - recent_trend[0]) * 0.3, 1),
        'confidence': 0.75,
        'recommendation': '建议继续保持当前的关注策略' if 50 <= avg_recent <= 80 else '建议调整关注分布以获得更好的内容体验'
    }