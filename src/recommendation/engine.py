# -*- coding: utf-8 -*-
"""
推荐引擎模块
Recommendation Engine Module

提供基于用户行为和内容的推荐算法
"""

import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict, Counter
import math
from datetime import datetime, timedelta
import json

# 数据库管理器通过参数传递，避免循环导入
from ..core.logger import get_logger

logger = get_logger()


class RecommendationEngine:
    """推荐引擎"""
    
    def __init__(self):
        # 数据库管理器通过方法参数传递
        self.category_weights = {
            '知识': 1.3,
            '科技': 1.2,
            '游戏': 1.1,
            '音乐': 1.1,
            '动画': 1.1,
            '生活': 1.0,
            '影视': 1.0,
            '体育': 1.0,
            '美食': 1.0,
            '娱乐': 0.9,
            '时尚': 0.9,
            '其他': 0.8
        }
        
        # 理想分布配置
        self.ideal_distribution = {
            '知识': 0.25,
            '科技': 0.15,
            '生活': 0.15,
            '娱乐': 0.15,
            '游戏': 0.10,
            '音乐': 0.10,
            '其他': 0.10
        }
    
    async def get_category_recommendations(self, user_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取类别推荐"""
        try:
            category_distribution = user_data.get('category_distribution', {})
            total_following = user_data.get('total_following', 0)
            
            if total_following == 0:
                return self._get_default_recommendations()
            
            recommendations = []
            current_distribution = {cat: count/total_following for cat, count in category_distribution.items()}
            
            # 计算每个类别的推荐优先级
            for category, ideal_ratio in self.ideal_distribution.items():
                current_ratio = current_distribution.get(category, 0)
                gap = ideal_ratio - current_ratio
                
                if gap > 0.03:  # 如果差距超过3%
                    priority_score = self._calculate_priority_score(gap, category, current_distribution)
                    
                    recommendations.append({
                        'category': category,
                        'current_percentage': round(current_ratio * 100, 1),
                        'suggested_percentage': round(ideal_ratio * 100, 1),
                        'gap': round(gap * 100, 1),
                        'priority': self._get_priority_level(gap),
                        'priority_score': priority_score,
                        'reason': self._generate_category_reason(category, gap, current_ratio),
                        'suggested_count': max(1, int(gap * total_following))
                    })
            
            # 按优先级得分排序
            recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
            return recommendations[:5]
            
        except Exception as e:
            logger.error(f"获取类别推荐失败: {str(e)}")
            return []
    
    def _get_simulated_user_recommendations(self, top_interests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """获取模拟用户推荐"""
        recommendations = []
        
        # 基于用户兴趣生成推荐
        for i, interest in enumerate(top_interests[:3]):
            category = interest.get('category', '其他')
            recommendations.append({
                'uid': f'rec_user_{i+1}',
                'name': f'{category}达人{i+1}',
                'category': category,
                'reason': f'基于您对{category}的兴趣推荐',
                'confidence': 0.85 - (i * 0.05),
                'follower_count': f'{np.random.randint(10, 100)}万',
                'video_count': np.random.randint(100, 1000)
            })
        
        # 添加一些多样性推荐
        diverse_categories = ['知识', '科技', '生活', '娱乐']
        for i, category in enumerate(diverse_categories[:2]):
            recommendations.append({
                'uid': f'diverse_user_{i+1}',
                'name': f'{category}博主{i+1}',
                'category': category,
                'reason': f'丰富您的{category}类关注',
                'confidence': 0.70 - (i * 0.05),
                'follower_count': f'{np.random.randint(5, 50)}万',
                'video_count': np.random.randint(50, 500)
            })
        
        return recommendations
    
    async def get_user_recommendations(self, user_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取用户推荐"""
        try:
            category_distribution = user_data.get('category_distribution', {})
            top_interests = user_data.get('top_interests', [])
            
            # 使用模拟推荐数据
            recommendations = self._get_simulated_user_recommendations(top_interests)
            
            return recommendations[:8]
            
        except Exception as e:
            logger.error(f"获取用户推荐失败: {str(e)}")
            return []
    
    async def calculate_diversity_score(self, category_distribution: Dict[str, int]) -> float:
        """计算多样性得分"""
        try:
            total_following = sum(category_distribution.values())
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
            
        except Exception as e:
            logger.error(f"计算多样性得分失败: {str(e)}")
            return 0.0
    
    def generate_suggestion_reason(self, diversity_score: float, category_distribution: Dict[str, int]) -> str:
        """生成建议原因"""
        try:
            total_following = sum(category_distribution.values())
            
            if diversity_score < 30:
                dominant_category = max(category_distribution.items(), key=lambda x: x[1])[0]
                return f"您的关注主要集中在{dominant_category}领域，建议增加其他类别的关注以丰富内容体验"
            elif diversity_score > 80:
                return "您的关注非常多样化，建议在感兴趣的领域深入关注优质创作者"
            elif total_following < 50:
                return "建议增加关注数量，探索更多感兴趣的内容创作者"
            else:
                return "您的关注分布较为均衡，建议根据个人兴趣适当调整关注重点"
                
        except Exception as e:
            logger.error(f"生成建议原因失败: {str(e)}")
            return "建议根据个人兴趣调整关注分布"
    
    def _calculate_priority_score(self, gap: float, category: str, current_distribution: Dict[str, float]) -> float:
        """计算优先级得分"""
        # 基础得分：差距越大得分越高
        base_score = gap * 100
        
        # 类别权重加成
        weight_bonus = self.category_weights.get(category, 1.0) * 10
        
        # 当前占比惩罚：如果当前占比已经很高，降低优先级
        current_ratio = current_distribution.get(category, 0)
        ratio_penalty = current_ratio * 20
        
        return base_score + weight_bonus - ratio_penalty
    
    def _get_priority_level(self, gap: float) -> str:
        """获取优先级等级"""
        if gap > 0.15:
            return 'high'
        elif gap > 0.08:
            return 'medium'
        else:
            return 'low'
    
    def _generate_category_reason(self, category: str, gap: float, current_ratio: float) -> str:
        """生成类别推荐原因"""
        reasons = {
            '知识': '增加知识类内容可以提升学习效果',
            '科技': '关注科技动态有助于跟上时代发展',
            '生活': '生活类内容能够丰富日常体验',
            '娱乐': '适当的娱乐内容有助于放松心情',
            '游戏': '游戏内容可以了解最新游戏资讯',
            '音乐': '音乐内容能够陶冶情操',
            '体育': '体育内容有助于了解运动资讯',
            '美食': '美食内容可以发现新的烹饪灵感',
            '动画': '动画内容能够带来视觉享受',
            '影视': '影视内容有助于了解最新作品'
        }
        
        base_reason = reasons.get(category, f'增加{category}类内容可以丰富您的关注体验')
        
        if current_ratio == 0:
            return f"您还没有关注{category}类内容，{base_reason}"
        elif gap > 0.2:
            return f"您的{category}类关注偏少，{base_reason}"
        else:
            return base_reason
    
    def _get_default_recommendations(self) -> List[Dict[str, Any]]:
        """获取默认推荐（当用户没有关注数据时）"""
        return [
            {
                'category': '知识',
                'current_percentage': 0,
                'suggested_percentage': 25,
                'gap': 25,
                'priority': 'high',
                'priority_score': 100,
                'reason': '知识类内容是建立关注体系的良好起点',
                'suggested_count': 5
            },
            {
                'category': '科技',
                'current_percentage': 0,
                'suggested_percentage': 15,
                'gap': 15,
                'priority': 'medium',
                'priority_score': 80,
                'reason': '科技内容有助于了解最新技术发展',
                'suggested_count': 3
            },
            {
                'category': '生活',
                'current_percentage': 0,
                'suggested_percentage': 15,
                'gap': 15,
                'priority': 'medium',
                'priority_score': 75,
                'reason': '生活类内容能够提供实用的日常建议',
                'suggested_count': 3
            }
        ]
    
    async def _get_recommended_users_for_category(self, category: str) -> List[Dict[str, Any]]:
        """为特定类别获取推荐用户"""
        # 这里返回模拟数据，实际应用中需要连接真实的用户数据库
        user_templates = {
            '知识': [
                {'name': '知识分享者A', 'reason': '专业的知识科普内容'},
                {'name': '学习达人B', 'reason': '高质量的学习方法分享'}
            ],
            '科技': [
                {'name': '科技评测C', 'reason': '深度的科技产品评测'},
                {'name': '程序员D', 'reason': '实用的编程技术分享'}
            ],
            '生活': [
                {'name': '生活博主E', 'reason': '实用的生活小技巧'},
                {'name': '美食达人F', 'reason': '简单易学的美食制作'}
            ]
        }
        
        templates = user_templates.get(category, [])
        recommendations = []
        
        for i, template in enumerate(templates[:2]):
            recommendations.append({
                'uid': f'{category}_rec_{i+1}',
                'name': template['name'],
                'category': category,
                'reason': template['reason'],
                'confidence': 0.75 + (i * 0.05),
                'follower_count': f'{np.random.randint(10, 100)}万',
                'video_count': np.random.randint(100, 1000)
            })
        
        return recommendations
    
    async def _get_diversity_recommendations(self, category_distribution: Dict[str, int]) -> List[Dict[str, Any]]:
        """基于多样性获取推荐"""
        total_following = sum(category_distribution.values())
        if total_following == 0:
            return []
        
        # 找出关注较少的类别
        current_ratios = {cat: count/total_following for cat, count in category_distribution.items()}
        underrepresented_categories = []
        
        for category, ideal_ratio in self.ideal_distribution.items():
            current_ratio = current_ratios.get(category, 0)
            if current_ratio < ideal_ratio * 0.5:  # 如果当前比例小于理想比例的一半
                underrepresented_categories.append(category)
        
        recommendations = []
        for category in underrepresented_categories[:2]:
            users = await self._get_recommended_users_for_category(category)
            for user in users[:1]:  # 每个类别推荐1个用户
                user['reason'] = f"丰富您的{category}类关注，提升内容多样性"
                user['confidence'] *= 0.9  # 多样性推荐的置信度稍低
                recommendations.append(user)
        
        return recommendations


class InterestAnalyzer:
    """兴趣分析器"""
    
    def __init__(self):
        # 数据库管理器通过方法参数传递
        pass
    
    async def analyze_interest_evolution(self, user_data: Dict[str, Any], days: int = 30) -> Dict[str, Any]:
        """分析兴趣演化"""
        try:
            # 模拟兴趣演化数据（实际应用中需要时间序列数据）
            evolution_data = self._generate_interest_evolution(user_data, days)
            
            # 计算兴趣稳定性
            stability_score = self._calculate_interest_stability(evolution_data)
            
            # 识别新兴兴趣
            emerging_interests = self._identify_emerging_interests(evolution_data)
            
            # 预测未来兴趣
            future_prediction = self._predict_future_interests(evolution_data)
            
            return {
                'evolution_data': evolution_data,
                'stability_score': stability_score,
                'emerging_interests': emerging_interests,
                'future_prediction': future_prediction
            }
            
        except Exception as e:
            logger.error(f"分析兴趣演化失败: {str(e)}")
            return {}
    
    def _generate_interest_evolution(self, user_data: Dict[str, Any], days: int) -> List[Dict[str, Any]]:
        """生成兴趣演化数据"""
        category_distribution = user_data.get('category_distribution', {})
        base_date = datetime.now() - timedelta(days=days)
        
        evolution_data = []
        for i in range(days):
            date = base_date + timedelta(days=i)
            
            # 模拟每日兴趣变化
            daily_interests = {}
            for category, base_count in category_distribution.items():
                # 添加随机波动
                variation = np.random.normal(0, 0.1)
                daily_interests[category] = max(0, base_count + variation)
            
            evolution_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'interests': daily_interests,
                'diversity_score': np.random.normal(60, 10)
            })
        
        return evolution_data
    
    def _calculate_interest_stability(self, evolution_data: List[Dict[str, Any]]) -> float:
        """计算兴趣稳定性"""
        if len(evolution_data) < 2:
            return 100.0
        
        # 计算多样性得分的方差
        diversity_scores = [item['diversity_score'] for item in evolution_data]
        variance = np.var(diversity_scores)
        
        # 转换为稳定性得分（方差越小，稳定性越高）
        stability = max(0, 100 - variance)
        return round(stability, 2)
    
    def _identify_emerging_interests(self, evolution_data: List[Dict[str, Any]]) -> List[str]:
        """识别新兴兴趣"""
        if len(evolution_data) < 7:
            return []
        
        # 比较最近一周和之前的数据
        recent_data = evolution_data[-7:]
        earlier_data = evolution_data[:-7]
        
        # 计算平均兴趣分布
        recent_avg = defaultdict(float)
        earlier_avg = defaultdict(float)
        
        for item in recent_data:
            for category, score in item['interests'].items():
                recent_avg[category] += score / len(recent_data)
        
        for item in earlier_data:
            for category, score in item['interests'].items():
                earlier_avg[category] += score / len(earlier_data)
        
        # 找出增长明显的类别
        emerging = []
        for category in recent_avg:
            if recent_avg[category] > earlier_avg.get(category, 0) * 1.5:
                emerging.append(category)
        
        return emerging[:3]
    
    def _predict_future_interests(self, evolution_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """预测未来兴趣"""
        if len(evolution_data) < 7:
            return {'message': '数据不足，无法生成预测'}
        
        # 简单的线性趋势预测
        recent_trend = [item['diversity_score'] for item in evolution_data[-7:]]
        trend_slope = (recent_trend[-1] - recent_trend[0]) / 6
        
        predicted_diversity = recent_trend[-1] + trend_slope * 7
        
        return {
            'predicted_diversity_score': round(predicted_diversity, 1),
            'trend_direction': '上升' if trend_slope > 1 else '下降' if trend_slope < -1 else '稳定',
            'confidence': 0.7,
            'recommendation': self._generate_prediction_recommendation(predicted_diversity, trend_slope)
        }
    
    def _generate_prediction_recommendation(self, predicted_score: float, trend_slope: float) -> str:
        """生成预测建议"""
        if predicted_score < 40:
            return "建议增加关注的多样性，探索新的内容领域"
        elif predicted_score > 85:
            return "您的兴趣非常广泛，建议在核心领域深入关注"
        elif trend_slope > 2:
            return "您的兴趣多样性在快速增长，保持这种探索精神"
        elif trend_slope < -2:
            return "您的兴趣趋于集中，可以考虑适当拓展新领域"
        else:
            return "您的兴趣发展趋势良好，建议保持当前的关注策略"