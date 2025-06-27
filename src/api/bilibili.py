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
from datetime import datetime
import gc
import time

from ..bilibili.api import get_bilibili_api
from ..bilibili.analyzer import FollowingAnalyzer
from ..core.logger import get_logger
from ..core.performance_optimizer import PerformanceOptimizer
from ..database.manager import DatabaseManager
from .data import router as data_router
from .analysis import router as analysis_router

router = APIRouter()
logger = get_logger()
analyzer = FollowingAnalyzer()

# 任务控制状态存储
task_control_states = {}


async def check_task_control(task_id: str, step_name: str):
    """检查任务控制状态"""
    control = task_control_states.get(task_id, {})
    action = control.get("action")
    
    if action == "stop":
        logger.info(f"任务 {task_id} 在步骤 {step_name} 被停止")
        raise Exception(f"任务已被用户停止")
    elif action == "pause":
        logger.info(f"任务 {task_id} 在步骤 {step_name} 被暂停")
        # 等待恢复或停止
        while task_control_states.get(task_id, {}).get("action") == "pause":
            await asyncio.sleep(1)
        # 重新检查状态
        await check_task_control(task_id, step_name)

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


class GroupUpdateRequest(BaseModel):
    """分组更新请求模型"""
    uid: int
    group_id: int


class BatchGroupUpdateRequest(BaseModel):
    """批量分组更新请求模型"""
    uids: List[int]
    group_id: int


class TaskControlRequest(BaseModel):
    """任务控制请求模型"""
    task_id: str
    action: str  # "pause", "resume", "stop"


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
        
        # 首先同步分组信息
        logger.info("开始同步分组信息...")
        bilibili_groups = await api.get_follow_groups()
        if bilibili_groups:
            for group in bilibili_groups:
                group_id = group.get('tagid', 0)
                group_name = group.get('name', '未知分组')
                group_count = group.get('count', 0)
                
                if group_id > 0:  # 跳过默认分组
                    await db_manager.insert_or_update_follow_group(
                        group_id, group_name, group_count
                    )
            logger.info(f"分组信息同步完成，共 {len(bilibili_groups)} 个分组")
        
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
                
                # 从B站API中获取分组信息 (tag数组包含分组ID)
                tag_list = user.get('tag', [])
                if isinstance(tag_list, list) and tag_list:
                    # 取第一个分组ID作为主分组
                    group_id = tag_list[0]
                    user['group_id'] = group_id
                    logger.debug(f"用户 {uname} 属于分组 {group_id}")
                else:
                    # 默认分组
                    user['group_id'] = 0
                
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


@router.get("/statistics")
async def get_statistics(req: Request):
    """获取详细统计数据"""
    try:
        db_manager = req.app.state.db_manager
        following_list = await db_manager.get_following_list()
        
        total_count = 0
        categorized_count = 0
        vip_count = 0
        official_count = 0
        
        for user in following_list:
            total_count += 1
            
            # 已分类用户：有category且不为空、不为null、不为"其他"
            category = user.get("category", "")
            if category and category.strip() != "" and category != "其他" and category != "null":
                categorized_count += 1
            
            # VIP用户：使用正确的字段检查
            vip_type = user.get("vip_type", 0)
            try:
                vip_type = int(vip_type) if vip_type is not None else 0
            except (ValueError, TypeError):
                vip_type = 0
            
            if vip_type > 0:
                vip_count += 1
            
            # 认证用户：使用正确的字段检查  
            official_type = user.get("official_type", -1)
            try:
                official_type = int(official_type) if official_type is not None else -1
            except (ValueError, TypeError):
                official_type = -1
                
            if official_type >= 0:
                official_count += 1
        
        return {
            "total_count": total_count,
            "categorized_count": categorized_count,
            "vip_count": vip_count,
            "official_count": official_count
        }
    except Exception as e:
        logger.error(f"获取统计数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取统计数据失败")


@router.post("/unfollow")
async def batch_unfollow(request: UnfollowRequest, req: Request):
    """批量取消关注"""
    if not request.uids:
        raise HTTPException(status_code=400, detail="用户ID列表不能为空")
    
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        # 从B站取消关注
        success_count, error_count = await api.batch_unfollow_users(request.uids)
        
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


@router.get("/groups")
async def get_follow_groups(req: Request):
    """获取关注分组列表"""
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        logger.info("开始获取关注分组列表")
        
        # 首先尝试从B站获取最新分组数据
        bilibili_groups = await api.get_follow_groups()
        
        if bilibili_groups:
            logger.info(f"从B站获取到 {len(bilibili_groups)} 个分组")
            # 更新本地数据库中的分组信息
            for group in bilibili_groups:
                group_id = group.get('tagid', 0)
                group_name = group.get('name', '未知分组')
                group_count = group.get('count', 0)
                
                logger.debug(f"处理分组: ID={group_id}, 名称={group_name}, 用户数={group_count}")
                
                if group_id > 0:  # 默认分组ID通常为0，跳过
                    await db_manager.insert_or_update_follow_group(
                        group_id, group_name, group_count
                    )
        else:
            logger.warning("未能从B站获取分组数据，可能是API权限问题")
        
        # 从数据库获取分组列表（包含实际用户数量）
        groups = await db_manager.get_follow_groups()
        
        # 检查数据库中的用户总数
        total_users = await db_manager.get_following_count()
        logger.info(f"数据库中共有 {total_users} 个关注用户，{len(groups)} 个分组")
        
        return {"groups": groups}
    except Exception as e:
        logger.error(f"获取关注分组失败: {e}")
        raise HTTPException(status_code=500, detail="获取关注分组失败")


@router.get("/groups/{group_id}/following")
async def get_group_following(
    group_id: int,
    req: Request,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    sort_by: Optional[str] = "follow_time",
    sort_order: Optional[str] = "desc"
):
    """获取指定分组的关注列表"""
    try:
        logger.info(f"获取分组 {group_id} 的关注列表 - 页码: {page}, 每页: {page_size}, 搜索: {search}")
        
        db_manager = req.app.state.db_manager
        offset = (page - 1) * page_size
        
        following_list = await db_manager.get_following_by_group(
            group_id=group_id, limit=page_size, offset=offset, 
            search=search, sort_by=sort_by, sort_order=sort_order
        )
        
        total_count = await db_manager.get_following_count_by_group(group_id)
        
        logger.info(f"分组 {group_id} 查询结果: 找到 {len(following_list)} 个用户, 总计 {total_count} 个")
        
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
        logger.error(f"获取分组关注列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取分组关注列表失败")


