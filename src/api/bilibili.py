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
            
            # VIP用户：vip_type > 0
            vip_info = user.get("vip", {})
            vip_type = vip_info.get("vipType", 0) if isinstance(vip_info, dict) else user.get("vip_type", 0)
            if vip_type and vip_type > 0:
                vip_count += 1
            
            # 认证用户：official_verify.type >= 0 或 official_type > 0
            official_verify = user.get("official_verify", {})
            if isinstance(official_verify, dict):
                official_type = official_verify.get("type", -1)
            else:
                official_type = user.get("official_type", -1)
            
            if official_type and official_type >= 0:
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
            ]
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