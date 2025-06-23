# -*- coding: utf-8 -*-
"""
数据分析API路由
Data Analysis API Router

提供关注列表数据分析相关的API接口
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from ..bilibili.analyzer import FollowingAnalyzer
from ..core.logger import get_logger

router = APIRouter()
logger = get_logger()
analyzer = FollowingAnalyzer()


@router.get("/distribution")
async def get_following_distribution(req: Request):
    """获取关注列表分布分析"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        distribution = analyzer.analyze_following_distribution(following_list)
        
        return {
            "distribution": distribution,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取分布分析失败: {e}")
        raise HTTPException(status_code=500, detail="获取分布分析失败")


@router.get("/inactive")
async def get_inactive_users(req: Request, limit: Optional[int] = 50):
    """获取不活跃用户列表"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 这里使用模拟的用户统计数据
        # 实际应用中应该从user_stats表获取
        user_stats = []
        for user in following_list:
            # 模拟统计数据
            user_stats.append({
                "uid": user["uid"],
                "fans_count": 0,
                "following_count": 0,
                "video_count": 5,  # 模拟视频数量
                "total_views": 0,
                "last_video_time": user.get("mtime", 0),
                "activity_score": 0.5  # 模拟活跃度
            })
        
        inactive_users = analyzer.find_inactive_users(following_list, user_stats)
        
        if limit:
            inactive_users = inactive_users[:limit]
        
        return {
            "inactive_users": inactive_users,
            "total_count": len(inactive_users),
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取不活跃用户失败: {e}")
        raise HTTPException(status_code=500, detail="获取不活跃用户失败")


@router.get("/cleanup-suggestions")
async def get_cleanup_suggestions(req: Request):
    """获取清理建议"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 模拟用户统计数据
        user_stats = []
        for user in following_list:
            user_stats.append({
                "uid": user["uid"],
                "fans_count": 0,
                "following_count": 0,
                "video_count": 5,
                "total_views": 0,
                "last_video_time": user.get("mtime", 0),
                "activity_score": 0.5
            })
        
        suggestions = analyzer.suggest_cleanup(following_list, user_stats)
        
        return {
            "suggestions": suggestions,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取清理建议失败: {e}")
        raise HTTPException(status_code=500, detail="获取清理建议失败")


@router.get("/report")
async def generate_analysis_report(req: Request):
    """生成完整的分析报告"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 模拟用户统计数据
        user_stats = []
        for user in following_list:
            user_stats.append({
                "uid": user["uid"],
                "fans_count": 0,
                "following_count": 0,
                "video_count": 5,
                "total_views": 0,
                "last_video_time": user.get("mtime", 0),
                "activity_score": 0.5
            })
        
        report = analyzer.generate_report(following_list, user_stats)
        
        return {
            "report": report,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"生成分析报告失败: {e}")
        raise HTTPException(status_code=500, detail="生成分析报告失败")


@router.get("/category-stats")
async def get_category_statistics(req: Request):
    """获取详细的分类统计"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 按分类统计
        category_details = {}
        for user in following_list:
            category = user.get("category", "其他")
            if category not in category_details:
                category_details[category] = {
                    "count": 0,
                    "users": [],
                    "vip_count": 0,
                    "official_count": 0
                }
            
            category_details[category]["count"] += 1
            category_details[category]["users"].append({
                "uid": user["uid"],
                "uname": user["uname"],
                "face": user.get("face", ""),
                "sign": user.get("sign", "")
            })
            
            if user.get("vip_type", 0) > 0:
                category_details[category]["vip_count"] += 1
            
            if user.get("official_type", -1) >= 0:
                category_details[category]["official_count"] += 1
        
        # 排序
        sorted_categories = sorted(
            category_details.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )
        
        return {
            "category_stats": dict(sorted_categories),
            "total_categories": len(category_details),
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取分类统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取分类统计失败")


@router.get("/trends")
async def get_following_trends(req: Request):
    """获取关注趋势分析"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 按月份统计关注数量
        monthly_data = {}
        for user in following_list:
            mtime = user.get("mtime", 0)
            if mtime > 0:
                date = datetime.fromtimestamp(mtime)
                month_key = date.strftime("%Y-%m")
                monthly_data[month_key] = monthly_data.get(month_key, 0) + 1
        
        # 排序月份数据
        sorted_months = sorted(monthly_data.items())
        
        # 计算趋势
        trend_data = []
        for i, (month, count) in enumerate(sorted_months):
            trend_item = {
                "month": month,
                "count": count,
                "cumulative": sum(item[1] for item in sorted_months[:i+1])
            }
            
            # 计算环比增长
            if i > 0:
                prev_count = sorted_months[i-1][1]
                growth_rate = ((count - prev_count) / prev_count * 100) if prev_count > 0 else 0
                trend_item["growth_rate"] = round(growth_rate, 2)
            else:
                trend_item["growth_rate"] = 0
            
            trend_data.append(trend_item)
        
        return {
            "trends": trend_data,
            "total_months": len(monthly_data),
            "peak_month": max(sorted_months, key=lambda x: x[1]) if sorted_months else None,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取关注趋势失败: {e}")
        raise HTTPException(status_code=500, detail="获取关注趋势失败") 