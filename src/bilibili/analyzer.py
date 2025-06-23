# -*- coding: utf-8 -*-
"""
关注列表分析模块
Following List Analyzer Module

提供关注列表的数据分析和智能分类功能
"""

import re
from typing import Dict, List, Any, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from ..core.logger import get_logger


class FollowingAnalyzer:
    """关注列表分析器"""
    
    def __init__(self):
        self.logger = get_logger()
        
        # 分类关键词映射
        self.category_keywords = {
            "游戏": [
                "游戏", "攻略", "解说", "实况", "通关", "评测", "LOL", "王者", "原神", 
                "和平精英", "CF", "CSGO", "DOTA", "守望先锋", "炉石", "我的世界",
                "游戏解说", "游戏主播", "电竞", "手游", "单机", "网游"
            ],
            "科技": [
                "科技", "数码", "手机", "电脑", "评测", "开箱", "iPhone", "华为", 
                "小米", "拆机", "硬件", "软件", "编程", "代码", "算法", "AI",
                "人工智能", "科普", "技术", "IT", "互联网", "极客"
            ],
            "知识": [
                "知识", "教育", "学习", "课程", "教学", "科普", "历史", "地理",
                "物理", "化学", "生物", "数学", "英语", "考研", "高考", "大学",
                "老师", "教授", "讲座", "演讲", "TED", "知识分享"
            ],
            "生活": [
                "生活", "日常", "vlog", "分享", "记录", "美食", "做饭", "料理",
                "旅行", "旅游", "探店", "购物", "穿搭", "护肤", "化妆", "家居",
                "装修", "宠物", "猫", "狗", "健身", "运动", "跑步"
            ],
            "娱乐": [
                "娱乐", "搞笑", "段子", "相声", "小品", "脱口秀", "综艺", "明星",
                "八卦", "影视", "电影", "电视剧", "动漫", "二次元", "cos",
                "音乐", "歌手", "乐器", "舞蹈", "表演", "魔术"
            ],
            "美食": [
                "美食", "做饭", "料理", "烹饪", "菜谱", "食谱", "餐厅", "小吃",
                "甜品", "蛋糕", "烘焙", "火锅", "川菜", "粤菜", "日料", "韩料",
                "西餐", "中餐", "零食", "饮品", "咖啡", "奶茶"
            ],
            "时尚": [
                "时尚", "穿搭", "服装", "搭配", "化妆", "护肤", "美妆", "口红",
                "包包", "鞋子", "配饰", "发型", "美甲", "减肥", "瘦身", "健身",
                "模特", "时装", "品牌", "奢侈品"
            ],
            "汽车": [
                "汽车", "车", "试驾", "评测", "改装", "豪车", "跑车", "SUV",
                "新能源", "电动车", "特斯拉", "比亚迪", "奔驰", "宝马", "奥迪",
                "保养", "维修", "驾驶", "驾考", "车展"
            ],
            "财经": [
                "财经", "股票", "基金", "投资", "理财", "经济", "金融", "创业",
                "商业", "企业", "管理", "营销", "电商", "直播带货", "副业",
                "赚钱", "省钱", "消费", "保险", "房产"
            ],
            "体育": [
                "体育", "足球", "篮球", "网球", "羽毛球", "乒乓球", "游泳",
                "健身", "跑步", "马拉松", "瑜伽", "NBA", "CBA", "世界杯",
                "奥运会", "运动员", "比赛", "竞技", "训练"
            ]
        }
    
    def classify_user(self, user_data: Dict[str, Any]) -> str:
        """对用户进行智能分类"""
        uname = user_data.get("uname", "").lower()
        sign = user_data.get("sign", "").lower()
        
        # 组合用户名和签名进行分析
        text = f"{uname} {sign}"
        
        # 计算每个分类的匹配分数
        category_scores = {}
        for category, keywords in self.category_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in text:
                    score += 1
            category_scores[category] = score
        
        # 找到最高分的分类
        if category_scores:
            best_category = max(category_scores, key=category_scores.get)
            if category_scores[best_category] > 0:
                return best_category
        
        # 如果没有匹配到，返回默认分类
        return "其他"
    
    def analyze_following_distribution(self, following_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析关注列表分布"""
        if not following_list:
            return {}
        
        # 分类统计
        categories = [self.classify_user(user) for user in following_list]
        category_stats = Counter(categories)
        
        # 关注时间分析
        follow_times = []
        for user in following_list:
            mtime = user.get("mtime", 0)
            if mtime > 0:
                follow_times.append(datetime.fromtimestamp(mtime))
        
        # 按月份统计关注数量
        monthly_stats = defaultdict(int)
        for dt in follow_times:
            month_key = dt.strftime("%Y-%m")
            monthly_stats[month_key] += 1
        
        # VIP用户统计
        vip_stats = Counter()
        for user in following_list:
            vip_type = user.get("vip", {}).get("vipType", 0)  # B站API使用vipType
            if vip_type == 0:
                vip_stats["普通用户"] += 1
            elif vip_type == 1:
                vip_stats["月度大会员"] += 1
            elif vip_type == 2:
                vip_stats["年度大会员"] += 1
        
        # 认证用户统计
        official_stats = Counter()
        for user in following_list:
            official_type = user.get("official_verify", {}).get("type", -1)  # B站API使用official_verify
            if official_type == -1:
                official_stats["未认证"] += 1
            elif official_type == 0:
                official_stats["个人认证"] += 1
            elif official_type == 1:
                official_stats["机构认证"] += 1
        
        return {
            "total_count": len(following_list),
            "category_distribution": dict(category_stats),
            "monthly_following": dict(monthly_stats),
            "vip_distribution": dict(vip_stats),
            "official_distribution": dict(official_stats),
            "analysis_time": datetime.now().isoformat()
        }
    
    def find_inactive_users(self, following_list: List[Dict[str, Any]], 
                           user_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """找出不活跃的用户"""
        inactive_users = []
        current_time = datetime.now()
        
        # 创建用户统计数据的字典
        stats_dict = {stat["uid"]: stat for stat in user_stats}
        
        for user in following_list:
            uid = user.get("uid")
            stat = stats_dict.get(uid, {})
            
            # 判断不活跃的标准
            is_inactive = False
            inactive_reasons = []
            
            # 最后发视频时间超过3个月
            last_video_time = stat.get("last_video_time", 0)
            if last_video_time > 0:
                last_video_date = datetime.fromtimestamp(last_video_time)
                days_since_last_video = (current_time - last_video_date).days
                if days_since_last_video > 90:
                    is_inactive = True
                    inactive_reasons.append(f"{days_since_last_video}天未发视频")
            
            # 活跃度分数低于0.3
            activity_score = stat.get("activity_score", 0)
            if activity_score < 0.3:
                is_inactive = True
                inactive_reasons.append(f"活跃度过低({activity_score:.2f})")
            
            # 视频数量过少
            video_count = stat.get("video_count", 0)
            if video_count < 5:
                is_inactive = True
                inactive_reasons.append(f"视频数量过少({video_count})")
            
            if is_inactive:
                user_copy = user.copy()
                user_copy["inactive_reasons"] = inactive_reasons
                user_copy["last_video_days"] = (current_time - datetime.fromtimestamp(last_video_time)).days if last_video_time > 0 else -1
                inactive_users.append(user_copy)
        
        # 按不活跃程度排序
        inactive_users.sort(key=lambda x: x.get("last_video_days", 9999), reverse=True)
        
        return inactive_users
    
    def suggest_cleanup(self, following_list: List[Dict[str, Any]], 
                       user_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """建议清理方案"""
        inactive_users = self.find_inactive_users(following_list, user_stats)
        
        # 分类建议
        suggestions = {
            "total_following": len(following_list),
            "inactive_count": len(inactive_users),
            "cleanup_suggestions": []
        }
        
        if len(inactive_users) > 10:
            suggestions["cleanup_suggestions"].append({
                "type": "batch_unfollow",
                "description": f"建议取消关注 {len(inactive_users)} 个不活跃用户",
                "user_list": [user["uid"] for user in inactive_users[:50]]  # 限制数量
            })
        
        # 分类建议
        category_stats = Counter(self.classify_user(user) for user in following_list)
        if category_stats.get("其他", 0) > 20:
            suggestions["cleanup_suggestions"].append({
                "type": "categorize",
                "description": f"有 {category_stats['其他']} 个用户未分类，建议进行分类整理"
            })
        
        return suggestions
    
    def generate_report(self, following_list: List[Dict[str, Any]], 
                       user_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成详细分析报告"""
        distribution = self.analyze_following_distribution(following_list)
        inactive_users = self.find_inactive_users(following_list, user_stats)
        cleanup_suggestions = self.suggest_cleanup(following_list, user_stats)
        
        # 计算一些额外的统计信息
        total_fans = sum(stat.get("fans_count", 0) for stat in user_stats)
        avg_activity = sum(stat.get("activity_score", 0) for stat in user_stats) / len(user_stats) if user_stats else 0
        
        report = {
            "summary": {
                "total_following": len(following_list),
                "total_fans_of_following": total_fans,
                "average_activity_score": round(avg_activity, 2),
                "inactive_users_count": len(inactive_users),
                "report_generated_at": datetime.now().isoformat()
            },
            "distribution": distribution,
            "inactive_analysis": {
                "count": len(inactive_users),
                "percentage": round(len(inactive_users) / len(following_list) * 100, 1) if following_list else 0,
                "top_inactive": inactive_users[:10]  # 最不活跃的10个
            },
            "cleanup_suggestions": cleanup_suggestions["cleanup_suggestions"],
            "category_recommendations": self._generate_category_recommendations(following_list)
        }
        
        return report
    
    def _generate_category_recommendations(self, following_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """生成分类建议"""
        recommendations = []
        
        # 找出未分类的用户
        uncategorized_users = []
        for user in following_list:
            if not user.get("category") or user.get("category") == "其他":
                suggested_category = self.classify_user(user)
                if suggested_category != "其他":
                    uncategorized_users.append({
                        "uid": user["uid"],
                        "uname": user["uname"],
                        "suggested_category": suggested_category,
                        "confidence": self._calculate_confidence(user, suggested_category)
                    })
        
        # 按置信度排序
        uncategorized_users.sort(key=lambda x: x["confidence"], reverse=True)
        
        if uncategorized_users:
            recommendations.append({
                "type": "auto_categorize",
                "description": f"建议自动分类 {len(uncategorized_users)} 个用户",
                "users": uncategorized_users[:20]  # 限制显示数量
            })
        
        return recommendations
    
    def _calculate_confidence(self, user_data: Dict[str, Any], category: str) -> float:
        """计算分类置信度"""
        uname = user_data.get("uname", "").lower()
        sign = user_data.get("sign", "").lower()
        text = f"{uname} {sign}"
        
        keywords = self.category_keywords.get(category, [])
        matches = sum(1 for keyword in keywords if keyword.lower() in text)
        
        # 计算置信度 (0-1)
        if matches == 0:
            return 0.0
        elif matches == 1:
            return 0.6
        elif matches == 2:
            return 0.8
        else:
            return 0.9 