#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化版同步任务恢复脚本
使用并发处理和性能优化器提升同步效率
"""

import asyncio
import sys
import time
from datetime import datetime
from src.database.manager import DatabaseManager
from src.bilibili.optimized_api import OptimizedBilibiliAPI
from src.core.performance_optimizer import OptimizationConfig
from src.core.logger import get_logger

logger = get_logger()

async def optimized_resume_sync(start_position: int = 0, limit: int = 0, 
                              concurrent_users: int = 8, batch_size: int = 30):
    """
    优化版同步任务恢复
    
    Args:
        start_position: 开始位置（从第几个用户开始）
        limit: 处理用户数量限制（0表示处理全部剩余用户）
        concurrent_users: 并发处理用户数
        batch_size: 批处理大小
    """
    try:
        # 初始化数据库和优化API
        db_manager = DatabaseManager()
        await db_manager.initialize()
        
        # 创建优化配置
        optimization_config = OptimizationConfig(
            max_concurrent_requests=concurrent_users,
            batch_size=batch_size,
            base_delay=0.2,  # 更短的基础延迟
            min_delay=0.1,
            max_delay=6.0,
            adaptive_delay=True,
            enable_cache=True,
            cache_ttl=300,  # 5分钟缓存
            failure_rate_threshold=0.6,  # 稍微宽松的失败率阈值
            failure_window_size=20,
            rate_limit_cooldown=20  # 较短的冷却时间
        )
        
        api = OptimizedBilibiliAPI(optimization_config)
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
        
        logger.info(f"使用优化配置: 并发数={concurrent_users}, 批大小={batch_size}")
        
        # 开始优化处理
        start_time = datetime.now()
        
        def progress_callback(current, total):
            """进度回调"""
            progress_percent = (current / total) * 100
            elapsed_time = (datetime.now() - start_time).total_seconds()
            rate = current / elapsed_time if elapsed_time > 0 else 0
            eta_seconds = (total - current) / rate if rate > 0 else 0
            eta_minutes = eta_seconds / 60
            
            logger.info(f"进度: {current}/{total} ({progress_percent:.1f}%), 速率: {rate:.2f}用户/秒, 预计剩余: {eta_minutes:.1f}分钟")
        
        # 使用优化API批量处理
        results = await api.get_users_stats_batch(users_to_process, progress_callback)
        
        # 保存结果到数据库
        updated_count = 0
        error_count = 0
        
        logger.info("开始保存结果到数据库...")
        
        for i, ((success, result), user) in enumerate(zip(results, users_to_process)):
            try:
                uid = user["uid"]
                uname = user.get('uname', str(uid))
                
                if success and result:
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
                                total_views = ?, last_video_time = ?, activity_score = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE uid = ?
                        """, (
                            result["fans_count"], result["following_count"], 
                            result["video_count"], result["total_views"],
                            result["last_video_time"], result["activity_score"], uid
                        ))
                    else:
                        # 插入新记录
                        await db_manager._connection.execute("""
                            INSERT INTO user_stats 
                            (uid, fans_count, following_count, video_count, total_views, 
                             last_video_time, activity_score) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            uid, result["fans_count"], result["following_count"],
                            result["video_count"], result["total_views"],
                            result["last_video_time"], result["activity_score"]
                        ))
                    
                    updated_count += 1
                    
                    # 每50个用户提交一次
                    if (i + 1) % 50 == 0:
                        await db_manager._connection.commit()
                    
                else:
                    error_count += 1
                    logger.warning(f"用户 {uname} 数据获取失败: {result}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"保存用户 {user.get('uname', uid)} 数据失败: {e}")
        
        # 最终提交
        await db_manager._connection.commit()
        
        # 输出最终结果和性能统计
        elapsed_time = (datetime.now() - start_time).total_seconds()
        performance_stats = api.get_performance_stats()
        
        logger.info(f"优化同步完成!")
        logger.info(f"处理结果: 总数={len(users_to_process)}, 成功={updated_count}, 失败={error_count}")
        logger.info(f"总耗时: {elapsed_time/60:.1f}分钟 (平均 {elapsed_time/len(users_to_process):.2f}秒/用户)")
        
        # 性能统计
        logger.info("性能统计:")
        logger.info(f"  总请求数: {performance_stats['total_requests']}")
        logger.info(f"  成功率: {performance_stats.get('success_rate', 0):.1%}")
        logger.info(f"  平均响应时间: {performance_stats['avg_response_time']:.2f}秒")
        logger.info(f"  缓存命中率: {performance_stats.get('cache_hit_rate', 0):.1%}")
        logger.info(f"  风控触发次数: {performance_stats['rate_limit_hits']}")
        
        # 清理资源
        await api.close()
        await db_manager.close()
        
    except Exception as e:
        logger.error(f"优化同步失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")

def main():
    """主函数"""
    print("B站批量操作工具 - 优化版同步任务恢复脚本")
    print("=" * 60)
    print("🚀 使用并发处理和智能优化算法，大幅提升同步效率！")
    print("=" * 60)
    
    # 获取命令行参数
    start_position = 0
    limit = 0
    concurrent_users = 8
    batch_size = 30
    
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
    
    if len(sys.argv) > 3:
        try:
            concurrent_users = int(sys.argv[3])
            concurrent_users = max(1, min(concurrent_users, 15))  # 限制在1-15之间
        except ValueError:
            print("错误: 并发数必须是数字")
            sys.exit(1)
    
    if len(sys.argv) > 4:
        try:
            batch_size = int(sys.argv[4])
            batch_size = max(10, min(batch_size, 100))  # 限制在10-100之间
        except ValueError:
            print("错误: 批大小必须是数字")
            sys.exit(1)
    
    # 如果没有提供参数，询问用户
    if len(sys.argv) <= 1:
        try:
            start_position = int(input("请输入开始位置 (从第几个用户开始，从0开始计数): ") or "0")
            limit = int(input("请输入处理数量 (0表示处理全部剩余用户): ") or "0")
            concurrent_users = int(input("请输入并发数 (1-15，推荐8): ") or "8")
            concurrent_users = max(1, min(concurrent_users, 15))
            batch_size = int(input("请输入批大小 (10-100，推荐30): ") or "30")
            batch_size = max(10, min(batch_size, 100))
        except ValueError:
            print("输入无效，使用默认值")
            start_position = 0
            limit = 0
            concurrent_users = 8
            batch_size = 30
    
    print(f"开始位置: {start_position}")
    print(f"处理数量: {'全部剩余用户' if limit == 0 else limit}")
    print(f"并发数: {concurrent_users}")
    print(f"批大小: {batch_size}")
    print("=" * 60)
    
    # 预估性能提升
    if concurrent_users > 1:
        estimated_speedup = min(concurrent_users * 0.7, 5.0)  # 考虑开销，最大5倍
        print(f"🔥 预估性能提升: {estimated_speedup:.1f}x 倍")
    
    # 确认执行
    if input("确定要执行优化同步吗？(y/N): ").lower() != 'y':
        print("已取消")
        return
    
    # 执行优化同步
    asyncio.run(optimized_resume_sync(start_position, limit, concurrent_users, batch_size))

if __name__ == "__main__":
    main() 