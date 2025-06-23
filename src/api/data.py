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