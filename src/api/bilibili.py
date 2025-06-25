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


class GroupUpdateRequest(BaseModel):
    """分组更新请求模型"""
    uid: int
    group_id: int


class BatchGroupUpdateRequest(BaseModel):
    """批量分组更新请求模型"""
    uids: List[int]
    group_id: int


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
async def one_click_update_all(background_tasks: BackgroundTasks, req: Request):
    """一键更新所有信息：关注列表、分组信息、用户统计、等级信息等"""
    try:
        api = await get_bilibili_api()
        
        if not api.is_configured():
            raise HTTPException(status_code=400, detail="未配置哔哩哔哩Cookie")
        
        # 创建一个唯一的任务ID
        import time
        task_id = f"update_{int(time.time())}"
        
        # 在后台执行一键更新任务
        background_tasks.add_task(_one_click_update_task, req.app.state.db_manager, task_id)
        
        return {"message": "一键更新任务已启动", "status": "started", "task_id": task_id}
        
    except Exception as e:
        logger.error(f"启动一键更新任务失败: {e}")
        raise HTTPException(status_code=500, detail="启动一键更新任务失败")


async def _one_click_update_task(db_manager, task_id):
    """一键更新的后台任务"""
    try:
        api = await get_bilibili_api()
        
        # 创建更详细的结果记录
        update_results = {
            "task_id": task_id,
            "start_time": datetime.now(),
            "following_sync": {"status": "pending", "details": {}, "logs": []},
            "groups_sync": {"status": "pending", "details": {}, "logs": []},
            "user_stats": {"status": "pending", "details": {}, "logs": []},
            "level_fix": {"status": "pending", "details": {}, "logs": []},
            "auto_categorize": {"status": "pending", "details": {}, "logs": []},
            "overall": {"status": "running", "progress": 0}
        }
        
        # 将结果存储到应用状态中，供前端查询
        if not hasattr(db_manager, '_update_cache'):
            db_manager._update_cache = {}
        db_manager._update_cache[task_id] = update_results
        
        logger.info(f"开始执行一键更新任务 {task_id}...")
        
        # 1. 同步关注列表和分组信息
        logger.info("步骤 1/5: 同步关注列表和分组信息...")
        update_results["overall"]["progress"] = 10
        try:
            record_id = await db_manager.insert_sync_record("one_click_following_sync")
            update_results["following_sync"]["logs"].append("开始同步关注列表...")
            
            # 获取分组信息
            update_results["groups_sync"]["logs"].append("开始获取分组信息...")
            bilibili_groups = await api.get_follow_groups()
            if bilibili_groups:
                for group in bilibili_groups:
                    group_id = group.get('tagid', 0)
                    group_name = group.get('name', '未知分组')
                    group_count = group.get('count', 0)
                    
                    if group_id > 0:
                        await db_manager.insert_or_update_follow_group(
                            group_id, group_name, group_count
                        )
                logger.info(f"分组信息同步完成，共 {len(bilibili_groups)} 个分组")
                update_results["groups_sync"]["status"] = "completed"
                update_results["groups_sync"]["details"] = {"groups_count": len(bilibili_groups)}
                update_results["groups_sync"]["logs"].append(f"成功同步 {len(bilibili_groups)} 个分组")
            
            # 获取所有关注列表（不限制数量）
            def progress_callback(current, total):
                progress_msg = f"同步关注列表进度: {current}/{total}"
                logger.info(progress_msg)
                update_results["following_sync"]["logs"].append(progress_msg)
                # 更新总体进度 (10% - 40%)
                if total > 0:
                    sync_progress = min((current / total) * 30, 30)
                    update_results["overall"]["progress"] = 10 + sync_progress
            
            update_results["following_sync"]["logs"].append("开始获取所有关注用户...")
            following_list = await api.get_all_following(progress_callback)
            
            success_count = 0
            error_count = 0
            
            update_results["following_sync"]["logs"].append(f"开始处理 {len(following_list)} 个用户的数据...")
            
            for i, user in enumerate(following_list):
                try:
                    uid = user.get('uid') or user.get('mid')
                    if not uid:
                        error_count += 1
                        update_results["following_sync"]["logs"].append(f"用户 {i+1} 缺少UID，跳过")
                        continue
                    
                    user['uid'] = uid
                    
                    # 分类
                    from ..bilibili.analyzer import FollowingAnalyzer
                    analyzer = FollowingAnalyzer()
                    category = analyzer.classify_user(user)
                    user["category"] = category
                    
                    # 分组信息
                    tag_list = user.get('tag', [])
                    if isinstance(tag_list, list) and tag_list:
                        user['group_id'] = tag_list[0]
                    else:
                        user['group_id'] = 0
                    
                    if await db_manager.insert_following_user(user):
                        success_count += 1
                    else:
                        error_count += 1
                        update_results["following_sync"]["logs"].append(f"用户 {user.get('uname', uid)} 保存失败")
                    
                    # 每处理100个用户更新一次进度日志
                    if (i + 1) % 100 == 0:
                        progress_msg = f"已处理 {i+1}/{len(following_list)} 个用户，成功 {success_count}，失败 {error_count}"
                        update_results["following_sync"]["logs"].append(progress_msg)
                        
                except Exception as e:
                    error_count += 1
                    error_msg = f"处理用户数据异常: {e}"
                    logger.error(error_msg)
                    update_results["following_sync"]["logs"].append(error_msg)
            
            await db_manager.update_sync_record(record_id, success_count, error_count, "completed")
            update_results["following_sync"]["status"] = "completed"
            update_results["following_sync"]["details"] = {
                "total": len(following_list),
                "success": success_count,
                "error": error_count
            }
            
            final_msg = f"关注列表同步完成: 获取 {len(following_list)} 个用户, 成功 {success_count}, 失败 {error_count}"
            logger.info(final_msg)
            update_results["following_sync"]["logs"].append(final_msg)
            update_results["overall"]["progress"] = 40
            
        except Exception as e:
            logger.error(f"同步关注列表失败: {e}")
            update_results["following_sync"]["status"] = "failed"
            update_results["following_sync"]["details"] = {"error": str(e)}
        
        # 2. 同步用户统计数据（全部用户）
        logger.info("步骤 2/5: 同步用户统计数据（全部用户）...")
        update_results["overall"]["progress"] = 45
        try:
            following_list = await db_manager.get_following_list()
            users_to_process = following_list  # 处理全部用户
            
            update_results["user_stats"]["logs"].append(f"开始同步 {len(users_to_process)} 个用户的统计数据...")
            
            updated_count = 0
            error_count = 0
            consecutive_failures = 0
            max_consecutive_failures = 10  # 增加容忍度
            
            for i, user in enumerate(users_to_process):
                try:
                    uid = user["uid"]
                    uname = user.get('uname', str(uid))
                    
                    if consecutive_failures >= max_consecutive_failures:
                        warning_msg = f"检测到连续 {consecutive_failures} 次失败，可能遇到API限制，暂停10秒后继续..."
                        logger.warning(warning_msg)
                        update_results["user_stats"]["logs"].append(warning_msg)
                        await asyncio.sleep(10)  # 暂停10秒
                        consecutive_failures = 0  # 重置计数器
                    
                    real_stats = await api.get_user_stats(uid)
                    
                    if real_stats:
                        cursor = await db_manager._connection.execute(
                            "SELECT uid FROM user_stats WHERE uid = ?", (uid,)
                        )
                        existing = await cursor.fetchone()
                        
                        if existing:
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
                        consecutive_failures = 0
                        
                        # 增加延迟时间以避免封号（3-5秒随机延迟）
                        import random
                        delay = random.uniform(3.0, 5.0)
                        await asyncio.sleep(delay)
                        
                    else:
                        error_count += 1
                        consecutive_failures += 1
                        error_msg = f"用户 {uname} 统计数据获取失败"
                        update_results["user_stats"]["logs"].append(error_msg)
                    
                    # 每处理10个用户更新一次进度
                    if (i + 1) % 10 == 0:
                        progress_msg = f"统计数据同步进度: {i+1}/{len(users_to_process)}, 成功: {updated_count}, 失败: {error_count}"
                        logger.info(progress_msg)
                        update_results["user_stats"]["logs"].append(progress_msg)
                        
                        # 更新总体进度 (45% - 75%)
                        stats_progress = min((i / len(users_to_process)) * 30, 30)
                        update_results["overall"]["progress"] = 45 + stats_progress
                        
                except Exception as e:
                    error_count += 1
                    consecutive_failures += 1
                    error_msg = f"同步用户 {user.get('uname', uid)} 统计数据失败: {e}"
                    logger.error(error_msg)
                    update_results["user_stats"]["logs"].append(error_msg)
            
            await db_manager._connection.commit()
            update_results["user_stats"]["status"] = "completed"
            update_results["user_stats"]["details"] = {
                "processed": len(users_to_process),
                "updated": updated_count,
                "error": error_count
            }
            
            final_msg = f"用户统计数据同步完成: 处理 {len(users_to_process)} 个用户, 成功 {updated_count} 个, 失败 {error_count} 个"
            logger.info(final_msg)
            update_results["user_stats"]["logs"].append(final_msg)
            update_results["overall"]["progress"] = 75
            
        except Exception as e:
            logger.error(f"同步用户统计数据失败: {e}")
            update_results["user_stats"]["status"] = "failed"
            update_results["user_stats"]["details"] = {"error": str(e)}
        
        # 3. 修复等级信息（全部需要修复的用户）
        logger.info("步骤 3/5: 修复用户等级信息...")
        update_results["overall"]["progress"] = 80
        try:
            users_to_fix = await db_manager.get_users_with_zero_level()  # 获取所有需要修复的用户
            
            update_results["level_fix"]["logs"].append(f"发现 {len(users_to_fix)} 个用户需要修复等级信息...")
            
            fixed_count = 0
            error_count = 0
            consecutive_failures = 0
            max_consecutive_failures = 8  # 适当增加容忍度
            
            for i, user in enumerate(users_to_fix):
                try:
                    uid = user.get('uid')
                    uname = user.get('uname', 'Unknown')
                    if not uid:
                        continue
                    
                    if consecutive_failures >= max_consecutive_failures:
                        warning_msg = f"检测到连续 {consecutive_failures} 次失败，可能遇到API限制，暂停8秒后继续..."
                        logger.warning(warning_msg)
                        update_results["level_fix"]["logs"].append(warning_msg)
                        await asyncio.sleep(8)  # 暂停8秒
                        consecutive_failures = 0  # 重置计数器
                    
                    user_detail = await api.get_user_info(uid)
                    if user_detail and user_detail.get('card'):
                        card_info = user_detail['card']
                        
                        if 'level_info' in card_info:
                            new_level = card_info['level_info'].get('current_level', 0)
                            
                            if new_level > 0:
                                await db_manager._connection.execute(
                                    "UPDATE following_list SET level = ? WHERE uid = ?",
                                    (new_level, uid)
                                )
                                await db_manager._connection.commit()
                                fixed_count += 1
                                consecutive_failures = 0
                                
                                success_msg = f"成功修复用户 {uname} 等级: {new_level}"
                                update_results["level_fix"]["logs"].append(success_msg)
                                
                                # 增加延迟时间以避免封号（2-4秒随机延迟）
                                import random
                                delay = random.uniform(2.0, 4.0)
                                await asyncio.sleep(delay)
                        else:
                            consecutive_failures += 1
                            error_msg = f"用户 {uname} 等级信息不可用"
                            update_results["level_fix"]["logs"].append(error_msg)
                    else:
                        consecutive_failures += 1
                        error_count += 1
                        error_msg = f"获取用户 {uname} 详细信息失败"
                        update_results["level_fix"]["logs"].append(error_msg)
                    
                    # 每处理5个用户更新一次进度
                    if (i + 1) % 5 == 0:
                        progress_msg = f"等级修复进度: {i+1}/{len(users_to_fix)}, 成功: {fixed_count}, 失败: {error_count}"
                        logger.info(progress_msg)
                        update_results["level_fix"]["logs"].append(progress_msg)
                        
                except Exception as e:
                    error_count += 1
                    consecutive_failures += 1
                    error_msg = f"修复用户 {user.get('uname', 'Unknown')} 等级信息失败: {e}"
                    logger.error(error_msg)
                    update_results["level_fix"]["logs"].append(error_msg)
            
            update_results["level_fix"]["status"] = "completed"
            update_results["level_fix"]["details"] = {
                "processed": len(users_to_fix),
                "fixed": fixed_count,
                "error": error_count
            }
            
            final_msg = f"等级信息修复完成: 处理 {len(users_to_fix)} 个用户, 成功修复 {fixed_count} 个, 失败 {error_count} 个"
            logger.info(final_msg)
            update_results["level_fix"]["logs"].append(final_msg)
            update_results["overall"]["progress"] = 90
            
        except Exception as e:
            logger.error(f"修复等级信息失败: {e}")
            update_results["level_fix"]["status"] = "failed"
            update_results["level_fix"]["details"] = {"error": str(e)}
        
        # 4. 自动分类（轻量级操作）
        logger.info("步骤 4/5: 执行自动分类...")
        update_results["overall"]["progress"] = 95
        try:
            from ..bilibili.analyzer import FollowingAnalyzer
            analyzer = FollowingAnalyzer()
            
            users = await db_manager.get_following_list()
            updated_count = 0
            error_count = 0
            
            # 筛选需要分类的用户
            users_to_categorize = [user for user in users if user.get('category', 'unknown') in ['unknown', '']]
            update_results["auto_categorize"]["logs"].append(f"发现 {len(users_to_categorize)} 个用户需要重新分类...")
            
            for i, user in enumerate(users_to_categorize):
                try:
                    uid = user.get('uid')
                    uname = user.get('uname', 'Unknown')
                    current_category = user.get('category', 'unknown')
                    
                    new_category = analyzer.classify_user(user)
                    if new_category != current_category:
                        await db_manager.update_user_category(uid, new_category)
                        updated_count += 1
                        
                        success_msg = f"用户 {uname} 分类更新: {current_category} -> {new_category}"
                        update_results["auto_categorize"]["logs"].append(success_msg)
                    
                    # 每处理50个用户更新一次进度
                    if (i + 1) % 50 == 0:
                        progress_msg = f"自动分类进度: {i+1}/{len(users_to_categorize)}, 已更新: {updated_count}"
                        update_results["auto_categorize"]["logs"].append(progress_msg)
                            
                except Exception as e:
                    error_count += 1
                    error_msg = f"自动分类用户 {user.get('uname', 'Unknown')} 失败: {e}"
                    logger.error(error_msg)
                    update_results["auto_categorize"]["logs"].append(error_msg)
            
            update_results["auto_categorize"]["status"] = "completed"
            update_results["auto_categorize"]["details"] = {
                "checked": len(users_to_categorize),
                "updated": updated_count,
                "error": error_count
            }
            
            final_msg = f"自动分类完成: 检查 {len(users_to_categorize)} 个用户, 更新 {updated_count} 个用户的分类, 失败 {error_count} 个"
            logger.info(final_msg)
            update_results["auto_categorize"]["logs"].append(final_msg)
            update_results["overall"]["progress"] = 100
            
        except Exception as e:
            logger.error(f"自动分类失败: {e}")
            update_results["auto_categorize"]["status"] = "failed"
            update_results["auto_categorize"]["details"] = {"error": str(e)}
        
        # 5. 记录更新结果
        logger.info("步骤 5/5: 更新任务完成")
        update_results["overall"]["status"] = "completed"
        update_results["overall"]["progress"] = 100
        update_results["end_time"] = datetime.now()
        
        # 统计总体结果
        task_keys = ["following_sync", "groups_sync", "user_stats", "level_fix", "auto_categorize"]
        completed_tasks = sum(1 for key in task_keys if update_results[key]["status"] == "completed")
        failed_tasks = sum(1 for key in task_keys if update_results[key]["status"] == "failed")
        
        # 创建总结日志
        duration = update_results["end_time"] - update_results["start_time"]
        duration_str = str(duration).split('.')[0]  # 去掉微秒
        
        summary_log = f"一键更新任务完成! 耗时: {duration_str}, 成功: {completed_tasks}/{len(task_keys)} 个任务, 失败: {failed_tasks} 个任务"
        logger.info(summary_log)
        
        # 汇总各步骤的详细结果
        summary_details = []
        if update_results["following_sync"]["status"] == "completed":
            details = update_results["following_sync"]["details"]
            summary_details.append(f"关注列表同步: {details.get('success', 0)}/{details.get('total', 0)} 成功")
        
        if update_results["groups_sync"]["status"] == "completed":
            details = update_results["groups_sync"]["details"]
            summary_details.append(f"分组同步: {details.get('groups_count', 0)} 个分组")
        
        if update_results["user_stats"]["status"] == "completed":
            details = update_results["user_stats"]["details"]
            summary_details.append(f"统计数据同步: {details.get('updated', 0)}/{details.get('processed', 0)} 成功")
        
        if update_results["level_fix"]["status"] == "completed":
            details = update_results["level_fix"]["details"]
            summary_details.append(f"等级修复: {details.get('fixed', 0)}/{details.get('processed', 0)} 成功")
        
        if update_results["auto_categorize"]["status"] == "completed":
            details = update_results["auto_categorize"]["details"]
            summary_details.append(f"自动分类: {details.get('updated', 0)}/{details.get('checked', 0)} 成功")
        
        summary_detail_str = " | ".join(summary_details)
        logger.info(f"详细结果: {summary_detail_str}")
        
        # 将任务完成时间和状态更新到缓存
        update_results["summary"] = {
            "duration": duration_str,
            "completed_tasks": completed_tasks,
            "total_tasks": len(task_keys),
            "failed_tasks": failed_tasks,
            "details": summary_detail_str
        }
        
    except Exception as e:
        logger.error(f"一键更新任务执行失败: {e}")
        update_results["overall"]["status"] = "failed"
        update_results["overall"]["error"] = str(e)
        update_results["end_time"] = datetime.now()
        
        # 即使任务失败，也要保留已执行的部分结果
        if "start_time" in update_results:
            duration = update_results["end_time"] - update_results["start_time"]
            duration_str = str(duration).split('.')[0]
            update_results["summary"] = {
                "duration": duration_str,
                "status": "failed",
                "error": str(e)
            }


