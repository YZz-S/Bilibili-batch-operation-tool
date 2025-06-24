#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步任务恢复脚本
用于从指定位置恢复中断的同步任务
"""

import asyncio
import sys
import time
from datetime import datetime
from src.database.manager import DatabaseManager
from src.bilibili.api import get_bilibili_api
from src.core.logger import get_logger

logger = get_logger()

async def resume_sync_from_position(start_position: int = 0, limit: int = 0):
    """
    从指定位置恢复同步任务
    
    Args:
        start_position: 开始位置（从第几个用户开始）
        limit: 处理用户数量限制（0表示处理全部剩余用户）
    """
    try:
        # 初始化数据库和API
        db_manager = DatabaseManager()
        await db_manager.initialize()
        
        api = await get_bilibili_api()
        if not api.is_configured():
            logger.error("未配置哔哩哔哩Cookie，请先配置")
            return
        
        # 获取所有用户列表
        following_list = await db_manager.get_following_list()
        logger.info(f"总共 {len(following_list)} 个用户")
        
        if start_position >= len(following_list):
            logger.error(f"开始位置 {start_position} 超出用户总数 {len(following_list)}")
            return
        
        # 确定处理范围
        if limit == 0:
            users_to_process = following_list[start_position:]
            logger.info(f"从第 {start_position+1} 个用户开始，处理剩余 {len(users_to_process)} 个用户")
        else:
            end_position = min(start_position + limit, len(following_list))
            users_to_process = following_list[start_position:end_position]
            logger.info(f"从第 {start_position+1} 个用户开始，处理 {len(users_to_process)} 个用户")
        
        # 开始处理
        updated_count = 0
        error_count = 0
        start_time = datetime.now()
        
        for i, user in enumerate(users_to_process):
            try:
                uid = user["uid"]
                uname = user.get('uname', str(uid))
                current_position = start_position + i + 1
                
                logger.info(f"处理第 {current_position}/{len(following_list)} 个用户: {uname} (UID: {uid})")
                
                # 从B站API获取真实统计数据
                real_stats = await api.get_user_stats(uid)
                
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
                    
                    # 立即提交每个用户的更改
                    await db_manager._connection.commit()
                    
                    updated_count += 1
                    logger.info(f"✅ 已更新用户 {uname} 的统计数据 (成功: {updated_count}, 失败: {error_count})")
                else:
                    error_count += 1
                    logger.warning(f"❌ 获取用户 {uname} 统计数据失败 (成功: {updated_count}, 失败: {error_count})")
                
                # 每处理5个用户报告一次进度
                if (i + 1) % 5 == 0:
                    elapsed_time = (datetime.now() - start_time).total_seconds()
                    logger.info(f"进度: {i + 1}/{len(users_to_process)}, 成功: {updated_count}, 失败: {error_count}, 耗时: {elapsed_time/60:.1f}分钟")
                
                # 添加延迟以避免API限制
                await asyncio.sleep(6.0)  # 6秒延迟
                
            except Exception as e:
                error_count += 1
                logger.error(f"处理用户 {user.get('uname', uid)} 失败: {e}")
                continue
        
        # 输出最终结果
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"恢复同步完成: 处理 {len(users_to_process)} 个用户, 成功 {updated_count} 个, 失败 {error_count} 个, 总耗时: {elapsed_time/60:.1f}分钟")
        
        # 清理资源
        await api.close()
        await db_manager.close()
        
    except Exception as e:
        logger.error(f"恢复同步失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")

def main():
    """主函数"""
    print("B站批量操作工具 - 同步任务恢复脚本")
    print("=" * 50)
    
    # 获取命令行参数
    start_position = 0
    limit = 0
    
    if len(sys.argv) > 1:
        try:
            start_position = int(sys.argv[1])
        except ValueError:
            print("错误: 开始位置必须是数字")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except ValueError:
            print("错误: 处理数量必须是数字")
            sys.exit(1)
    
    # 如果没有提供参数，询问用户
    if len(sys.argv) <= 1:
        try:
            start_position = int(input("请输入开始位置 (从第几个用户开始，从0开始计数): ") or "0")
            limit = int(input("请输入处理数量 (0表示处理全部剩余用户): ") or "0")
        except ValueError:
            print("输入无效，使用默认值")
            start_position = 0
            limit = 0
    
    print(f"开始位置: {start_position}")
    print(f"处理数量: {'全部剩余用户' if limit == 0 else limit}")
    print("=" * 50)
    
    # 确认执行
    if input("确定要执行恢复同步吗？(y/N): ").lower() != 'y':
        print("已取消")
        return
    
    # 执行恢复同步
    asyncio.run(resume_sync_from_position(start_position, limit))

if __name__ == "__main__":
    main() 