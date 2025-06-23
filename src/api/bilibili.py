# -*- coding: utf-8 -*-
"""
哔哩哔哩API路由
Bilibili API Router

处理与哔哩哔哩相关的API请求
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio

from ..bilibili.api import get_bilibili_api
from ..bilibili.analyzer import FollowingAnalyzer
from ..core.logger import get_logger

router = APIRouter()
logger = get_logger()
analyzer = FollowingAnalyzer()


class SyncRequest(BaseModel):
    """同步请求模型"""
    force_refresh: bool = False


class UnfollowRequest(BaseModel):
    """取消关注请求模型"""
    uids: List[int]


class CategoryUpdateRequest(BaseModel):
    """分类更新请求模型"""
    uid: int
    category: str


@router.get("/status")
async def get_api_status():
    """获取API状态"""
    api = await get_bilibili_api()
    return {
        "configured": api.is_configured(),
        "cookie_valid": bool(api.cookie),
        "csrf_token_valid": bool(api._extract_csrf_token())
    }


@router.post("/sync")
async def sync_following_list(request: SyncRequest, background_tasks: BackgroundTasks, req: Request):
    """同步关注列表"""
    api = await get_bilibili_api()
    
    if not api.is_configured():
        raise HTTPException(status_code=400, detail="未配置哔哩哔哩Cookie")
    
    # 在后台执行同步任务
    background_tasks.add_task(_sync_following_task, req.app.state.db_manager)
    
    return {"message": "同步任务已启动", "status": "started"}


async def _sync_following_task(db_manager):
    """同步关注列表的后台任务"""
    try:
        api = await get_bilibili_api()
        
        # 创建同步记录
        record_id = await db_manager.insert_sync_record("following_sync")
        
        # 获取所有关注用户
        def progress_callback(current, total):
            logger.info(f"同步进度: {current}/{total}")
        
        following_list = await api.get_all_following(progress_callback)
        
        # 保存到数据库
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        logger.info(f"开始保存 {len(following_list)} 个用户到数据库")
        
        for i, user in enumerate(following_list, 1):
            try:
                # 验证用户数据 - 优先使用uid，如果没有则使用mid
                uid = user.get('uid') or user.get('mid')
                uname = user.get('uname', 'Unknown')
                
                if not uid:
                    logger.warning(f"用户 {i}/{len(following_list)} 缺少UID/MID，跳过: {user}")
                    skipped_count += 1
                    error_count += 1
                    continue
                
                # 确保uid字段存在
                user['uid'] = uid
                
                # 自动分类
                category = analyzer.classify_user(user)
                user["category"] = category
                
                if await db_manager.insert_following_user(user):
                    success_count += 1
                    if i % 50 == 0:  # 每50个用户记录一次进度
                        logger.info(f"数据库保存进度: {i}/{len(following_list)}")
                else:
                    error_count += 1
                    logger.warning(f"保存用户失败: UID={uid}, 用户名={uname}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"处理用户数据异常: {e}, 用户数据: {user}")
                continue
        
        # 更新同步记录
        await db_manager.update_sync_record(
            record_id, success_count, error_count, "completed"
        )
        
        logger.info(f"同步完成: 获取 {len(following_list)} 个用户, 成功保存 {success_count}, 失败 {error_count}, 跳过 {skipped_count}")
        
    except Exception as e:
        logger.error(f"同步失败: {e}")
        if 'record_id' in locals():
            await db_manager.update_sync_record(
                record_id, 0, 0, "failed", str(e)
            )


@router.get("/following")
async def get_following_list(
    req: Request,
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = "follow_time",
    sort_order: Optional[str] = "desc"
):
    """获取关注列表"""
    try:
        db_manager = req.app.state.db_manager
        offset = (page - 1) * page_size
        following_list = await db_manager.get_following_list(
            limit=page_size, offset=offset, category=category, search=search,
            sort_by=sort_by, sort_order=sort_order
        )
        
        total_count = await db_manager.get_following_count(category)
        
        return {
            "data": following_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "pages": (total_count + page_size - 1) // page_size
            }
        }
    except Exception as e:
        logger.error(f"获取关注列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取关注列表失败")


@router.get("/categories")
async def get_categories(req: Request):
    """获取分类统计"""
    try:
        db_manager = req.app.state.db_manager
        categories = await db_manager.get_categories_stats()
        return {"categories": categories}
    except Exception as e:
        logger.error(f"获取分类统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取分类统计失败")


@router.post("/unfollow")
async def batch_unfollow(request: UnfollowRequest, req: Request):
    """批量取消关注"""
    if not request.uids:
        raise HTTPException(status_code=400, detail="用户ID列表不能为空")
    
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        # 从B站取消关注
        success_count, error_count = await api.batch_unfollow(request.uids)
        
        # 从数据库删除
        db_success, db_error = await db_manager.batch_unfollow(request.uids)
        
        return {
            "message": f"批量取消关注完成",
            "bilibili_result": {
                "success": success_count,
                "error": error_count
            },
            "database_result": {
                "success": db_success,
                "error": db_error
            }
        }
    except Exception as e:
        logger.error(f"批量取消关注失败: {e}")
        raise HTTPException(status_code=500, detail="批量取消关注失败")


@router.post("/update-category")
async def update_user_category(request: CategoryUpdateRequest, req: Request):
    """更新用户分类"""
    try:
        db_manager = req.app.state.db_manager
        success = await db_manager.update_user_category(request.uid, request.category)
        if success:
            return {"message": "分类更新成功"}
        else:
            raise HTTPException(status_code=400, detail="分类更新失败")
    except Exception as e:
        logger.error(f"更新用户分类失败: {e}")
        raise HTTPException(status_code=500, detail="更新用户分类失败")


@router.post("/auto-categorize")
async def auto_categorize_users(req: Request):
    """自动分类用户"""
    try:
        db_manager = req.app.state.db_manager
        # 获取所有未分类的用户
        following_list = await db_manager.get_following_list()
        
        updated_count = 0
        for user in following_list:
            if not user.get("category") or user.get("category") == "其他":
                category = analyzer.classify_user(user)
                if category != "其他":
                    await db_manager.update_user_category(user["uid"], category)
                    updated_count += 1
        
        return {
            "message": f"自动分类完成，更新了 {updated_count} 个用户",
            "updated_count": updated_count
        }
    except Exception as e:
        logger.error(f"自动分类失败: {e}")
        raise HTTPException(status_code=500, detail="自动分类失败") 