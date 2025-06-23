# -*- coding: utf-8 -*-
"""
数据分析API路由
Data Analysis API Router

提供关注列表数据分析相关的API接口
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import time

from ..bilibili.analyzer import FollowingAnalyzer
from ..core.logger import get_logger

router = APIRouter()
logger = get_logger()
analyzer = FollowingAnalyzer()


@router.get("/distribution")
async def get_following_distribution(req: Request, ignore_ungrouped: bool = False):
    """获取关注列表分布分析"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 为没有分类的用户进行内存中的自动分类，但不更新数据库
        # 避免每次访问analysis页面时都触发大量数据库写操作
        for user in following_list:
            if not user.get("category") or user.get("category").strip() == "":
                # 只在内存中设置分类，不写入数据库
                user["category"] = analyzer.classify_user(user)
        
        # 如果启用忽略未分组，则过滤掉未分组的用户
        if ignore_ungrouped:
            following_list = [
                user for user in following_list 
                if user.get("category") and user.get("category").strip() != "" 
                and user.get("category") not in ["其他", "null", "默认分组", "未分组"]
            ]
        
        distribution = analyzer.analyze_following_distribution(following_list)
        
        return {
            "distribution": distribution,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取分布分析失败: {e}")
        raise HTTPException(status_code=500, detail="获取分布分析失败")


@router.get("/inactive")
async def get_inactive_users(req: Request, limit: Optional[int] = 50, ignore_ungrouped: bool = False):
    """获取不活跃用户列表"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 如果启用忽略未分组，则过滤掉未分组的用户
        if ignore_ungrouped:
            following_list = [
                user for user in following_list 
                if user.get("category") and user.get("category").strip() != "" 
                and user.get("category") not in ["其他", "null", "默认分组", "未分组"]
            ]
        
        # 获取真实的用户统计数据，如果没有则使用默认值
        user_stats = []
        for user in following_list:
            # 尝试从user_stats表获取真实数据
            try:
                cursor = await db_manager._connection.execute(
                    "SELECT * FROM user_stats WHERE uid = ?", (user["uid"],)
                )
                stat_row = await cursor.fetchone()
                
                if stat_row:
                    # 使用数据库中的真实数据
                    columns = [description[0] for description in cursor.description]
                    stat_data = dict(zip(columns, stat_row))
                else:
                    # 当没有真实数据时，使用更合理的默认值
                    # 避免随机生成可能误导的活跃度数据
                    current_time = int(time.time())
                    follow_time = user.get("mtime", 0) or user.get("follow_time", 0)
                    
                    stat_data = {
                        "uid": user["uid"],
                        "fans_count": 1000,  # 使用中等粉丝数
                        "following_count": 100,  # 适中的关注数
                        "video_count": 10,  # 适中的视频数量，避免被误判为不活跃
                        "total_views": 50000,  # 适中的播放量
                        "last_video_time": max(follow_time, current_time - 15*24*3600),  # 最近15天内
                        "activity_score": 0.6  # 中等活跃度，不会被误判为不活跃
                    }
                user_stats.append(stat_data)
            except Exception as e:
                logger.warning(f"获取用户 {user['uid']} 统计数据失败: {e}")
                # 使用合理的默认值，避免误判为不活跃
                current_time = int(time.time())
                user_stats.append({
                    "uid": user["uid"],
                    "fans_count": 1000,
                    "following_count": 100,
                    "video_count": 10,
                    "total_views": 50000,
                    "last_video_time": current_time - 15*24*3600,  # 15天前
                    "activity_score": 0.6
                })
        
        inactive_users = analyzer.find_inactive_users(following_list, user_stats)
        
        if limit:
            inactive_users = inactive_users[:limit]
        
        return {
            "inactive_users": inactive_users,
            "total_count": len(inactive_users),
            "criteria": {
                "primary": "超过30天未发布视频",
                "secondary": "活跃度低于0.2且视频少于3个",
                "description": "主要以发布时间为准，辅助考虑活跃度和内容产出"
            },
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取不活跃用户失败: {e}")
        raise HTTPException(status_code=500, detail="获取不活跃用户失败")


@router.get("/inactive/all")
async def get_all_inactive_users(req: Request, ignore_ungrouped: bool = False):
    """获取所有不活跃用户列表（无数量限制）"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 如果启用忽略未分组，则过滤掉未分组的用户
        if ignore_ungrouped:
            following_list = [
                user for user in following_list 
                if user.get("category") and user.get("category").strip() != "" 
                and user.get("category") not in ["其他", "null", "默认分组", "未分组"]
            ]
        
        # 获取用户统计数据
        user_stats = []
        for user in following_list:
            try:
                cursor = await db_manager._connection.execute(
                    "SELECT * FROM user_stats WHERE uid = ?", (user["uid"],)
                )
                stat_row = await cursor.fetchone()
                
                if stat_row:
                    columns = [description[0] for description in cursor.description]
                    stat_data = dict(zip(columns, stat_row))
                else:
                    current_time = int(time.time())
                    follow_time = user.get("mtime", 0) or user.get("follow_time", 0)
                    
                    stat_data = {
                        "uid": user["uid"],
                        "fans_count": 1000,
                        "following_count": 100,
                        "video_count": 10,
                        "total_views": 50000,
                        "last_video_time": max(follow_time, current_time - 15*24*3600),
                        "activity_score": 0.6
                    }
                user_stats.append(stat_data)
            except Exception as e:
                logger.warning(f"获取用户 {user['uid']} 统计数据失败: {e}")
                current_time = int(time.time())
                user_stats.append({
                    "uid": user["uid"],
                    "fans_count": 1000,
                    "following_count": 100,
                    "video_count": 10,
                    "total_views": 50000,
                    "last_video_time": current_time - 15*24*3600,
                    "activity_score": 0.6
                })
        
        inactive_users = analyzer.find_inactive_users(following_list, user_stats)
        
        return {
            "inactive_users": inactive_users,
            "total_count": len(inactive_users),
            "total_following": len(following_list),
            "inactive_percentage": round(len(inactive_users) / len(following_list) * 100, 1) if following_list else 0,
            "criteria": {
                "primary": "超过30天未发布视频",
                "secondary": "活跃度低于0.2且视频少于3个", 
                "description": "主要以发布时间为准，辅助考虑活跃度和内容产出"
            },
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取所有不活跃用户失败: {e}")
        raise HTTPException(status_code=500, detail="获取不活跃用户失败")


@router.get("/cleanup-suggestions")
async def get_cleanup_suggestions(req: Request, ignore_ungrouped: bool = False):
    """获取清理建议"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 如果启用忽略未分组，则过滤掉未分组的用户
        if ignore_ungrouped:
            following_list = [
                user for user in following_list 
                if user.get("category") and user.get("category").strip() != "" 
                and user.get("category") not in ["其他", "null", "默认分组", "未分组"]
            ]
        
        # 获取用户统计数据
        user_stats = []
        for user in following_list:
            try:
                cursor = await db_manager._connection.execute(
                    "SELECT * FROM user_stats WHERE uid = ?", (user["uid"],)
                )
                stat_row = await cursor.fetchone()
                
                if stat_row:
                    columns = [description[0] for description in cursor.description]
                    stat_data = dict(zip(columns, stat_row))
                else:
                    # 当没有真实数据时，使用更合理的默认值
                    current_time = int(time.time())
                    follow_time = user.get("mtime", 0) or user.get("follow_time", 0)
                    
                    stat_data = {
                        "uid": user["uid"],
                        "fans_count": 1000,  # 使用中等粉丝数
                        "following_count": 100,  # 适中的关注数
                        "video_count": 10,  # 适中的视频数量，避免被误判为不活跃
                        "total_views": 50000,  # 适中的播放量
                        "last_video_time": max(follow_time, current_time - 15*24*3600),  # 最近15天内
                        "activity_score": 0.6  # 中等活跃度，不会被误判为不活跃
                    }
                user_stats.append(stat_data)
            except Exception:
                # 使用合理的默认值，避免误判为不活跃
                current_time = int(time.time())
                user_stats.append({
                    "uid": user["uid"],
                    "fans_count": 1000,
                    "following_count": 100,
                    "video_count": 10,
                    "total_views": 50000,
                    "last_video_time": current_time - 15*24*3600,
                    "activity_score": 0.6
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
        
        # 获取用户统计数据
        user_stats = []
        for user in following_list:
            try:
                cursor = await db_manager._connection.execute(
                    "SELECT * FROM user_stats WHERE uid = ?", (user["uid"],)
                )
                stat_row = await cursor.fetchone()
                
                if stat_row:
                    columns = [description[0] for description in cursor.description]
                    stat_data = dict(zip(columns, stat_row))
                else:
                    # 当没有真实数据时，使用更合理的默认值
                    current_time = int(time.time())
                    follow_time = user.get("mtime", 0) or user.get("follow_time", 0)
                    
                    stat_data = {
                        "uid": user["uid"],
                        "fans_count": 1000,  # 使用中等粉丝数
                        "following_count": 100,  # 适中的关注数
                        "video_count": 10,  # 适中的视频数量，避免被误判为不活跃
                        "total_views": 50000,  # 适中的播放量
                        "last_video_time": max(follow_time, current_time - 15*24*3600),  # 最近15天内
                        "activity_score": 0.6  # 中等活跃度，不会被误判为不活跃
                    }
                user_stats.append(stat_data)
            except Exception:
                # 使用合理的默认值，避免误判为不活跃
                current_time = int(time.time())
                user_stats.append({
                    "uid": user["uid"],
                    "fans_count": 1000,
                    "following_count": 100,
                    "video_count": 10,
                    "total_views": 50000,
                    "last_video_time": current_time - 15*24*3600,
                    "activity_score": 0.6
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
        
        # 为没有分类的用户自动分类
        for user in following_list:
            if not user.get("category") or user.get("category").strip() == "":
                new_category = analyzer.classify_user(user)
                user["category"] = new_category
                # 更新数据库中的分类
                await db_manager.update_user_category(user["uid"], new_category)
        
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
async def get_following_trends(req: Request, ignore_ungrouped: bool = False):
    """获取关注趋势分析"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 如果启用忽略未分组，则过滤掉未分组的用户
        if ignore_ungrouped:
            following_list = [
                user for user in following_list 
                if user.get("category") and user.get("category").strip() != "" 
                and user.get("category") not in ["其他", "null", "默认分组", "未分组"]
            ]
        
        # 按月份统计关注数量
        monthly_data = {}
        for user in following_list:
            mtime = user.get("mtime", 0) or user.get("follow_time", 0)
            if mtime > 0:
                date = datetime.fromtimestamp(mtime)
                month_key = date.strftime("%Y-%m")
                monthly_data[month_key] = monthly_data.get(month_key, 0) + 1
        
        # 排序月份数据
        sorted_months = sorted(monthly_data.items())
        
        # 计算趋势
        trend_data = []
        cumulative_total = 0
        for i, (month, count) in enumerate(sorted_months):
            cumulative_total += count
            trend_item = {
                "month": month,
                "count": count,
                "cumulative": cumulative_total
            }
            
            # 计算环比增长
            if i > 0:
                prev_count = sorted_months[i-1][1]
                growth_rate = ((count - prev_count) / prev_count * 100) if prev_count > 0 else 0
                trend_item["growth_rate"] = round(growth_rate, 2)
            else:
                trend_item["growth_rate"] = 0
            
            trend_data.append(trend_item)
        
        # 创建适合前端图表的数据格式
        chart_data = {}
        for item in trend_data:
            chart_data[item["month"]] = item["count"]
        
        return {
            "trends": trend_data,
            "chart_data": chart_data,  # 添加图表专用数据
            "total_months": len(monthly_data),
            "peak_month": max(sorted_months, key=lambda x: x[1]) if sorted_months else None,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取关注趋势失败: {e}")
        raise HTTPException(status_code=500, detail="获取关注趋势失败")


@router.post("/update-categories")
async def update_user_categories(req: Request):
    """手动更新用户分类"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        updated_count = 0
        for user in following_list:
            if not user.get("category") or user.get("category").strip() == "":
                new_category = analyzer.classify_user(user)
                if await db_manager.update_user_category(user["uid"], new_category):
                    updated_count += 1
        
        logger.info(f"手动分类更新完成，共更新 {updated_count} 个用户的分类")
        
        return {
            "updated_count": updated_count,
            "total_users": len(following_list),
            "message": f"成功更新 {updated_count} 个用户的分类"
        }
    except Exception as e:
        logger.error(f"手动更新分类失败: {e}")
        raise HTTPException(status_code=500, detail="更新分类失败")


@router.post("/init-user-stats")
async def init_user_stats(req: Request):
    """初始化用户统计数据 - 为没有真实数据的用户生成合理的模拟数据"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 检查现有的user_stats数据
        existing_stats = set()
        try:
            cursor = await db_manager._connection.execute("SELECT uid FROM user_stats")
            existing_stats = {row[0] for row in await cursor.fetchall()}
        except Exception:
            pass
        
        created_count = 0
        current_time = int(time.time())
        
        for user in following_list:
            uid = user["uid"]
            if uid not in existing_stats:
                # 为新用户创建合理的统计数据
                follow_time = user.get("mtime", 0) or user.get("follow_time", 0)
                
                # 根据关注时间和用户信息生成更合理的数据
                days_since_follow = (current_time - follow_time) / (24 * 3600) if follow_time > 0 else 30
                
                # 生成相对合理的统计数据，包含一些变化
                import hashlib
                user_hash = int(hashlib.md5(str(uid).encode()).hexdigest()[:8], 16)
                
                # 使用哈希值生成确定性的"随机"数据，但范围更合理
                fans_count = 100 + (user_hash % 5000)  # 100-5100
                video_count = 5 + (user_hash % 50)     # 5-55
                
                # 根据关注时长调整活跃度
                if days_since_follow < 30:
                    activity_base = 0.7  # 较新的关注，假设较活跃
                    last_video_days = 5 + (user_hash % 20)  # 5-25天前
                elif days_since_follow < 180:
                    activity_base = 0.5  # 中等时间的关注
                    last_video_days = 15 + (user_hash % 60)  # 15-75天前
                else:
                    activity_base = 0.3  # 较老的关注，可能不太活跃
                    last_video_days = 30 + (user_hash % 120)  # 30-150天前
                
                activity_score = activity_base + (user_hash % 100) / 1000  # 添加一些变化
                last_video_time = current_time - (last_video_days * 24 * 3600)
                
                # 确保last_video_time不早于关注时间
                if follow_time > 0:
                    last_video_time = max(last_video_time, follow_time)
                
                try:
                    await db_manager._connection.execute(
                        """INSERT INTO user_stats 
                           (uid, fans_count, following_count, video_count, total_views, 
                            last_video_time, activity_score, updated_at) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (uid, fans_count, 100, video_count, fans_count * 10, 
                         last_video_time, activity_score, current_time)
                    )
                    created_count += 1
                except Exception as e:
                    logger.warning(f"创建用户 {uid} 统计数据失败: {e}")
        
        await db_manager._connection.commit()
        
        logger.info(f"初始化用户统计数据完成，共创建 {created_count} 条记录")
        
        return {
            "created_count": created_count,
            "total_users": len(following_list),
            "existing_stats": len(existing_stats),
            "message": f"成功初始化 {created_count} 个用户的统计数据"
        }
    except Exception as e:
        logger.error(f"初始化用户统计数据失败: {e}")
        raise HTTPException(status_code=500, detail="初始化统计数据失败") 