@router.get("/groups-distribution")
async def get_groups_distribution(req: Request, ignore_ungrouped: bool = False):
    """获取B站分组分布分析"""
    try:
        db_manager = req.app.state.db_manager
        groups = await db_manager.get_follow_groups()
        
        # 构建分布数据
        distribution = {}
        for group in groups:
            group_name = group.get('group_name', '未知分组')
            group_id = group.get('group_id', 0)
            
            # 如果启用忽略未分组，则跳过未分组数据
            if ignore_ungrouped and (group_id == 0 or group_name in ['未分组', '默认分组']):
                continue
                
            # 使用实际用户数量，优先使用actual_count，其次是group_count
            user_count = group.get('actual_count', 0) or group.get('group_count', 0)
            if user_count > 0:
                distribution[group_name] = user_count
        
        return {
            "distribution": {
                "category_distribution": distribution
            },
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取分组分布失败: {e}")
        raise HTTPException(status_code=500, detail="获取分组分布失败")


@router.get("/groups-stats")
async def get_groups_statistics(req: Request):
    """获取B站分组统计信息"""
    try:
        db_manager = req.app.state.db_manager
        
        # 获取总用户数
        total_count = await db_manager.get_following_count()
        
        # 获取分组信息
        groups = await db_manager.get_follow_groups()
        
        # 计算已分组用户数（排除默认分组）
        grouped_count = sum(
            group.get('actual_count', 0) or group.get('group_count', 0)
            for group in groups 
            if group.get('group_id', 0) > 0
        )
        
        # 获取VIP和认证用户统计
        following_list = await db_manager.get_following_list()
        vip_count = sum(1 for user in following_list if user.get('vip_type', 0) > 0)
        official_count = sum(1 for user in following_list if user.get('official_type', -1) >= 0)
        
        return {
            "total_count": total_count,
            "grouped_count": grouped_count,
            "vip_count": vip_count,
            "official_count": official_count,
            "total_groups": len([g for g in groups if g.get('group_id', 0) > 0])
        }
    except Exception as e:
        logger.error(f"获取分组统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取分组统计失败")


@router.post("/update-group")
async def update_user_group(request: GroupUpdateRequest, req: Request):
    """更新用户分组"""
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        # 先同步到B站
        bilibili_success = await api.modify_user_group(request.uid, request.group_id)
        
        if bilibili_success:
            # 只有B站同步成功时才更新本地数据库
            db_success = await db_manager.update_user_group(request.uid, request.group_id)
            if db_success:
                return {"message": "分组更新成功", "bilibili_synced": True}
            else:
                logger.warning(f"B站同步成功但本地数据库更新失败，用户ID: {request.uid}")
                return {"message": "B站同步成功，但本地数据库更新失败", "bilibili_synced": True}
        else:
            raise HTTPException(status_code=400, detail="B站分组更新失败，未更新本地数据")
    except Exception as e:
        logger.error(f"更新用户分组失败: {e}")
        raise HTTPException(status_code=500, detail="更新用户分组失败")


@router.post("/batch-update-group")
async def batch_update_user_group(request: BatchGroupUpdateRequest, req: Request):
    """批量更新用户分组"""
    if not request.uids:
        raise HTTPException(status_code=400, detail="用户ID列表不能为空")
    
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        success_count = 0
        error_count = 0
        bilibili_sync_errors = 0
        
        for uid in request.uids:
            try:
                # 先同步到B站
                bilibili_success = await api.modify_user_group(uid, request.group_id)
                
                if bilibili_success:
                    # 只有B站同步成功时才更新本地数据库
                    db_success = await db_manager.update_user_group(uid, request.group_id)
                    if db_success:
                        success_count += 1
                    else:
                        error_count += 1
                        logger.warning(f"用户 {uid} B站同步成功但本地数据库更新失败")
                else:
                    bilibili_sync_errors += 1
                    error_count += 1
                    logger.warning(f"用户 {uid} B站分组更新失败")
            except Exception as e:
                logger.error(f"批量更新用户 {uid} 分组时出错: {e}")
                error_count += 1
        
        message = f"批量分组更新完成：成功 {success_count}，失败 {error_count}"
        if bilibili_sync_errors > 0:
            message += f"，其中B站同步失败 {bilibili_sync_errors} 个"
        
        return {
            "message": message,
            "success_count": success_count,
            "error_count": error_count,
            "bilibili_sync_errors": bilibili_sync_errors
        }
    except Exception as e:
        logger.error(f"批量更新分组失败: {e}")
        raise HTTPException(status_code=500, detail="批量更新分组失败")


@router.get("/debug/data-status")
async def debug_data_status(req: Request):
    """调试：检查数据状态"""
    try:
        db_manager = req.app.state.db_manager
        
        # 检查关注用户总数
        total_users = await db_manager.get_following_count()
        
        # 检查分组数量
        groups = await db_manager.get_follow_groups()
        
        # 检查未分组用户数量
        ungrouped_count = await db_manager.get_following_count_by_group(0)
        
        # 检查每个分组的用户数量
        group_details = []
        for group in groups:
            group_id = group['group_id']
            actual_count = await db_manager.get_following_count_by_group(group_id)
            group_details.append({
                "group_id": group_id,
                "group_name": group['group_name'],
                "stored_count": group.get('actual_count', 0),
                "real_count": actual_count
            })
        
        # 随机抽取一些用户数据检查
        sample_users = await db_manager.get_following_list(limit=5)
        
        # 检查B站分组分布
        distribution_data = {}
        for group in groups:
            group_name = group.get('group_name', '未知分组')
            user_count = group.get('actual_count', 0) or group.get('group_count', 0)
            if user_count > 0:
                distribution_data[group_name] = user_count
        
        return {
            "total_users": total_users,
            "total_groups": len(groups),
            "ungrouped_users": ungrouped_count,
            "group_details": group_details,
            "sample_users": [
                {
                    "uid": user.get('uid'),
                    "uname": user.get('uname'),
                    "group_id": user.get('group_id'),
                    "category": user.get('category')
                } for user in sample_users
            ],
            "distribution_preview": distribution_data,
            "groups_raw": groups  # 添加原始分组数据用于调试
        }
    except Exception as e:
        logger.error(f"获取调试数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取调试数据失败")


@router.post("/fix-user-levels")
async def fix_user_levels(req: Request):
    """修复用户等级信息"""
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        logger.info("开始修复用户等级信息...")
        
        # 获取所有等级为0的用户
        following_list = await db_manager.get_following_list()
        users_to_fix = [user for user in following_list if user.get('level', 0) == 0]
        
        if not users_to_fix:
            return {"message": "没有需要修复的用户", "fixed_count": 0}
        
        logger.info(f"发现 {len(users_to_fix)} 个需要修复等级信息的用户")
        
        fixed_count = 0
        error_count = 0
        wind_control_detected = False
        consecutive_failures = 0
        
        for i, user in enumerate(users_to_fix):
            try:
                uid = user.get('uid')
                if not uid:
                    continue
                
                # 检测风控情况
                if consecutive_failures >= 5:
                    logger.warning("检测到可能的风控限制，暂停修复过程")
                    wind_control_detected = True
                    break
                
                # 获取用户详细信息
                user_detail = await api.get_user_info(uid)
                if user_detail and user_detail.get('card'):
                    card_info = user_detail['card']
                    
                    if 'level_info' in card_info:
                        new_level = card_info['level_info'].get('current_level', 0)
                        
                        # 更新数据库中的等级信息
                        if new_level > 0:
                            await db_manager._connection.execute(
                                "UPDATE following_list SET level = ? WHERE uid = ?",
                                (new_level, uid)
                            )
                            await db_manager._connection.commit()
                            fixed_count += 1
                            consecutive_failures = 0  # 成功时重置失败计数
                            logger.debug(f"用户 {user.get('uname', 'Unknown')} 等级已更新: {new_level}")
                        else:
                            logger.debug(f"用户 {user.get('uname', 'Unknown')} 等级仍为0，可能是真实等级")
                    else:
                        consecutive_failures += 1
                        logger.warning(f"用户 {user.get('uname', 'Unknown')} 等级信息不可用")
                elif user_detail is None:
                    # API调用失败
                    consecutive_failures += 1
                    error_count += 1
                    logger.warning(f"获取用户 {user.get('uname', 'Unknown')} 详细信息失败，连续失败 {consecutive_failures} 次")
                    
                    # 如果连续失败过多，增加等待时间
                    if consecutive_failures >= 3:
                        wait_time = min(consecutive_failures * 2, 10)
                        logger.warning(f"连续失败过多，等待 {wait_time} 秒")
                        await asyncio.sleep(wait_time)
                
                # 每修复10个用户后稍微休息
                if (i + 1) % 10 == 0:
                    base_delay = 1.0 if consecutive_failures == 0 else min(consecutive_failures * 0.5, 3.0)
                    await asyncio.sleep(base_delay)
                    logger.info(f"已处理 {i + 1}/{len(users_to_fix)} 个用户，成功修复 {fixed_count} 个")
                elif (i + 1) % 5 == 0:
                    # 每5个用户也稍微休息
                    await asyncio.sleep(0.3)
                
            except Exception as e:
                error_count += 1
                consecutive_failures += 1
                logger.error(f"修复用户 {user.get('uname', 'Unknown')} 等级信息失败: {e}")
        
        # 构建返回消息
        if wind_control_detected:
            message = f"等级信息修复因风控限制而停止"
        else:
            message = f"等级信息修复完成"
        
        logger.info(f"修复结果: 处理 {min(i + 1, len(users_to_fix))} 个用户，成功修复 {fixed_count} 个，失败 {error_count} 个")
        
        return {
            "message": message,
            "total_users": len(users_to_fix),
            "processed_users": min(i + 1, len(users_to_fix)) if 'i' in locals() else 0,
            "fixed_count": fixed_count,
            "error_count": error_count,
            "wind_control_detected": wind_control_detected
        }
        
    except Exception as e:
        logger.error(f"修复用户等级信息失败: {e}")
        raise HTTPException(status_code=500, detail="修复用户等级信息失败")


@router.post("/sync-user-stats")
async def sync_user_stats(req: Request, background_tasks: BackgroundTasks, limit: int = 0):
    """同步用户真实统计数据（从B站API获取）"""
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        if not api.is_configured():
            raise HTTPException(status_code=400, detail="请先配置哔哩哔哩Cookie")
        
        # 创建任务ID和进度跟踪
        import time
        task_id = f"sync_stats_{int(time.time())}"
        
        # 初始化进度跟踪缓存
        if not hasattr(db_manager, '_sync_progress_cache'):
            db_manager._sync_progress_cache = {}
        
        # 获取所有关注的用户
        following_list = await db_manager.get_following_list()
        
        # 根据limit决定处理用户数量
        if limit == 0:
            users_to_process = following_list  # 处理全部用户
            logger.info(f"开始同步全部 {len(following_list)} 个用户的真实统计数据")
        else:
            users_to_process = following_list[:limit]
            logger.info(f"开始同步 {len(users_to_process)} 个用户的真实统计数据")
        
        # 初始化进度信息
        progress_info = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "total_users": len(users_to_process),
            "processed_users": 0,
            "updated_count": 0,
            "error_count": 0,
            "current_user": "",
            "start_time": datetime.now(),
            "end_time": None,
            "message": "开始同步用户统计数据..."
        }
        db_manager._sync_progress_cache[task_id] = progress_info
        
        # 在后台执行同步任务
        background_tasks.add_task(_sync_user_stats_task, db_manager, task_id, users_to_process, limit)
        
        return {
            "message": "用户统计数据同步任务已启动",
            "task_id": task_id,
            "total_users": len(users_to_process),
            "status": "started"
        }
        
    except Exception as e:
        logger.error(f"启动同步用户统计数据任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动同步失败: {str(e)}")