@router.get("/one-click-update/{task_id}")
async def get_one_click_update_progress(task_id: str, req: Request):
    """获取一键更新任务的进度"""
    try:
        db_manager = req.app.state.db_manager
        
        if not hasattr(db_manager, '_update_cache') or task_id not in db_manager._update_cache:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        
        update_results = db_manager._update_cache[task_id]
        
        # 返回进度信息
        return {
            "task_id": task_id,
            "overall": update_results.get("overall", {}),
            "steps": {
                "following_sync": {
                    "status": update_results["following_sync"]["status"],
                    "details": update_results["following_sync"]["details"],
                    "logs": update_results["following_sync"]["logs"][-10:]  # 最近10条日志
                },
                "groups_sync": {
                    "status": update_results["groups_sync"]["status"],
                    "details": update_results["groups_sync"]["details"],
                    "logs": update_results["groups_sync"]["logs"][-5:]  # 最近5条日志
                },
                "user_stats": {
                    "status": update_results["user_stats"]["status"],
                    "details": update_results["user_stats"]["details"],
                    "logs": update_results["user_stats"]["logs"][-10:]  # 最近10条日志
                },
                "level_fix": {
                    "status": update_results["level_fix"]["status"],
                    "details": update_results["level_fix"]["details"],
                    "logs": update_results["level_fix"]["logs"][-10:]  # 最近10条日志
                },
                "auto_categorize": {
                    "status": update_results["auto_categorize"]["status"],
                    "details": update_results["auto_categorize"]["details"],
                    "logs": update_results["auto_categorize"]["logs"][-5:]  # 最近5条日志
                }
            },
            "summary": update_results.get("summary", {}),
            "start_time": update_results.get("start_time", "").isoformat() if update_results.get("start_time") else "",
            "end_time": update_results.get("end_time", "").isoformat() if update_results.get("end_time") else ""
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务进度失败: {e}")
        raise HTTPException(status_code=500, detail="获取任务进度失败")


@router.get("/one-click-update/{task_id}/logs")
async def get_one_click_update_logs(task_id: str, req: Request, step: str = None):
    """获取一键更新任务的详细日志"""
    try:
        db_manager = req.app.state.db_manager
        
        if not hasattr(db_manager, '_update_cache') or task_id not in db_manager._update_cache:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        
        update_results = db_manager._update_cache[task_id]
        
        if step:
            # 获取特定步骤的日志
            if step not in update_results:
                raise HTTPException(status_code=404, detail="步骤不存在")
            
            return {
                "task_id": task_id,
                "step": step,
                "logs": update_results[step].get("logs", []),
                "status": update_results[step].get("status", "pending"),
                "details": update_results[step].get("details", {})
            }
        else:
            # 获取所有步骤的日志
            all_logs = []
            steps = ["following_sync", "groups_sync", "user_stats", "level_fix", "auto_categorize"]
            
            for step_name in steps:
                step_data = update_results.get(step_name, {})
                step_logs = step_data.get("logs", [])
                for log in step_logs:
                    all_logs.append({
                        "step": step_name,
                        "message": log,
                        "status": step_data.get("status", "pending")
                    })
            
            return {
                "task_id": task_id,
                "all_logs": all_logs,
                "summary": update_results.get("summary", {}),
                "overall": update_results.get("overall", {})
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务日志失败: {e}")
        raise HTTPException(status_code=500, detail="获取任务日志失败") 

# 在文件末尾添加保守同步相关的接口

@router.post("/sync-user-stats-conservative")
async def sync_user_stats_conservative(req: Request, background_tasks: BackgroundTasks, 
                                     start_pos: int = 0, count: Optional[int] = None):
    """保守模式同步用户统计数据"""
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        if not api.is_configured():
            raise HTTPException(status_code=400, detail="请先配置哔哩哔哩Cookie")
        
        # 创建任务ID
        import time
        task_id = f"conservative_sync_{int(time.time())}"
        
        # 初始化进度跟踪缓存
        if not hasattr(db_manager, '_sync_progress_cache'):
            db_manager._sync_progress_cache = {}
        
        # 获取关注列表
        following_list = await db_manager.get_following_list()
        
        # 确定处理范围
        end_pos = min(start_pos + count, len(following_list)) if count else len(following_list)
        users_to_process = following_list[start_pos:end_pos]
        
        logger.info(f"开始保守模式同步：处理位置 {start_pos+1}-{end_pos} 的 {len(users_to_process)} 个用户")
        
        # 初始化进度信息
        progress_info = {
            "task_id": task_id,
            "mode": "conservative",
            "status": "running",
            "progress": 0,
            "total_users": len(users_to_process),
            "processed_users": 0,
            "successful_users": 0,
            "failed_users": 0,
            "skipped_users": 0,
            "wind_control_hits": 0,
            "current_user": "",
            "start_time": datetime.now(),
            "end_time": None,
            "message": "开始保守模式同步...",
            "failed_user_list": [],  # 记录失败的用户
            "skipped_user_list": []  # 记录跳过的用户
        }
        db_manager._sync_progress_cache[task_id] = progress_info
        
        # 在后台执行保守同步任务
        background_tasks.add_task(_conservative_sync_task, db_manager, task_id, users_to_process, start_pos)
        
        return {
            "message": "保守模式同步任务已启动",
            "task_id": task_id,
            "mode": "conservative",
            "total_users": len(users_to_process),
            "start_position": start_pos + 1,
            "status": "started"
        }
        
    except Exception as e:
        logger.error(f"启动保守模式同步任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动保守同步失败: {str(e)}")


@router.post("/sync-user-stats-ultra-conservative")
async def sync_user_stats_ultra_conservative(req: Request, background_tasks: BackgroundTasks,
                                           start_pos: int = 0, count: Optional[int] = None):
    """超级保守模式同步用户统计数据"""
    try:
        db_manager = req.app.state.db_manager
        api = await get_bilibili_api()
        
        if not api.is_configured():
            raise HTTPException(status_code=400, detail="请先配置哔哩哔哩Cookie")
        
        # 创建任务ID
        import time
        task_id = f"ultra_conservative_sync_{int(time.time())}"
        
        # 初始化进度跟踪缓存
        if not hasattr(db_manager, '_sync_progress_cache'):
            db_manager._sync_progress_cache = {}
        
        # 获取关注列表
        following_list = await db_manager.get_following_list()
        
        # 确定处理范围
        end_pos = min(start_pos + count, len(following_list)) if count else len(following_list)
        users_to_process = following_list[start_pos:end_pos]
        
        logger.info(f"开始超级保守模式同步：处理位置 {start_pos+1}-{end_pos} 的 {len(users_to_process)} 个用户")
        
        # 初始化进度信息
        progress_info = {
            "task_id": task_id,
            "mode": "ultra_conservative",
            "status": "running",
            "progress": 0,
            "total_users": len(users_to_process),
            "processed_users": 0,
            "successful_users": 0,
            "failed_users": 0,
            "skipped_users": 0,
            "api_warnings": 0,
            "current_user": "",
            "start_time": datetime.now(),
            "end_time": None,
            "message": "开始超级保守模式同步...",
            "failed_user_list": [],  # 记录失败的用户
            "skipped_user_list": []  # 记录跳过的用户
        }
        db_manager._sync_progress_cache[task_id] = progress_info
        
        # 在后台执行超级保守同步任务
        background_tasks.add_task(_ultra_conservative_sync_task, db_manager, task_id, users_to_process, start_pos)
        
        return {
            "message": "超级保守模式同步任务已启动",
            "task_id": task_id,
            "mode": "ultra_conservative",
            "total_users": len(users_to_process),
            "start_position": start_pos + 1,
            "estimated_time_hours": len(users_to_process) * 47 / 3600,  # 基于测试的47秒/用户
            "status": "started"
        }
        
    except Exception as e:
        logger.error(f"启动超级保守模式同步任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动超级保守同步失败: {str(e)}")


async def _conservative_sync_task(db_manager, task_id: str, users_to_process: list, start_pos: int):
    """保守同步的后台任务"""
    api = None
    try:
        api = await get_bilibili_api()
        
        # 保守同步配置
        conservative_config = {
            'base_delay': 3.0,
            'min_delay': 2.0,
            'max_delay': 15.0,
            'api_call_delay': 0.5,
            'max_failures': 10,
            'batch_rest_interval': 60,  # 每5个用户休息1分钟
            'batch_size': 5
        }
        
        successful_users = 0
        failed_users = 0
        skipped_users = 0
        wind_control_hits = 0
        
        for i, user in enumerate(users_to_process):
            try:
                # 检查任务是否被取消
                if task_id not in db_manager._sync_progress_cache:
                    break
                
                uid = user.get('uid') or user.get('mid')
                uname = user.get('uname', f'User_{uid}')
                
                if not uid:
                    skipped_users += 1
                    continue
                
                # 更新当前处理状态
                if task_id in db_manager._sync_progress_cache:
                    db_manager._sync_progress_cache[task_id]["current_user"] = uname
                    db_manager._sync_progress_cache[task_id]["message"] = f"保守模式处理用户 {uname} ({i+1}/{len(users_to_process)})"
                
                # 检查是否需要跳过（最近1小时内已更新）
                if await _should_skip_user_conservative(db_manager, uid):
                    skipped_users += 1
                    logger.info(f"⏭️ 用户 {uname} 数据较新，跳过")
                    
                    # 记录跳过的用户
                    if task_id in db_manager._sync_progress_cache:
                        db_manager._sync_progress_cache[task_id]["skipped_user_list"].append({
                            "uid": uid,
                            "uname": uname,
                            "reason": "数据较新（1小时内已更新）"
                        })
                else:
                    # API调用前延迟
                    await asyncio.sleep(conservative_config['api_call_delay'])
                    
                    # 获取用户统计信息
                    logger.info(f"🔄 保守模式处理用户 {uname}")
                    user_stats = await api.get_user_stats(uid)
                    
                    if user_stats:
                        await _update_user_stats_to_db(db_manager, uid, user, user_stats)
                        successful_users += 1
                        logger.info(f"✅ 用户 {uname} 处理成功")
                    else:
                        failed_users += 1
                        logger.warning(f"❌ 用户 {uname} 处理失败")
                        
                        # 记录失败的用户
                        if task_id in db_manager._sync_progress_cache:
                            db_manager._sync_progress_cache[task_id]["failed_user_list"].append({
                                "uid": uid,
                                "uname": uname,
                                "reason": "API调用失败或返回数据为空"
                            })
                
                # 批次休息
                if (i + 1) % conservative_config['batch_size'] == 0:
                    rest_time = conservative_config['batch_rest_interval']
                    logger.info(f"😴 批次休息 {rest_time} 秒...")
                    await asyncio.sleep(rest_time)
                
                # 更新进度
                if task_id in db_manager._sync_progress_cache:
                    progress = ((i + 1) / len(users_to_process)) * 100
                    db_manager._sync_progress_cache[task_id].update({
                        "processed_users": i + 1,
                        "successful_users": successful_users,
                        "failed_users": failed_users,
                        "skipped_users": skipped_users,
                        "progress": round(progress, 2)
                    })
                
                # 用户间延迟
                if i < len(users_to_process) - 1:
                    delay = await _get_conservative_delay(conservative_config, failed_users, i + 1)
                    await asyncio.sleep(delay)
                
            except Exception as e:
                failed_users += 1
                logger.error(f"处理用户失败: {e}")
                
                # 记录异常失败的用户
                if task_id in db_manager._sync_progress_cache:
                    user_name = user.get('uname', f'User_{user.get("uid", "unknown")}') if 'user' in locals() else '未知用户'
                    db_manager._sync_progress_cache[task_id]["failed_user_list"].append({
                        "uid": user.get('uid') if 'user' in locals() else 'unknown',
                        "uname": user_name,
                        "reason": f"处理异常: {str(e)}"
                    })
        
        # 更新最终状态
        if task_id in db_manager._sync_progress_cache:
            db_manager._sync_progress_cache[task_id].update({
                "status": "completed",
                "progress": 100,
                "successful_users": successful_users,
                "failed_users": failed_users,
                "skipped_users": skipped_users,
                "end_time": datetime.now(),
                "message": f"保守同步完成：成功 {successful_users}，失败 {failed_users}，跳过 {skipped_users}"
            })
        
        logger.info(f"保守同步任务 {task_id} 完成：成功 {successful_users}，失败 {failed_users}，跳过 {skipped_users}")
        
    except Exception as e:
        logger.error(f"保守同步任务失败: {e}")
        if hasattr(db_manager, '_sync_progress_cache') and task_id in db_manager._sync_progress_cache:
            db_manager._sync_progress_cache[task_id].update({
                "status": "failed",
                "message": f"保守同步失败: {str(e)}",
                "end_time": datetime.now()
            })
    
    finally:
        if api:
            try:
                await api.close()
            except:
                pass


async def _ultra_conservative_sync_task(db_manager, task_id: str, users_to_process: list, start_pos: int):
    """超级保守同步的后台任务"""
    api = None
    try:
        api = await get_bilibili_api()
        
        # 超级保守同步配置
        ultra_config = {
            'base_delay': 10.0,
            'min_delay': 8.0,
            'max_delay': 30.0,
            'api_call_delay': 3.0,
            'batch_rest_interval': 120,  # 每10个用户休息2分钟
            'batch_size': 10
        }
        
        # 预热等待
        await asyncio.sleep(10)
        
        successful_users = 0
        failed_users = 0
        skipped_users = 0
        api_warnings = 0
        
        for i, user in enumerate(users_to_process):
            try:
                # 检查任务是否被取消
                if task_id not in db_manager._sync_progress_cache:
                    break
                
                uid = user.get('uid') or user.get('mid')
                uname = user.get('uname', f'User_{uid}')
                
                if not uid:
                    skipped_users += 1
                    continue
                
                # 更新当前处理状态
                if task_id in db_manager._sync_progress_cache:
                    db_manager._sync_progress_cache[task_id]["current_user"] = uname
                    db_manager._sync_progress_cache[task_id]["message"] = f"超级保守模式处理用户 {uname} ({i+1}/{len(users_to_process)})"
                
                # 检查是否需要跳过（最近6小时内已更新）
                if await _should_skip_user_ultra_conservative(db_manager, uid):
                    skipped_users += 1
                    logger.info(f"⏭️ 用户 {uname} 数据较新，跳过")
                    
                    # 记录跳过的用户
                    if task_id in db_manager._sync_progress_cache:
                        db_manager._sync_progress_cache[task_id]["skipped_user_list"].append({
                            "uid": uid,
                            "uname": uname,
                            "reason": "数据较新（6小时内已更新）"
                        })
                else:
                    # API调用前的额外延迟
                    await asyncio.sleep(ultra_config['api_call_delay'])
                    
                    # 获取用户统计信息
                    logger.info(f"🐌 超级保守模式处理用户 {uname}")
                    user_stats = await api.get_user_stats(uid)
                    
                    if user_stats:
                        await _update_user_stats_to_db(db_manager, uid, user, user_stats)
                        successful_users += 1
                        logger.info(f"✅ 用户 {uname} 处理成功")
                    else:
                        failed_users += 1
                        api_warnings += 1
                        logger.warning(f"❌ 用户 {uname} 处理失败")
                        
                        # 记录失败的用户
                        if task_id in db_manager._sync_progress_cache:
                            db_manager._sync_progress_cache[task_id]["failed_user_list"].append({
                                "uid": uid,
                                "uname": uname,
                                "reason": "API调用失败或返回数据为空"
                            })
                        
                        # API限制额外等待
                        await asyncio.sleep(60)
                
                # 批次休息
                if (i + 1) % ultra_config['batch_size'] == 0:
                    rest_time = ultra_config['batch_rest_interval']
                    logger.info(f"😴 批次休息 {rest_time} 秒，避免累积API压力...")
                    await asyncio.sleep(rest_time)
                
                # 更新进度
                if task_id in db_manager._sync_progress_cache:
                    progress = ((i + 1) / len(users_to_process)) * 100
                    db_manager._sync_progress_cache[task_id].update({
                        "processed_users": i + 1,
                        "successful_users": successful_users,
                        "failed_users": failed_users,
                        "skipped_users": skipped_users,
                        "api_warnings": api_warnings,
                        "progress": round(progress, 2)
                    })
                
                # 超级保守的用户间延迟
                if i < len(users_to_process) - 1:
                    delay = await _get_ultra_conservative_delay(ultra_config, api_warnings, failed_users)
                    await asyncio.sleep(delay)
                
            except Exception as e:
                failed_users += 1
                logger.error(f"处理用户失败: {e}")
                
                # 记录异常失败的用户
                if task_id in db_manager._sync_progress_cache:
                    user_name = user.get('uname', f'User_{user.get("uid", "unknown")}') if 'user' in locals() else '未知用户'
                    db_manager._sync_progress_cache[task_id]["failed_user_list"].append({
                        "uid": user.get('uid') if 'user' in locals() else 'unknown',
                        "uname": user_name,
                        "reason": f"处理异常: {str(e)}"
                    })
        
        # 更新最终状态
        if task_id in db_manager._sync_progress_cache:
            db_manager._sync_progress_cache[task_id].update({
                "status": "completed",
                "progress": 100,
                "successful_users": successful_users,
                "failed_users": failed_users,
                "skipped_users": skipped_users,
                "api_warnings": api_warnings,
                "end_time": datetime.now(),
                "message": f"超级保守同步完成：成功 {successful_users}，失败 {failed_users}，跳过 {skipped_users}"
            })
        
        logger.info(f"超级保守同步任务 {task_id} 完成：成功 {successful_users}，失败 {failed_users}，跳过 {skipped_users}")
        
    except Exception as e:
        logger.error(f"超级保守同步任务失败: {e}")
        if hasattr(db_manager, '_sync_progress_cache') and task_id in db_manager._sync_progress_cache:
            db_manager._sync_progress_cache[task_id].update({
                "status": "failed",
                "message": f"超级保守同步失败: {str(e)}",
                "end_time": datetime.now()
            })
    
    finally:
        if api:
            try:
                await api.close()
            except:
                pass


async def _should_skip_user_conservative(db_manager, uid: int) -> bool:
    """检查是否应该跳过用户（保守模式：1小时）"""
    try:
        cursor = await db_manager._connection.execute(
            "SELECT updated_at FROM user_stats WHERE uid = ?", (uid,)
        )
        result = await cursor.fetchone()
        if not result:
            return False
        
        from datetime import datetime
        try:
            last_time = datetime.fromisoformat(result[0])
            now = datetime.now()
            return (now - last_time).total_seconds() < 3600  # 1小时
        except:
            return False
    except:
        return False


async def _should_skip_user_ultra_conservative(db_manager, uid: int) -> bool:
    """检查是否应该跳过用户（超级保守模式：6小时）"""
    try:
        cursor = await db_manager._connection.execute(
            "SELECT updated_at FROM user_stats WHERE uid = ?", (uid,)
        )
        result = await cursor.fetchone()
        if not result:
            return False
        
        from datetime import datetime
        try:
            last_time = datetime.fromisoformat(result[0])
            now = datetime.now()
            return (now - last_time).total_seconds() < 21600  # 6小时
        except:
            return False
    except:
        return False


async def _update_user_stats_to_db(db_manager, uid: int, user: dict, user_stats: dict):
    """更新用户统计数据到数据库"""
    try:
        # 检查是否已存在
        cursor = await db_manager._connection.execute(
            "SELECT uid FROM user_stats WHERE uid = ?", (uid,)
        )
        existing = await cursor.fetchone()
        
        if existing:
            # 更新现有记录
            await db_manager._connection.execute("""
                UPDATE user_stats SET 
                    fans_count = ?, following_count = ?, video_count = ?,
                    total_views = ?, last_video_time = ?, activity_score = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE uid = ?
            """, (
                user_stats["fans_count"], user_stats["following_count"],
                user_stats["video_count"], user_stats["total_views"],
                user_stats["last_video_time"], user_stats["activity_score"], uid
            ))
        else:
            # 插入新记录
            await db_manager._connection.execute("""
                INSERT INTO user_stats 
                (uid, fans_count, following_count, video_count, total_views, 
                 last_video_time, activity_score) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                uid, user_stats["fans_count"], user_stats["following_count"],
                user_stats["video_count"], user_stats["total_views"],
                user_stats["last_video_time"], user_stats["activity_score"]
            ))
        
        await db_manager._connection.commit()
        
    except Exception as e:
        logger.error(f"更新用户统计数据到数据库失败: {e}")
        raise


async def _get_conservative_delay(config: dict, failed_count: int, processed_count: int) -> float:
    """获取保守延迟"""
    base_delay = config['base_delay']
    
    # 根据失败率调整
    if processed_count > 0:
        failure_rate = failed_count / processed_count
        if failure_rate > 0.2:
            base_delay *= (1 + failure_rate)
    
    # 随机抖动
    import random
    jitter = random.uniform(0.8, 1.2)
    final_delay = base_delay * jitter
    
    return max(config['min_delay'], min(final_delay, config['max_delay']))


async def _get_ultra_conservative_delay(config: dict, api_warnings: int, failed_count: int) -> float:
    """获取超级保守延迟"""
    base_delay = config['base_delay']
    
    # 根据API警告次数调整
    if api_warnings > 0:
        base_delay *= (1.0 + api_warnings * 0.5)
    
    # 根据失败次数调整
    if failed_count > 0:
        base_delay *= (1.0 + failed_count * 0.3)
    
    # 随机抖动
    import random
    jitter = random.uniform(0.9, 1.3)
    final_delay = base_delay * jitter
    
    return max(config['min_delay'], min(final_delay, config['max_delay']))


@router.get("/task-progress/{task_id}")
async def get_task_progress(task_id: str, req: Request):
    """获取任务进度（通用接口）"""
    try:
        db_manager = req.app.state.db_manager
        
        # 检查是否有进度缓存
        if hasattr(db_manager, '_sync_progress_cache'):
            if task_id in db_manager._sync_progress_cache:
                progress_data = db_manager._sync_progress_cache[task_id]
                
                # 转换datetime对象为字符串
                result = {}
                for key, value in progress_data.items():
                    if isinstance(value, datetime):
                        result[key] = value.isoformat()
                    else:
                        result[key] = value
                
                return result
        
        # 如果缓存中没有，尝试从数据库查询
        # 这里可以根据需要实现数据库查询逻辑
        
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已过期")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务进度失败: {e}")
        raise HTTPException(status_code=500, detail="获取任务进度失败")