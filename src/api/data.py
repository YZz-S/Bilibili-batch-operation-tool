# -*- coding: utf-8 -*-
"""
数据管理API路由
Data Management API Router

处理数据导入、导出和管理相关的API请求
"""

from fastapi import APIRouter, HTTPException, Response, Request
from fastapi.responses import JSONResponse
import json
import csv
import io
from typing import Optional, Dict, Any
from datetime import datetime

from ..core.logger import get_logger

router = APIRouter()
logger = get_logger()


@router.get("/export/json")
async def export_following_json(req: Request):
    """导出关注列表为JSON格式"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 准备导出数据
        export_data = {
            "export_time": datetime.now().isoformat(),
            "total_count": len(following_list),
            "following_list": following_list
        }
        
        # 创建JSON响应
        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        
        return Response(
            content=json_str,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=bilibili_following_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
    except Exception as e:
        logger.error(f"导出JSON失败: {e}")
        raise HTTPException(status_code=500, detail="导出失败")


@router.get("/export/csv")
async def export_following_csv(req: Request):
    """导出关注列表为CSV格式"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        # 创建CSV内容
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        headers = [
            "UID", "用户名", "签名", "等级", "VIP类型", "认证类型", 
            "分类", "关注时间", "特别关注", "创建时间"
        ]
        writer.writerow(headers)
        
        # 写入数据
        for user in following_list:
            follow_time = ""
            if user.get("follow_time"):
                follow_time = datetime.fromtimestamp(user["follow_time"]).strftime("%Y-%m-%d %H:%M:%S")
            
            row = [
                user.get("uid", ""),
                user.get("uname", ""),
                user.get("sign", ""),
                user.get("level", 0),
                user.get("vip_type", 0),
                user.get("official_type", 0),
                user.get("category", ""),
                follow_time,
                user.get("special_attention", 0),
                user.get("created_at", "")
            ]
            writer.writerow(row)
        
        csv_content = output.getvalue()
        output.close()
        
        return Response(
            content=csv_content.encode('utf-8-sig'),  # 添加BOM以支持Excel中文
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=bilibili_following_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    except Exception as e:
        logger.error(f"导出CSV失败: {e}")
        raise HTTPException(status_code=500, detail="导出失败")


@router.get("/stats/overview")
async def get_overview_stats(req: Request, ignore_ungrouped: bool = False):
    """获取概览统计"""
    try:
        db_manager = req.app.state.db_manager
        # 总关注数
        total_following = await db_manager.get_following_count()
        
        # 分类统计
        categories = await db_manager.get_categories_stats()
        
        # 如果启用忽略未分组，则过滤分类统计
        if ignore_ungrouped:
            categories = [
                cat for cat in categories 
                if cat.get("category") and cat.get("category").strip() != "" 
                and cat.get("category") not in ["其他", "null", "默认分组", "未分组"]
            ]
        
        # 最近关注用户（按关注时间排序，取前10个）
        following_list = await db_manager.get_following_list(
            limit=10, 
            sort_by="follow_time", 
            sort_order="desc"
        )
        recent_following = []
        for user in following_list:
            recent_following.append({
                "uid": user["uid"],
                "uname": user["uname"],
                "face": user.get("face", ""),  # 添加头像字段
                "sign": user.get("sign", ""),  # 添加签名字段
                "category": user.get("category", ""),  # 添加分类字段
                "follow_time": user.get("follow_time", 0),  # 关注时间
                "created_at": user.get("created_at", "")
            })
        
        return {
            "total_following": total_following,
            "categories": categories,
            "recent_following": recent_following,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取概览统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取统计数据失败")


@router.delete("/clear")
async def clear_all_data(req: Request):
    """清空所有数据（危险操作）"""
    try:
        db_manager = req.app.state.db_manager
        # 删除所有关注数据
        await db_manager._connection.execute("DELETE FROM following_list")
        await db_manager._connection.execute("DELETE FROM user_stats")
        await db_manager._connection.execute("DELETE FROM watch_history")
        await db_manager._connection.commit()
        
        logger.warning("所有数据已被清空")
        return {"message": "所有数据已清空"}
    except Exception as e:
        logger.error(f"清空数据失败: {e}")
        raise HTTPException(status_code=500, detail="清空数据失败")


@router.get("/backup")
async def create_backup(req: Request):
    """创建数据备份"""
    try:
        db_manager = req.app.state.db_manager
        # 获取所有数据
        following_list = await db_manager.get_following_list()
        categories = await db_manager.get_categories_stats()
        
        backup_data = {
            "backup_time": datetime.now().isoformat(),
            "version": "1.0.0",
            "data": {
                "following_list": following_list,
                "categories": categories
            }
        }
        
        json_str = json.dumps(backup_data, ensure_ascii=False, indent=2)
        
        return Response(
            content=json_str,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=bilibili_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
    except Exception as e:
        logger.error(f"创建备份失败: {e}")
        raise HTTPException(status_code=500, detail="创建备份失败")


@router.get("/search")
async def search_users(
    req: Request,
    q: str,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    """搜索用户"""
    try:
        db_manager = req.app.state.db_manager
        offset = (page - 1) * page_size
        following_list = await db_manager.get_following_list(
            limit=page_size, offset=offset, category=category, search=q
        )
        
        # 计算总数（这里简化处理）
        all_results = await db_manager.get_following_list(category=category, search=q)
        total_count = len(all_results)
        
        return {
            "data": following_list,
            "query": q,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "pages": (total_count + page_size - 1) // page_size
            }
        }
    except Exception as e:
        logger.error(f"搜索用户失败: {e}")
        raise HTTPException(status_code=500, detail="搜索失败")


@router.get("/user-stats")
async def get_user_stats_data(req: Request, page: int = 1, limit: int = 50, search: str = None, 
                             has_real_data: bool = None, sort_by: str = "updated_at", 
                             sort_order: str = "desc"):
    """获取用户统计数据详情"""
    try:
        db_manager = req.app.state.db_manager
        
        # 获取user_stats表的数据统计
        cursor = await db_manager._connection.execute(
            "SELECT COUNT(*) as total FROM user_stats"
        )
        total_stats_count = (await cursor.fetchone())[0]
        
        # 获取最新更新时间
        cursor = await db_manager._connection.execute(
            "SELECT MAX(updated_at) as last_updated FROM user_stats"
        )
        result = await cursor.fetchone()
        last_updated = result[0] if result and result[0] else None
        
        # 构建查询条件
        where_conditions = []
        params = []
        
        # 联表查询，获取用户基本信息和统计数据
        base_sql = """
            SELECT us.*, fl.uname, fl.face, fl.category, fl.created_at as user_created_at
            FROM user_stats us
            LEFT JOIN following_list fl ON us.uid = fl.uid
            WHERE 1=1
        """
        
        if search:
            where_conditions.append("(fl.uname LIKE ? OR CAST(us.uid AS TEXT) LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        if has_real_data is not None:
            if has_real_data:
                # 有真实数据：updated_at不为空且不等于默认时间
                where_conditions.append("us.updated_at IS NOT NULL")
            else:
                # 无真实数据的用户：在following_list中但不在user_stats中
                base_sql = """
                    SELECT NULL as uid, NULL as fans_count, NULL as following_count, 
                           NULL as video_count, NULL as total_views, NULL as last_video_time,
                           NULL as activity_score, NULL as updated_at,
                           fl.uname, fl.face, fl.category, fl.created_at as user_created_at,
                           fl.uid as real_uid
                    FROM following_list fl
                    LEFT JOIN user_stats us ON fl.uid = us.uid
                    WHERE us.uid IS NULL
                """
                where_conditions = []
                params = []
        
        # 添加WHERE条件
        if where_conditions:
            base_sql += " AND " + " AND ".join(where_conditions)
        
        # 添加排序
        valid_sort_fields = {
            "updated_at": "us.updated_at",
            "fans_count": "us.fans_count", 
            "video_count": "us.video_count",
            "activity_score": "us.activity_score",
            "uname": "fl.uname",
            "last_video_time": "us.last_video_time"
        }
        
        if has_real_data is False:
            # 对于无数据的用户，按用户名排序
            base_sql += f" ORDER BY fl.uname {'DESC' if sort_order.lower() == 'desc' else 'ASC'}"
        else:
            sort_field = valid_sort_fields.get(sort_by, "us.updated_at")
            order = "DESC" if sort_order.lower() == "desc" else "ASC"
            base_sql += f" ORDER BY {sort_field} {order}"
        
        # 分页
        offset = (page - 1) * limit
        base_sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        # 执行查询
        cursor = await db_manager._connection.execute(base_sql, params)
        rows = await cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        
        # 转换为字典列表
        users_data = []
        for row in rows:
            user_dict = dict(zip(columns, row))
            
            # 处理无数据的用户
            if has_real_data is False:
                user_dict['uid'] = user_dict.get('real_uid')
                user_dict['has_real_data'] = False
            else:
                user_dict['has_real_data'] = True
                
            # 格式化时间
            if user_dict.get('updated_at'):
                try:
                    if isinstance(user_dict['updated_at'], (int, float)):
                        # 时间戳格式
                        updated_time = datetime.fromtimestamp(user_dict['updated_at'])
                        user_dict['updated_at_formatted'] = updated_time.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(user_dict['updated_at'], str):
                        # ISO格式字符串
                        updated_time = datetime.fromisoformat(user_dict['updated_at'].replace('Z', '+00:00'))
                        user_dict['updated_at_formatted'] = updated_time.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        user_dict['updated_at_formatted'] = str(user_dict['updated_at'])
                except Exception as e:
                    user_dict['updated_at_formatted'] = '格式错误'
            else:
                user_dict['updated_at_formatted'] = '无数据'
                
            # 计算最后视频天数
            if user_dict.get('last_video_time') and user_dict['last_video_time'] > 0:
                import time
                days_ago = int((time.time() - user_dict['last_video_time']) / (24 * 3600))
                user_dict['last_video_days'] = days_ago
            else:
                user_dict['last_video_days'] = None
                
            users_data.append(user_dict)
        
        # 获取总数（用于分页）
        if has_real_data is False:
            # 统计没有user_stats数据的用户数量
            count_sql = """
                SELECT COUNT(*)
                FROM following_list fl
                LEFT JOIN user_stats us ON fl.uid = us.uid
                WHERE us.uid IS NULL
            """
            count_params = []
            if search:
                count_sql += " AND (fl.uname LIKE ? OR CAST(fl.uid AS TEXT) LIKE ?)"
                count_params.extend([f"%{search}%", f"%{search}%"])
        else:
            # 统计有user_stats数据的用户数量
            count_sql = """
                SELECT COUNT(*)
                FROM user_stats us
                LEFT JOIN following_list fl ON us.uid = fl.uid
                WHERE 1=1
            """
            count_params = []
            if search:
                count_sql += " AND (fl.uname LIKE ? OR CAST(us.uid AS TEXT) LIKE ?)"
                count_params.extend([f"%{search}%", f"%{search}%"])
        
        cursor = await db_manager._connection.execute(count_sql, count_params)
        total_count = (await cursor.fetchone())[0]
        
        # 获取总体统计信息
        total_users = await db_manager.get_following_count()
        
        # 获取有统计数据的用户数量
        cursor = await db_manager._connection.execute(
            "SELECT COUNT(DISTINCT uid) FROM user_stats"
        )
        users_with_stats = (await cursor.fetchone())[0]
        
        return {
            "users": users_data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit
            },
            "summary": {
                "total_users": total_users,
                "users_with_stats": users_with_stats,
                "users_without_stats": total_users - users_with_stats,
                "last_updated": last_updated,
                "coverage_rate": round(users_with_stats / total_users * 100, 1) if total_users > 0 else 0
            },
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取用户统计数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取用户统计数据失败")


@router.get("/user-stats/summary")
async def get_user_stats_summary(req: Request):
    """获取用户统计数据概要信息"""
    try:
        db_manager = req.app.state.db_manager
        
        # 获取基本统计
        total_users = await db_manager.get_following_count()
        
        cursor = await db_manager._connection.execute(
            "SELECT COUNT(DISTINCT uid) FROM user_stats"
        )
        users_with_stats = (await cursor.fetchone())[0]
        
        # 获取最新更新时间和最旧更新时间
        cursor = await db_manager._connection.execute(
            "SELECT MAX(updated_at) as last_updated, MIN(updated_at) as first_updated FROM user_stats"
        )
        result = await cursor.fetchone()
        last_updated = result[0] if result and result[0] else None
        first_updated = result[1] if result and result[1] else None
        
        # 获取数据分布统计
        cursor = await db_manager._connection.execute("""
            SELECT 
                AVG(fans_count) as avg_fans,
                MAX(fans_count) as max_fans,
                AVG(video_count) as avg_videos,
                MAX(video_count) as max_videos,
                AVG(activity_score) as avg_activity
            FROM user_stats
        """)
        stats_result = await cursor.fetchone()
        
        # 获取最近7天和30天的更新数量
        from datetime import datetime, timedelta
        now = datetime.now()
        week_ago = (now - timedelta(days=7)).isoformat()
        month_ago = (now - timedelta(days=30)).isoformat()
        
        cursor = await db_manager._connection.execute(
            "SELECT COUNT(*) FROM user_stats WHERE updated_at >= ?", (week_ago,)
        )
        updated_this_week = (await cursor.fetchone())[0]
        
        cursor = await db_manager._connection.execute(
            "SELECT COUNT(*) FROM user_stats WHERE updated_at >= ?", (month_ago,)
        )
        updated_this_month = (await cursor.fetchone())[0]
        
        return {
            "basic_stats": {
                "total_users": total_users,
                "users_with_stats": users_with_stats,
                "users_without_stats": total_users - users_with_stats,
                "coverage_rate": round(users_with_stats / total_users * 100, 1) if total_users > 0 else 0
            },
            "time_info": {
                "last_updated": last_updated,
                "first_updated": first_updated,
                "updated_this_week": updated_this_week,
                "updated_this_month": updated_this_month
            },
            "data_distribution": {
                "avg_fans": int(stats_result[0]) if stats_result[0] else 0,
                "max_fans": int(stats_result[1]) if stats_result[1] else 0,
                "avg_videos": int(stats_result[2]) if stats_result[2] else 0,
                "max_videos": int(stats_result[3]) if stats_result[3] else 0,
                "avg_activity": round(stats_result[4], 2) if stats_result[4] else 0
            },
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取用户统计概要失败: {e}")
        raise HTTPException(status_code=500, detail="获取用户统计概要失败") 