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
        
        # 分类关键词映射 - 增强版
        self.category_keywords = {
            "游戏": [
                "游戏", "攻略", "解说", "实况", "通关", "评测", "LOL", "王者", "原神", 
                "和平精英", "CF", "CSGO", "DOTA", "守望先锋", "炉石", "我的世界",
                "游戏解说", "游戏主播", "电竞", "手游", "单机", "网游", "FPS", "MOBA",
                "DNF", "魔兽", "暗黑", "塞尔达", "宝可梦", "神奇宝贝", "steam",
                "主机游戏", "掌机", "switch", "ps", "xbox", "任天堂", "索尼"
            ],
            "科技": [
                "科技", "数码", "手机", "电脑", "评测", "开箱", "iPhone", "华为", 
                "小米", "拆机", "硬件", "软件", "编程", "代码", "算法", "AI",
                "人工智能", "科普", "技术", "IT", "互联网", "极客", "CPU", "GPU",
                "安卓", "iOS", "Windows", "Mac", "Linux", "芯片", "处理器",
                "笔记本", "台式机", "显卡", "内存", "SSD", "5G", "6G", "Wi-Fi"
            ],
            "知识": [
                "知识", "教育", "学习", "课程", "教学", "科普", "历史", "地理",
                "物理", "化学", "生物", "数学", "英语", "考研", "高考", "大学",
                "老师", "教授", "讲座", "演讲", "TED", "知识分享", "学术", "研究",
                "论文", "博士", "硕士", "本科", "中学", "小学", "语文", "文学"
            ],
            "生活": [
                "生活", "日常", "vlog", "分享", "记录", "美食", "做饭", "料理",
                "旅行", "旅游", "探店", "购物", "穿搭", "护肤", "化妆", "家居",
                "装修", "宠物", "猫", "狗", "健身", "运动", "跑步", "瑜伽",
                "居家", "日用", "好物", "种草", "拔草", "测评", "推荐"
            ],
            "娱乐": [
                "娱乐", "搞笑", "段子", "相声", "小品", "脱口秀", "综艺", "明星",
                "八卦", "影视", "电影", "电视剧", "动漫", "二次元", "cos",
                "音乐", "歌手", "乐器", "舞蹈", "表演", "魔术", "街舞", "古风",
                "说唱", "rap", "翻唱", "原创", "MV", "演唱会", "音乐节"
            ],
            "美食": [
                "美食", "做饭", "料理", "烹饪", "菜谱", "食谱", "餐厅", "小吃",
                "甜品", "蛋糕", "烘焙", "火锅", "川菜", "粤菜", "日料", "韩料",
                "西餐", "中餐", "零食", "饮品", "咖啡", "奶茶", "探店", "吃播",
                "厨师", "大厨", "家常菜", "特色菜", "地方菜", "传统菜"
            ],
            "时尚": [
                "时尚", "穿搭", "服装", "搭配", "化妆", "护肤", "美妆", "口红",
                "包包", "鞋子", "配饰", "发型", "美甲", "减肥", "瘦身", "健身",
                "模特", "时装", "品牌", "奢侈品", "潮流", "流行", "趋势",
                "造型", "搭配师", "美容", "保养", "彩妆", "香水"
            ],
            "汽车": [
                "汽车", "车", "试驾", "评测", "改装", "豪车", "跑车", "SUV",
                "新能源", "电动车", "特斯拉", "比亚迪", "奔驰", "宝马", "奥迪",
                "保养", "维修", "驾驶", "驾考", "车展", "赛车", "摩托车",
                "二手车", "购车", "选车", "4S店", "汽配", "轮胎", "机油"
            ],
            "财经": [
                "财经", "股票", "基金", "投资", "理财", "经济", "金融", "创业",
                "商业", "企业", "管理", "营销", "电商", "直播带货", "副业",
                "赚钱", "省钱", "消费", "保险", "房产", "炒股", "期货", "外汇",
                "银行", "贷款", "信用卡", "支付", "数字货币", "比特币"
            ],
            "体育": [
                "体育", "足球", "篮球", "网球", "羽毛球", "乒乓球", "游泳",
                "健身", "跑步", "马拉松", "瑜伽", "NBA", "CBA", "世界杯",
                "奥运会", "运动员", "比赛", "竞技", "训练", "中超", "英超",
                "欧冠", "奥运", "亚运", "全运", "体操", "田径", "举重"
            ],
            "动漫": [
                "动漫", "番剧", "漫画", "二次元", "ACG", "动画", "声优",
                "手办", "模型", "cos", "cosplay", "宅", "萌", "治愈",
                "热血", "恋爱", "校园", "异世界", "穿越", "魔法", "忍者",
                "海贼", "火影", "死神", "龙珠", "柯南", "进击", "鬼灭"
            ],
            "音乐": [
                "音乐", "唱歌", "翻唱", "原创", "作词", "作曲", "编曲", "乐器",
                "钢琴", "吉他", "小提琴", "古筝", "二胡", "民谣", "摇滚",
                "流行", "古典", "电子", "说唱", "rap", "嘻哈", "爵士",
                "蓝调", "country", "金属", "朋克", "indie", "lo-fi"
            ]
        }
    
    def classify_user(self, user_data: Dict[str, Any]) -> str:
        """对用户进行智能分类"""
        uname = user_data.get("uname", "").lower()
        sign = user_data.get("sign", "").lower()
        
        # 组合用户名和签名进行分析，给用户名更高权重
        uname_weight = 3.0  # 用户名权重更高
        sign_weight = 1.0   # 签名权重
        
        # 计算每个分类的匹配分数
        category_scores = {}
        for category, keywords in self.category_keywords.items():
            score = 0.0
            
            # 检查用户名匹配
            for keyword in keywords:
                keyword_lower = keyword.lower()
                # 完全匹配得分更高
                if keyword_lower == uname.strip():
                    score += 5.0 * uname_weight
                elif keyword_lower in uname:
                    score += 2.0 * uname_weight
                
                # 检查签名匹配
                if keyword_lower == sign.strip():
                    score += 3.0 * sign_weight
                elif keyword_lower in sign:
                    score += 1.0 * sign_weight
            
            category_scores[category] = score
        
        # 找到最高分的分类
        if category_scores:
            best_category = max(category_scores, key=category_scores.get)
            best_score = category_scores[best_category]
            
            # 设置最低分数阈值，避免误分类
            min_score_threshold = 1.0
            if best_score >= min_score_threshold:
                # 检查是否有明显的最佳分类（与第二名差距足够大）
                sorted_scores = sorted(category_scores.values(), reverse=True)
                if len(sorted_scores) >= 2:
                    first_score = sorted_scores[0]
                    second_score = sorted_scores[1]
                    # 如果最高分与第二高分差距不够大，说明分类不够明确
                    if first_score - second_score < 0.5:
                        return "其他"
                
                return best_category
        
        # 如果没有匹配到明确分类，尝试一些特殊规则
        combined_text = f"{uname} {sign}"
        
        # UP主类型检测
        if any(keyword in combined_text for keyword in ['up主', 'up', 'youtuber', '主播', '博主']):
            # 根据其他关键词进一步细分
            if any(keyword in combined_text for keyword in ['游戏', '电竞', '直播']):
                return "游戏"
            elif any(keyword in combined_text for keyword in ['科技', '数码', '测评']):
                return "科技"
            elif any(keyword in combined_text for keyword in ['美食', '料理', '做饭']):
                return "美食"
            elif any(keyword in combined_text for keyword in ['生活', 'vlog', '日常']):
                return "生活"
        
        # 如果都没有匹配到，返回其他
        return "其他"
    
    def analyze_following_distribution(self, following_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析关注列表分布"""
        if not following_list:
            return {
                "total_count": 0,
                "category_distribution": {},
                "monthly_following": {},
                "vip_distribution": {"普通用户": 0},
                "official_distribution": {"未认证": 0},
                "analysis_time": datetime.now().isoformat()
            }
        
        # 分类统计 - 确保每个用户都有分类
        categories = []
        for user in following_list:
            category = user.get("category")
            if not category or category.strip() == "":
                # 如果没有分类，进行智能分类
                category = self.classify_user(user)
            categories.append(category)
        
        category_stats = Counter(categories)
        
        # 关注时间分析
        follow_times = []
        for user in following_list:
            mtime = user.get("mtime", 0) or user.get("follow_time", 0)
            if mtime > 0:
                follow_times.append(datetime.fromtimestamp(mtime))
        
        # 按月份统计关注数量
        monthly_stats = defaultdict(int)
        for dt in follow_times:
            month_key = dt.strftime("%Y-%m")
            monthly_stats[month_key] += 1
        
        # VIP用户统计 - 修复字段访问
        vip_stats = Counter()
        for user in following_list:
            vip_type = user.get("vip_type", 0)
            # 确保vip_type是数字类型
            try:
                vip_type = int(vip_type) if vip_type is not None else 0
            except (ValueError, TypeError):
                vip_type = 0
                
            if vip_type == 0:
                vip_stats["普通用户"] += 1
            elif vip_type == 1:
                vip_stats["月度大会员"] += 1
            elif vip_type == 2:
                vip_stats["年度大会员"] += 1
            else:
                vip_stats["其他VIP"] += 1
        
        # 认证用户统计 - 修复字段访问
        official_stats = Counter()
        for user in following_list:
            official_type = user.get("official_type", -1)
            # 确保official_type是数字类型
            try:
                official_type = int(official_type) if official_type is not None else -1
            except (ValueError, TypeError):
                official_type = -1
                
            if official_type == -1:
                official_stats["未认证"] += 1
            elif official_type == 0:
                official_stats["个人认证"] += 1
            elif official_type == 1:
                official_stats["机构认证"] += 1
            else:
                official_stats["其他认证"] += 1
        
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
        """找出不活跃的用户
        
        不活跃判断标准：
        1. 主要标准：超过30天未发布视频
        2. 辅助标准：活跃度分数低于0.2 且 视频数量少于3个
        """
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
            
            # 主要标准：最后发视频时间超过30天
            last_video_time = stat.get("last_video_time", 0)
            days_since_last_video = -1
            
            if last_video_time > 0:
                last_video_date = datetime.fromtimestamp(last_video_time)
                days_since_last_video = (current_time - last_video_date).days
                
                # 主要判断：30天未更新视频
                if days_since_last_video > 30:
                    is_inactive = True
                    inactive_reasons.append(f"{days_since_last_video}天未发视频")
            else:
                # 没有视频时间记录，但不直接标记为不活跃
                # 需要结合其他指标综合判断
                days_since_last_video = 999  # 标记为无记录
            
            # 辅助判断：综合活跃度和内容产出
            activity_score = stat.get("activity_score", 0)
            video_count = stat.get("video_count", 0)
            
            # 只有在活跃度很低且视频很少的情况下才额外标记为不活跃
            if activity_score < 0.2 and video_count < 3:
                if not is_inactive:  # 如果时间标准没有判定为不活跃
                    is_inactive = True
                    inactive_reasons.append(f"活跃度极低({activity_score:.2f})且内容稀少({video_count}个视频)")
                else:
                    # 如果已经因为时间被判定为不活跃，添加额外原因
                    inactive_reasons.append(f"活跃度低({activity_score:.2f})")
                    inactive_reasons.append(f"视频数量少({video_count})")
            
            # 对于没有视频记录的特殊处理
            if last_video_time == 0 and activity_score < 0.1:
                is_inactive = True
                if "无视频活动记录" not in " ".join(inactive_reasons):
                    inactive_reasons.append("无视频活动记录且活跃度极低")
            
            if is_inactive:
                user_copy = user.copy()
                user_copy["inactive_reasons"] = inactive_reasons
                user_copy["last_video_days"] = days_since_last_video
                user_copy["activity_score"] = activity_score
                user_copy["video_count"] = video_count
                inactive_users.append(user_copy)
        
        # 按不活跃程度排序 - 综合考虑多个因素
        def inactive_score(user):
            score = 0
            if user["last_video_days"] > 0:
                score += user["last_video_days"] / 30  # 按月计算
            else:
                score += 12  # 无记录给高分
            
            stat = stats_dict.get(user.get("uid"), {})
            activity_score = stat.get("activity_score", 0)
            score += (1 - activity_score) * 10  # 活跃度越低分数越高
            
            video_count = stat.get("video_count", 0)
            if video_count < 5:
                score += (5 - video_count) * 2
            
            return score
        
        inactive_users.sort(key=inactive_score, reverse=True)
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