async def _sync_user_stats_task(db_manager, task_id: str, users_to_process: list, limit: int):
    """同步用户统计数据的后台任务"""
    api = None
    start_time = datetime.now()
    max_task_duration = 6 * 60 * 60  # 最大任务时长6小时
    
    try:
        api = await get_bilibili_api()
        
        # 确保缓存存在
        if not hasattr(db_manager, '_sync_progress_cache'):
            db_manager._sync_progress_cache = {}
        
        # 检查任务是否还存在
        if task_id not in db_manager._sync_progress_cache:
            logger.error(f"任务 {task_id} 的进度缓存不存在，无法执行同步")
            return
        
        # 添加调试信息
        logger.info(f"后台任务开始 - task_id: {task_id}, 用户数量: {len(users_to_process)}")
        
        updated_count = 0
        error_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 15  # 增加容忍度，避免过早停止
        total_api_errors = 0
        max_total_errors = len(users_to_process) // 2  # 允许最多一半用户失败
        
        # 风控检测优化
        recent_failure_window = []  # 最近失败的时间窗口
        failure_window_size = 30  # 30次请求的窗口
        failure_rate_threshold = 0.7  # 失败率超过70%时认为可能遇到风控
        
        for i, user in enumerate(users_to_process):
            try:
                # 检查任务超时
                elapsed_time = (datetime.now() - start_time).total_seconds()
                if elapsed_time > max_task_duration:
                    logger.warning(f"任务 {task_id} 超过最大执行时间({max_task_duration/3600:.1f}小时)，停止同步")
                    if task_id in db_manager._sync_progress_cache:
                        db_manager._sync_progress_cache[task_id]["status"] = "timeout"
                        db_manager._sync_progress_cache[task_id]["message"] = f"任务超时停止，已处理 {i+1} 个用户"
                    break
                
                uid = user["uid"]
                uname = user.get('uname', str(uid))
                
                # 确保缓存仍然存在
                if task_id not in db_manager._sync_progress_cache:
                    logger.warning(f"任务 {task_id} 的进度缓存已丢失，停止同步")
                    break
                
                # 改进的风控检测：基于最近的失败率而不是连续失败
                if len(recent_failure_window) >= failure_window_size:
                    recent_failures = sum(recent_failure_window)
                    failure_rate = recent_failures / failure_window_size
                    
                    if failure_rate > failure_rate_threshold:
                        logger.warning(f"检测到高失败率({failure_rate:.1%})，可能遇到风控限制，暂停60秒...")
                        if task_id in db_manager._sync_progress_cache:
                            db_manager._sync_progress_cache[task_id]["message"] = f"检测到高失败率，暂停60秒... ({i+1}/{len(users_to_process)})"
                        await asyncio.sleep(60)  # 暂停1分钟
                        recent_failure_window.clear()  # 清空失败窗口，重新开始
                        consecutive_failures = 0  # 重置连续失败计数
                
                # 检查总错误率，如果太高则停止
                if total_api_errors > max_total_errors:
                    logger.warning(f"总错误数({total_api_errors})超过限制({max_total_errors})，停止同步")
                    if task_id in db_manager._sync_progress_cache:
                        db_manager._sync_progress_cache[task_id]["status"] = "stopped"
                        db_manager._sync_progress_cache[task_id]["message"] = f"错误率过高，停止同步：已处理 {i+1} 个用户"
                    break
                
                # 更新当前处理状态（开始处理前）
                if task_id in db_manager._sync_progress_cache:
                    db_manager._sync_progress_cache[task_id]["current_user"] = uname
                    db_manager._sync_progress_cache[task_id]["message"] = f"正在同步用户 {uname} ({i+1}/{len(users_to_process)})"
                    db_manager._sync_progress_cache[task_id]["last_heartbeat"] = datetime.now().isoformat()
                
                # 从B站API获取真实统计数据
                logger.info(f"开始获取用户 {uname} (UID: {uid}) 的统计数据...")
                
                # 添加API调用超时
                try:
                    real_stats = await asyncio.wait_for(api.get_user_stats(uid), timeout=30.0)
                    api_success = real_stats is not None
                except asyncio.TimeoutError:
                    logger.warning(f"获取用户 {uname} 统计数据超时")
                    real_stats = None
                    api_success = False
                except Exception as api_e:
                    logger.warning(f"获取用户 {uname} 统计数据异常: {api_e}")
                    real_stats = None
                    api_success = False
                
                # 更新失败窗口
                recent_failure_window.append(0 if api_success else 1)
                if len(recent_failure_window) > failure_window_size:
                    recent_failure_window.pop(0)
                
                if real_stats:
                    # 更新或插入到数据库
                    cursor = await db_manager._connection.execute(
                        "SELECT uid FROM user_stats WHERE uid = ?", (uid,)
                    )
                    existing = await cursor.fetchone()
                    
                    if existing:
                        # 更新现有记录
                        await db_manager._connection.execute("""
                            UPDATE user_stats SET 
                                fans_count = ?, following_count = ?, video_count = ?,
                                total_views = ?, last_video_time = ?, activity_score = ?
                            WHERE uid = ?
                        """, (
                            real_stats["fans_count"], real_stats["following_count"], 
                            real_stats["video_count"], real_stats["total_views"],
                            real_stats["last_video_time"], real_stats["activity_score"], uid
                        ))
                    else:
                        # 插入新记录
                        await db_manager._connection.execute("""
                            INSERT INTO user_stats 
                            (uid, fans_count, following_count, video_count, total_views, 
                             last_video_time, activity_score) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            uid, real_stats["fans_count"], real_stats["following_count"],
                            real_stats["video_count"], real_stats["total_views"],
                            real_stats["last_video_time"], real_stats["activity_score"]
                        ))
                    
                    # 立即提交每个用户的更改，避免程序异常退出时数据丢失
                    await db_manager._connection.commit()
                    
                    updated_count += 1
                    consecutive_failures = 0  # 成功后重置失败计数
                    logger.info(f"已更新用户 {uname} 的真实统计数据 (成功: {updated_count}, 失败: {error_count})")
                else:
                    error_count += 1
                    total_api_errors += 1
                    consecutive_failures += 1
                    logger.warning(f"获取用户 {uname} 统计数据失败，连续失败 {consecutive_failures} 次 (成功: {updated_count}, 失败: {error_count})")
                
                # 确保缓存仍然存在再更新进度
                if task_id in db_manager._sync_progress_cache:
                    # 处理完成后立即更新所有进度信息，确保数据一致性
                    db_manager._sync_progress_cache[task_id]["processed_users"] = i + 1
                    db_manager._sync_progress_cache[task_id]["updated_count"] = updated_count
                    db_manager._sync_progress_cache[task_id]["error_count"] = error_count
                    # 修复进度计算，使用浮点数保留更高精度
                    progress_percentage = round(((i + 1) / len(users_to_process)) * 100, 2)
                    db_manager._sync_progress_cache[task_id]["progress"] = progress_percentage
                    
                    # 添加调试信息
                    progress_info = db_manager._sync_progress_cache[task_id]
                    logger.info(f"更新进度信息: processed={progress_info['processed_users']}, updated={progress_info['updated_count']}, error={progress_info['error_count']}, progress={progress_info['progress']}%")
                    
                    # 强制更新缓存引用，确保数据一致性
                    db_manager._sync_progress_cache[task_id]["last_update"] = datetime.now().isoformat()
                
                # 根据用户数量和失败情况调整延迟，由于API限制增加延迟
                if limit == 0:  # 全部用户模式，使用更长延迟
                    base_delay = 6.0 if consecutive_failures == 0 else min(consecutive_failures * 2.0, 20.0)
                elif limit >= 50:  # 大批量模式
                    base_delay = 5.0 if consecutive_failures == 0 else min(consecutive_failures * 1.5, 15.0)
                else:  # 小批量模式
                    base_delay = 4.0 if consecutive_failures == 0 else min(consecutive_failures * 1.0, 12.0)
                
                logger.info(f"等待 {base_delay:.1f} 秒后处理下一个用户...")
                await asyncio.sleep(base_delay)
                
                # 每处理5个用户报告一次进度
                if (i + 1) % 5 == 0:
                    logger.info(f"进度: {i + 1}/{len(users_to_process)}, 成功: {updated_count}, 失败: {error_count}, 总耗时: {elapsed_time/60:.1f}分钟")
                    
                    # 每处理10个用户后强制进行垃圾回收，释放内存
                    if (i + 1) % 10 == 0:
                        gc.collect()
                        logger.debug(f"已处理 {i + 1} 个用户，执行垃圾回收释放内存")
                
            except Exception as e:
                error_count += 1
                total_api_errors += 1
                consecutive_failures += 1
                logger.error(f"同步用户 {user.get('uname', uid)} 统计数据失败: {e} (成功: {updated_count}, 失败: {error_count})")
                
                # 确保缓存仍然存在再更新错误状态
                if task_id in db_manager._sync_progress_cache:
                    # 立即更新错误状态到进度信息，确保前端能获取到最新进度
                    db_manager._sync_progress_cache[task_id]["updated_count"] = updated_count
                    db_manager._sync_progress_cache[task_id]["error_count"] = error_count
                    db_manager._sync_progress_cache[task_id]["processed_users"] = i + 1
                    db_manager._sync_progress_cache[task_id]["progress"] = round(((i + 1) / len(users_to_process)) * 100, 2)
                    
                    # 添加调试信息
                    progress_info = db_manager._sync_progress_cache[task_id]
                    logger.info(f"异常后更新进度信息: processed={progress_info['processed_users']}, updated={progress_info['updated_count']}, error={progress_info['error_count']}")
        
        # 数据库更改已在每个用户处理后立即提交，无需再次提交
        
        # 确保缓存仍然存在再更新最终状态
        if task_id in db_manager._sync_progress_cache:
            # 判断任务完成状态
            current_status = db_manager._sync_progress_cache[task_id].get("status", "running")
            if current_status == "running":  # 只有在running状态下才更新为completed
                final_status = "completed"
            else:
                final_status = current_status  # 保持已设置的状态（如timeout、stopped等）
            
            # 更新最终进度信息
            db_manager._sync_progress_cache[task_id]["status"] = final_status
            db_manager._sync_progress_cache[task_id]["progress"] = 100 if final_status == "completed" else db_manager._sync_progress_cache[task_id].get("progress", 0)
            db_manager._sync_progress_cache[task_id]["updated_count"] = updated_count
            db_manager._sync_progress_cache[task_id]["error_count"] = error_count
            db_manager._sync_progress_cache[task_id]["end_time"] = datetime.now()
            
            # 构建返回消息
            if final_status == "completed":
                db_manager._sync_progress_cache[task_id]["message"] = f"同步完成：成功更新 {updated_count} 个用户，失败 {error_count} 个用户"
            elif final_status == "timeout":
                db_manager._sync_progress_cache[task_id]["message"] = f"同步超时：已处理 {len(users_to_process)} 个用户中的 {db_manager._sync_progress_cache[task_id].get('processed_users', 0)} 个"
            elif final_status == "stopped":
                db_manager._sync_progress_cache[task_id]["message"] = f"同步停止：已处理 {db_manager._sync_progress_cache[task_id].get('processed_users', 0)} 个用户"
        
        logger.info(f"用户统计数据同步任务 {task_id} 完成：更新 {updated_count} 个用户，失败 {error_count} 个用户，状态: {final_status}")
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"同步用户统计数据任务失败: {e}")
        logger.error(f"错误详情: {error_details}")
        
        # 更新错误状态
        if hasattr(db_manager, '_sync_progress_cache') and task_id in db_manager._sync_progress_cache:
            db_manager._sync_progress_cache[task_id]["status"] = "failed"
            db_manager._sync_progress_cache[task_id]["message"] = f"同步失败: {str(e)}"
            db_manager._sync_progress_cache[task_id]["end_time"] = datetime.now()
    
    finally:
        # 确保API资源被正确清理
        if api is not None:
            try:
                await api.close()
            except Exception as e:
                logger.warning(f"关闭API连接时出错: {e}")


@router.get("/sync-user-stats/{task_id}/progress")
async def get_sync_progress(task_id: str, req: Request):
    """获取用户统计数据同步进度"""
    try:
        db_manager = req.app.state.db_manager
        
        # 添加调试信息
        logger.info(f"获取同步进度请求 - task_id: {task_id}")
        logger.info(f"_sync_progress_cache 是否存在: {hasattr(db_manager, '_sync_progress_cache')}")
        
        if hasattr(db_manager, '_sync_progress_cache'):
            logger.info(f"缓存中的所有task_id: {list(db_manager._sync_progress_cache.keys())}")
            if task_id in db_manager._sync_progress_cache:
                progress_info = db_manager._sync_progress_cache[task_id]
                logger.info(f"找到进度信息: processed={progress_info.get('processed_users', 0)}, updated={progress_info.get('updated_count', 0)}")
            else:
                logger.warning(f"task_id {task_id} 不在缓存中")
        
        if not hasattr(db_manager, '_sync_progress_cache') or task_id not in db_manager._sync_progress_cache:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        
        progress_info = db_manager._sync_progress_cache[task_id]
        
        # 检查任务是否超时（基于心跳机制）
        current_time = datetime.now()
        
        # 检查是否有心跳时间记录
        last_heartbeat_str = progress_info.get("last_heartbeat")
        if last_heartbeat_str:
            try:
                last_heartbeat = datetime.fromisoformat(last_heartbeat_str)
                time_since_heartbeat = (current_time - last_heartbeat).total_seconds()
                
                # 如果超过5分钟没有心跳且任务仍在运行，标记为超时
                if time_since_heartbeat > 300 and progress_info.get("status") == "running":
                    logger.warning(f"任务 {task_id} 超过5分钟没有心跳更新，标记为超时")
                    progress_info["status"] = "timeout"
                    progress_info["message"] = f"任务超时：超过5分钟未响应（最后心跳: {last_heartbeat_str}）"
                    progress_info["end_time"] = current_time
                    
            except ValueError as e:
                logger.warning(f"解析心跳时间失败: {e}")
        
        # 检查任务开始时间，如果总运行时间超过7小时且仍在运行，标记为超时
        start_time = progress_info.get("start_time")
        if start_time and progress_info.get("status") == "running":
            try:
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time)
                
                total_runtime = (current_time - start_time).total_seconds()
                max_runtime = 7 * 60 * 60  # 7小时
                
                if total_runtime > max_runtime:
                    logger.warning(f"任务 {task_id} 总运行时间超过7小时，标记为超时")
                    progress_info["status"] = "timeout"
                    progress_info["message"] = f"任务超时：总运行时间超过7小时"
                    progress_info["end_time"] = current_time
                    
            except (ValueError, TypeError) as e:
                logger.warning(f"解析开始时间失败: {e}")
        
        # 返回进度信息
        result = {
            "task_id": task_id,
            "status": progress_info.get("status", "running"),
            "progress": progress_info.get("progress", 0),
            "total_users": progress_info.get("total_users", 0),
            "processed_users": progress_info.get("processed_users", 0),
            "updated_count": progress_info.get("updated_count", 0),
            "error_count": progress_info.get("error_count", 0),
            "current_user": progress_info.get("current_user", ""),
            "message": progress_info.get("message", "正在同步..."),
            "start_time": progress_info["start_time"].isoformat() if progress_info.get("start_time") and hasattr(progress_info["start_time"], 'isoformat') else str(progress_info.get("start_time", "")),
            "end_time": progress_info["end_time"].isoformat() if progress_info.get("end_time") and hasattr(progress_info["end_time"], 'isoformat') else str(progress_info.get("end_time", ""))
        }
        
        logger.info(f"返回进度信息: {result}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取同步进度失败: {e}")
        raise HTTPException(status_code=500, detail="获取同步进度失败")


@router.post("/one-click-update")
async def one_click_update_all(background_tasks: BackgroundTasks, req: Request, mode: str = "standard"):
    """一键更新所有信息：关注列表、分组信息、用户统计、等级信息等
    
    Args:
        mode: 更新模式，"standard"（标准模式）或 "conservative"（保守模式）
    """
    try:
        api = await get_bilibili_api()
        
        if not api.is_configured():
            raise HTTPException(status_code=400, detail="未配置哔哩哔哩Cookie")
        
        # 创建一个唯一的任务ID
        import time
        task_id = f"update_{mode}_{int(time.time())}"
        
        # 在后台执行一键更新任务
        background_tasks.add_task(_one_click_update_task, req.app.state.db_manager, task_id, mode)
        
        mode_name = "保守模式" if mode == "conservative" else "标准模式"
        return {
            "message": f"一键更新任务已启动（{mode_name}）", 
            "status": "started", 
            "task_id": task_id,
            "mode": mode
        }
        
    except Exception as e:
        logger.error(f"启动一键更新任务失败: {e}")
        raise HTTPException(status_code=500, detail="启动一键更新任务失败")


@router.post("/one-click-update-conservative")
async def one_click_update_conservative(background_tasks: BackgroundTasks, req: Request):
    """保守模式一键更新所有信息"""
    return await one_click_update_all(background_tasks, req, mode="conservative")


@router.post("/one-click-update-optimized")
async def one_click_update_optimized(background_tasks: BackgroundTasks, req: Request):
    """优化版一键更新所有信息"""
    try:
        db_manager = req.app.state.db_manager
        task_id = f"optimized_update_{int(time.time())}"
        
        # 启动后台任务
        background_tasks.add_task(_one_click_update_optimized_task, db_manager, task_id)
        
        logger.info(f"启动优化版一键更新任务: {task_id}")
        
        return {
            "message": "优化版一键更新任务已启动",
            "task_id": task_id,
            "mode": "optimized",
            "monitor_url": f"/api/bilibili/one-click-update-optimized/{task_id}"
        }
        
    except Exception as e:
        logger.error(f"启动优化版一键更新任务失败: {e}")
        raise HTTPException(status_code=500, detail="启动优化版一键更新任务失败")


async def _one_click_update_optimized_task(db_manager, task_id):
    """优化版一键更新任务（后台执行）"""
    import time
    from datetime import datetime
    
    # 记录开始时间
    start_time = time.time()
    
    # 初始化更新结果结构
    update_results = {
        "task_id": task_id,
        "start_time": datetime.now().isoformat(),
        "mode": "optimized",
        "optimization_enabled": True,
        "steps": {
            "sync_following": {"status": "pending", "start_time": None, "end_time": None, "details": "", "count": 0},
            "groups_sync": {"status": "pending", "start_time": None, "end_time": None, "details": "", "count": 0},
            "sync_user_stats": {"status": "pending", "start_time": None, "end_time": None, "details": "", "count": 0},
            "fix_levels": {"status": "pending", "start_time": None, "end_time": None, "details": "", "count": 0},
            "auto_categorize": {"status": "pending", "start_time": None, "end_time": None, "details": "", "count": 0}
        },
        "progress": 0,
        "status": "running",
        "total_users": 0,
        "processed_users": 0,
        "failed_users": 0,
        "skipped_users": 0,
        "notifications": [],
        "optimization_stats": {
            "parallel_requests": 0,
            "cache_hits": 0,
            "time_saved": 0
        }
    }
    
    # 初始化更新状态存储（使用数据库管理器的缓存机制）
    if not hasattr(db_manager, '_update_cache'):
        db_manager._update_cache = {}
    db_manager._update_cache[task_id] = update_results
    
    try:
        api = await get_bilibili_api()
        if not api.is_configured():
            update_results["status"] = "failed"
            update_results["error"] = "未配置哔哩哔哩Cookie"
            return
        
        logger.info(f"开始优化版一键更新任务 {task_id}")
        
        # === 步骤1：优化版同步关注列表和分组 ===
        step_name = "sync_following"
        logger.info("步骤1: 开始优化版同步关注列表")
        
        update_results["steps"][step_name]["status"] = "running"
        update_results["steps"][step_name]["start_time"] = datetime.now().isoformat()
        add_step_notification(update_results, step_name, "开始", "🚀 使用优化策略并发获取关注列表")
        
        # 同时启动分组同步步骤显示
        groups_step_name = "groups_sync"
        update_results["steps"][groups_step_name]["status"] = "running"
        update_results["steps"][groups_step_name]["start_time"] = datetime.now().isoformat()
        add_step_notification(update_results, groups_step_name, "开始", "🔄 并发获取分组信息")
        
        def progress_callback_following(current, total):
            update_results["total_users"] = total
            update_results["processed_users"] = current
            update_results["progress"] = min(25, (current / total) * 25) if total > 0 else 0
            update_results["steps"][step_name]["details"] = f"已获取 {current}/{total} 个关注用户"
            # 添加详细进度日志
            if current % 100 == 0 or current == total:
                logger.info(f"关注列表获取进度: {current}/{total} ({(current/total*100):.1f}%)")
        
        try:
            step_start = time.time()
            
            logger.info("开始并发获取关注列表和分组信息（优化版）")
            
            # 使用优化的合并获取方法
            following_list, bilibili_groups = await api.get_following_and_groups_combined(
                progress_callback=progress_callback_following
            )
            
            step_duration = time.time() - step_start
            update_results["optimization_stats"]["time_saved"] += max(0, step_duration * 0.3)  # 估算节省时间
            
            logger.info(f"关注列表获取完成: {len(following_list)} 个用户")
            
            # 处理分组信息
            groups_processed = 0
            if bilibili_groups:
                logger.info(f"开始处理 {len(bilibili_groups)} 个分组信息")
                for group in bilibili_groups:
                    group_id = group.get('tagid', 0)
                    group_name = group.get('name', '未知分组')
                    group_count = group.get('count', 0)
                    
                    if group_id > 0:
                        await db_manager.insert_or_update_follow_group(
                            group_id, group_name, group_count
                        )
                        groups_processed += 1
                        logger.debug(f"处理分组: {group_name} (ID: {group_id}, 用户数: {group_count})")
                
                # 更新分组同步状态
                update_results["steps"][groups_step_name]["status"] = "completed"
                update_results["steps"][groups_step_name]["end_time"] = datetime.now().isoformat()
                update_results["steps"][groups_step_name]["details"] = f"同步完成: {groups_processed} 个分组"
                update_results["steps"][groups_step_name]["count"] = groups_processed
                add_step_notification(update_results, groups_step_name, "完成", f"✅ 成功同步 {groups_processed} 个分组")
                logger.info(f"分组信息同步完成，共处理 {groups_processed} 个分组")
            else:
                update_results["steps"][groups_step_name]["status"] = "completed"
                update_results["steps"][groups_step_name]["end_time"] = datetime.now().isoformat()
                update_results["steps"][groups_step_name]["details"] = "无分组数据"
                update_results["steps"][groups_step_name]["count"] = 0
                add_step_notification(update_results, groups_step_name, "完成", "⚠️ 未找到分组信息")
                logger.warning("未获取到分组信息")
            
            # 保存关注列表到数据库（同时进行边同步边分类）
            logger.info(f"开始保存 {len(following_list)} 个用户到数据库")
            success_count = 0
            error_count = 0
            
            for i, user in enumerate(following_list, 1):
                await check_task_control(task_id, step_name)
                
                try:
                    uid = user.get('uid') or user.get('mid')
                    if not uid:
                        error_count += 1
                        continue
                    
                    user['uid'] = uid
                    
                    # 边同步边分类（优化版特色）
                    category = analyzer.classify_user(user)
                    user["category"] = category
                    
                    # 处理分组信息
                    tag_list = user.get('tag', [])
                    if isinstance(tag_list, list) and tag_list:
                        user['group_id'] = tag_list[0]
                    else:
                        user['group_id'] = 0
                    
                    if await db_manager.insert_following_user(user):
                        success_count += 1
                    else:
                        error_count += 1
                    
                    # 每100个用户记录一次进度
                    if i % 100 == 0:
                        logger.info(f"数据库保存进度: {i}/{len(following_list)} ({(i/len(following_list)*100):.1f}%)")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"处理用户数据异常: {e}")
                    continue
            
            update_results["steps"][step_name]["status"] = "completed"
            update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
            update_results["steps"][step_name]["details"] = f"同步完成: {success_count} 个用户"
            update_results["steps"][step_name]["count"] = success_count
            update_results["progress"] = 25
            
            add_step_notification(update_results, step_name, "完成", 
                f"✅ 优化策略节省时间 {step_duration * 0.3:.1f}s，成功同步 {success_count} 个用户")
            
            logger.info(f"优化版关注列表同步完成: 成功 {success_count}, 失败 {error_count}")
            
        except Exception as e:
            update_results["steps"][step_name]["status"] = "failed"
            update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
            update_results["steps"][step_name]["details"] = f"同步失败: {str(e)}"
            add_step_notification(update_results, step_name, "失败", str(e))
            
            # 同时标记分组同步失败
            update_results["steps"][groups_step_name]["status"] = "failed"
            update_results["steps"][groups_step_name]["end_time"] = datetime.now().isoformat()
            update_results["steps"][groups_step_name]["details"] = f"因关注列表同步失败而中断"
            add_step_notification(update_results, groups_step_name, "失败", "因关注列表同步失败而中断")
            
            logger.error(f"优化版关注列表同步失败: {e}")
            raise
        
        # === 步骤2：同步用户统计数据（优化版 - 批量并发）===
        step_name = "sync_user_stats"
        logger.info("步骤2: 开始同步用户统计数据（优化版）")
        
        update_results["steps"][step_name]["status"] = "running"
        update_results["steps"][step_name]["start_time"] = datetime.now().isoformat()
        add_step_notification(update_results, step_name, "开始", "使用批量并发策略和增量更新")
        
        def progress_callback_stats(current, total):
            base_progress = 25
            step_progress = (current / total) * 50 if total > 0 else 0
            update_results["progress"] = base_progress + step_progress
            update_results["steps"][step_name]["details"] = f"已更新 {current}/{total} 个用户统计数据"
            # 添加详细进度日志
            if current % 50 == 0 or current == total:
                logger.info(f"用户统计同步进度: {current}/{total} ({(current/total*100):.1f}%)")
            
        try:
            step_start = time.time()
            
            # 获取需要更新的用户列表
            following_list = await db_manager.get_following_list()
            
            # 使用优化的批量统计获取方法（优化版使用24小时跳过策略）
            skip_hours = 24
            
            stats_results = await api.get_user_stats_batch(
                following_list,
                db_manager=db_manager,
                progress_callback=progress_callback_stats,
                skip_recent_hours=skip_hours
            )
            
            step_duration = time.time() - step_start
            
            # 统计结果
            success_count = sum(1 for success, _ in stats_results if success)
            skipped_count = sum(1 for success, result in stats_results if success and result == "skipped")
            failed_count = len(stats_results) - success_count
            
            update_results["skipped_users"] = skipped_count
            update_results["optimization_stats"]["time_saved"] += skipped_count * 1.5  # 每个跳过的用户节省约1.5秒
            update_results["optimization_stats"]["cache_hits"] = skipped_count
            
            update_results["steps"][step_name]["status"] = "completed"
            update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
            update_results["steps"][step_name]["details"] = f"更新 {success_count - skipped_count} 个，跳过 {skipped_count} 个，失败 {failed_count} 个"
            update_results["steps"][step_name]["count"] = success_count - skipped_count
            update_results["progress"] = 75
            
            add_step_notification(update_results, step_name, "完成", 
                f"🎯 增量更新策略节省时间 {skipped_count * 1.5:.1f}s，智能跳过 {skipped_count} 个最近更新的用户")
            
            logger.info(f"优化版统计数据同步完成: 成功 {success_count}, 跳过 {skipped_count}, 失败 {failed_count}")
            
        except Exception as e:
            update_results["steps"][step_name]["status"] = "failed"
            update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
            update_results["steps"][step_name]["details"] = f"同步失败: {str(e)}"
            add_step_notification(update_results, step_name, "失败", str(e))
            logger.error(f"优化版统计数据同步失败: {e}")
        
        # === 步骤3：快速等级修复 ===
        step_name = "fix_levels"
        logger.info("步骤3: 开始快速等级修复")
        
        update_results["steps"][step_name]["status"] = "running"
        update_results["steps"][step_name]["start_time"] = datetime.now().isoformat()
        add_step_notification(update_results, step_name, "开始", "修复缺失的用户等级信息")
        
        try:
            # 获取需要修复等级的用户（由于前面已经获取了详细信息，这里应该很少）
            cursor = await db_manager._connection.execute(
                "SELECT uid, uname FROM following_list WHERE level = 0 OR level IS NULL"
            )
            users_need_fix = await cursor.fetchall()
            
            if users_need_fix:
                fixed_count = 0
                for i, (uid, uname) in enumerate(users_need_fix):
                    await check_task_control(task_id, step_name)
                    
                    try:
                        user_info = await api.get_user_info(uid)
                        if user_info and user_info.get('card', {}).get('level_info'):
                            level = user_info['card']['level_info'].get('current_level', 0)
                            if level > 0:
                                await db_manager._connection.execute(
                                    "UPDATE following_list SET level = ? WHERE uid = ?",
                                    (level, uid)
                                )
                                fixed_count += 1
                        
                        if (i + 1) % 10 == 0:
                            progress = 75 + ((i + 1) / len(users_need_fix)) * 10
                            update_results["progress"] = progress
                            update_results["steps"][step_name]["details"] = f"已修复 {i + 1}/{len(users_need_fix)} 个用户等级"
                        
                        await asyncio.sleep(0.3)
                        
                    except Exception as e:
                        logger.warning(f"修复用户 {uname} 等级失败: {e}")
                
                await db_manager._connection.commit()
                
                update_results["steps"][step_name]["status"] = "completed"
                update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
                update_results["steps"][step_name]["details"] = f"成功修复 {fixed_count} 个用户的等级信息"
                update_results["steps"][step_name]["count"] = fixed_count
                
                add_step_notification(update_results, step_name, "完成", f"修复了 {fixed_count} 个用户的等级信息")
            else:
                update_results["steps"][step_name]["status"] = "completed"
                update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
                update_results["steps"][step_name]["details"] = "所有用户等级信息完整，无需修复"
                update_results["steps"][step_name]["count"] = 0
                add_step_notification(update_results, step_name, "完成", "所有用户等级信息完整")
            
        except Exception as e:
            update_results["steps"][step_name]["status"] = "failed"
            update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
            update_results["steps"][step_name]["details"] = f"修复失败: {str(e)}"
            add_step_notification(update_results, step_name, "失败", str(e))
            logger.error(f"等级修复失败: {e}")
        
        # === 步骤4：检查分类完整性 ===
        step_name = "auto_categorize"
        logger.info("步骤4: 检查分类完整性")
        
        update_results["steps"][step_name]["status"] = "running"
        update_results["steps"][step_name]["start_time"] = datetime.now().isoformat()
        add_step_notification(update_results, step_name, "开始", "✨ 边同步边分类已在步骤1完成，检查遗漏")
        
        try:
            # 检查是否还有未分类的用户（理论上应该很少，因为已经边同步边分类了）
            cursor = await db_manager._connection.execute(
                """SELECT COUNT(*) FROM following_list 
                   WHERE category IS NULL OR category = '' OR category = '其他'"""
            )
            uncategorized_count = (await cursor.fetchone())[0]
            
            if uncategorized_count > 0:
                # 快速补充分类，使用已导入的analyzer
                
                cursor = await db_manager._connection.execute(
                    """SELECT uid, uname, sign FROM following_list 
                       WHERE category IS NULL OR category = '' OR category = '其他'"""
                )
                uncategorized_users = await cursor.fetchall()
                
                categorized_count = 0
                for uid, uname, sign in uncategorized_users:
                    await check_task_control(task_id, step_name)
                    
                    try:
                        user_data = {"uid": uid, "uname": uname, "sign": sign or ""}
                        category = analyzer.classify_user(user_data)
                        
                        if category and category != "其他":
                            await db_manager._connection.execute(
                                "UPDATE following_list SET category = ? WHERE uid = ?",
                                (category, uid)
                            )
                            categorized_count += 1
                    except Exception as e:
                        logger.warning(f"分类用户 {uname} 失败: {e}")
                
                await db_manager._connection.commit()
                
                update_results["steps"][step_name]["status"] = "completed"
                update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
                update_results["steps"][step_name]["details"] = f"成功分类 {categorized_count} 个用户"
                update_results["steps"][step_name]["count"] = categorized_count
                
                add_step_notification(update_results, step_name, "完成", f"补充分类了 {categorized_count} 个用户")
            else:
                update_results["steps"][step_name]["status"] = "completed"
                update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
                update_results["steps"][step_name]["details"] = "所有用户已完成分类"
                update_results["steps"][step_name]["count"] = 0
                add_step_notification(update_results, step_name, "完成", "所有用户已完成分类")
                logger.info("补充分类完成: 无需分类")
            
        except Exception as e:
            update_results["steps"][step_name]["status"] = "failed"
            update_results["steps"][step_name]["end_time"] = datetime.now().isoformat()
            update_results["steps"][step_name]["details"] = f"分类失败: {str(e)}"
            add_step_notification(update_results, step_name, "失败", str(e))
            logger.error(f"自动分类失败: {e}")
        
        # 完成所有步骤
        total_duration = time.time() - start_time
        update_results["progress"] = 100
        update_results["status"] = "completed"
        update_results["end_time"] = datetime.now().isoformat()
        update_results["total_duration"] = total_duration
        
        # 计算优化效果
        time_saved = update_results["optimization_stats"]["time_saved"]
        traditional_time = total_duration + time_saved
        efficiency_gain = (time_saved / traditional_time) * 100 if traditional_time > 0 else 0
        
        add_step_notification(update_results, "summary", "完成", 
            f"🚀 优化版一键更新完成！耗时 {total_duration:.1f}s，比传统方式节省约 {time_saved:.1f}s（提升 {efficiency_gain:.1f}%）")
        
        logger.info(f"优化版一键更新任务 {task_id} 完成，耗时: {total_duration:.1f}s，优化节省: {time_saved:.1f}s")
        
    except Exception as e:
        update_results["status"] = "failed"
        update_results["error"] = str(e)
        update_results["end_time"] = datetime.now().isoformat()
        add_step_notification(update_results, "error", "失败", f"任务执行失败: {str(e)}")
        logger.error(f"优化版一键更新任务 {task_id} 失败: {e}")
    
    finally:
        try:
            await api.close()
        except Exception:
            pass

@router.get("/one-click-update-optimized/{task_id}")
async def get_one_click_update_optimized_progress(task_id: str, req: Request):
    """获取优化版一键更新任务的进度"""
    try:
        db_manager = req.app.state.db_manager
        
        # 初始化缓存（如果不存在）
        if not hasattr(db_manager, '_update_cache'):
            db_manager._update_cache = {}
        
        # 清理过期任务（超过4小时的任务）
        current_time = time.time()
        expired_tasks = []
        for cached_task_id, task_data in db_manager._update_cache.items():
            try:
                start_time_str = task_data.get("start_time", "")
                if start_time_str:
                    # 解析开始时间
                    if isinstance(start_time_str, str):
                        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                        start_timestamp = start_time.timestamp()
                    else:
                        start_timestamp = start_time_str
                    
                    # 检查是否超过4小时
                    if current_time - start_timestamp > 4 * 3600:
                        expired_tasks.append(cached_task_id)
            except Exception as e:
                logger.warning(f"解析任务 {cached_task_id} 时间失败: {e}")
                # 如果解析失败，也认为是过期任务
                expired_tasks.append(cached_task_id)
        
        # 删除过期任务
        for expired_task_id in expired_tasks:
            del db_manager._update_cache[expired_task_id]
            logger.info(f"清理过期任务: {expired_task_id}")
        
        # 检查任务是否存在
        if task_id not in db_manager._update_cache:
            # 提供更详细的404错误信息
            available_tasks = list(db_manager._update_cache.keys())
            logger.warning(f"任务 {task_id} 不存在，当前可用任务: {available_tasks}")
            
            error_detail = {
                "error": "任务不存在或已过期",
                "task_id": task_id,
                "available_tasks": available_tasks[-3:] if available_tasks else [],  # 返回最近3个任务
                "message": "任务可能已完成、过期或服务已重启。请刷新页面并重新启动任务。"
            }
            raise HTTPException(status_code=404, detail=error_detail)
        
        update_results = db_manager._update_cache[task_id]
        
        # 获取步骤信息并确保安全访问
        steps = update_results.get("steps", {})
        
        def get_step_info(step_name):
            step_data = steps.get(step_name, {})
            return {
                "status": step_data.get("status", "pending"),
                "details": step_data.get("details", ""),
                "logs": step_data.get("logs", [])[-10:]
            }
        
        # 安全格式化时间字段
        def format_time(time_field):
            if not time_field:
                return ""
            if isinstance(time_field, str):
                return time_field
            try:
                return time_field.isoformat()
            except AttributeError:
                return str(time_field)
        
        # 返回优化版特有的进度信息
        return {
            "task_id": task_id,
            "mode": "optimized",
            "overall": {
                "status": update_results.get("status", "unknown"),
                "progress": update_results.get("progress", 0),
                "start_time": format_time(update_results.get("start_time")),
                "end_time": format_time(update_results.get("end_time")),
                "total_users": update_results.get("total_users", 0),
                "processed_users": update_results.get("processed_users", 0),
                "failed_users": update_results.get("failed_users", 0),
                "skipped_users": update_results.get("skipped_users", 0)
            },
            "optimization_stats": update_results.get("optimization_stats", {}),
            "steps": {
                "sync_following": get_step_info("sync_following"),
                "groups_sync": get_step_info("groups_sync"),
                "sync_user_stats": get_step_info("sync_user_stats"), 
                "fix_levels": get_step_info("fix_levels"),
                "auto_categorize": get_step_info("auto_categorize")
            },
            "summary": update_results.get("summary", {}),
            "start_time": format_time(update_results.get("start_time")),
            "end_time": format_time(update_results.get("end_time")),
            "total_duration": update_results.get("total_duration"),
            "notifications": update_results.get("notifications", [])[-5:]  # 最近5个通知
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取优化版任务进度失败: {e}")
        raise HTTPException(status_code=500, detail="获取任务进度失败")

@router.get("/active-tasks")
async def get_active_tasks(req: Request):
    """获取当前活跃的任务列表"""
    try:
        db_manager = req.app.state.db_manager
        
        active_tasks = {
            "update_tasks": [],
            "sync_tasks": []
        }
        
        # 检查一键更新任务
        if hasattr(db_manager, '_update_cache'):
            for task_id, task_data in db_manager._update_cache.items():
                status = task_data.get("status", "unknown")
                start_time = task_data.get("start_time", "")
                mode = task_data.get("mode", "unknown")
                progress = task_data.get("progress", 0)
                
                active_tasks["update_tasks"].append({
                    "task_id": task_id,
                    "status": status,
                    "mode": mode,
                    "progress": progress,
                    "start_time": start_time,
                    "is_optimized": task_data.get("optimization_enabled", False)
                })
        
        # 检查同步任务
        if hasattr(db_manager, '_sync_progress_cache'):
            for task_id, task_data in db_manager._sync_progress_cache.items():
                status = task_data.get("status", "unknown")
                start_time = task_data.get("start_time", "")
                progress = task_data.get("progress", 0)
                
                if isinstance(start_time, datetime):
                    start_time = start_time.isoformat()
                
                active_tasks["sync_tasks"].append({
                    "task_id": task_id,
                    "status": status,
                    "progress": progress,
                    "start_time": start_time
                })
        
        return {
            "active_tasks": active_tasks,
            "total_active": len(active_tasks["update_tasks"]) + len(active_tasks["sync_tasks"]),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取活跃任务列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取活跃任务列表失败")

def add_step_notification(update_results: dict, step_name: str, action: str, details: str = ""):
    """添加步骤通知（开始/完成/失败）"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # 确保步骤存在logs字段
    if step_name not in update_results.get("steps", {}):
        return
    
    if "logs" not in update_results["steps"][step_name]:
        update_results["steps"][step_name]["logs"] = []
    
    if action == "开始":
        message = f"🚀 [{timestamp}] 开始执行"
        if details:
            message += f": {details}"
        update_results["steps"][step_name]["logs"].append(message)
        logger.info(f"步骤开始: {step_name} - {details}")
    elif action == "完成":
        message = f"✅ [{timestamp}] 执行完成"
        if details:
            message += f": {details}"
        update_results["steps"][step_name]["logs"].append(message)
        logger.info(f"步骤完成: {step_name} - {details}")
    elif action == "失败":
        message = f"❌ [{timestamp}] 执行失败"
        if details:
            message += f": {details}"
        update_results["steps"][step_name]["logs"].append(message)
        logger.error(f"步骤失败: {step_name} - {details}")
    elif action == "暂停":
        message = f"⏸️ [{timestamp}] 已暂停"
        if details:
            message += f": {details}"
        update_results["steps"][step_name]["logs"].append(message)
        logger.info(f"步骤暂停: {step_name} - {details}")
    elif action == "继续":
        message = f"▶️ [{timestamp}] 已继续"
        if details:
            message += f": {details}"
        update_results["steps"][step_name]["logs"].append(message)
        logger.info(f"步骤继续: {step_name} - {details}")
    
    # 同时添加到全局通知列表
    if "notifications" not in update_results:
        update_results["notifications"] = []
    
    update_results["notifications"].append({
        "timestamp": timestamp,
        "step": step_name,
        "action": action,
        "message": message
    })