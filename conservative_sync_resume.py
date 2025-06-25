# -*- coding: utf-8 -*-
"""
保守同步工具
Conservative Sync Tool

专门针对容易触发风控的环境，采用单线程、更长延迟的保守策略
"""

import asyncio
import sys
import time
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

# 添加项目根目录到 Python 路径
sys.path.append('.')

from src.core.conservative_optimizer import get_conservative_optimizer, ConservativeOptimizationConfig
from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.database.manager import DatabaseManager
from src.bilibili.api import BilibiliAPI


class ConservativeSyncManager:
    """保守同步管理器"""
    
    def __init__(self, config_path: str = None):
        """初始化管理器"""
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        self.logger = get_logger()
        
        # 初始化数据库和API
        self.db = DatabaseManager()
        self.api = BilibiliAPI()
        
        # 初始化保守优化器
        self.optimizer = get_conservative_optimizer()
        
        # 统计信息
        self.stats = {
            'total_users': 0,
            'processed_users': 0,
            'successful_users': 0,
            'failed_users': 0,
            'skipped_users': 0,
            'start_time': None,
            'end_time': None,
            'wind_control_hits': 0
        }
    
    async def sync_conservative(self, 
                              start_pos: int = 0, 
                              count: Optional[int] = None,
                              max_failures: int = 10) -> bool:
        """保守同步关注列表"""
        self.logger.info("🐌 开始保守同步模式")
        self.logger.info("⚠️  注意：此模式采用单线程处理，避免触发风控")
        
        self.stats['start_time'] = datetime.now()
        
        try:
            # 初始化数据库
            await self.db.initialize()
            # 获取关注列表
            self.logger.info("📋 获取关注列表...")
            following_list = await self._get_following_list_safely()
            if not following_list:
                self.logger.error("❌ 无法获取关注列表")
                return False
            
            total_users = len(following_list)
            self.stats['total_users'] = total_users
            self.logger.info(f"📊 总共发现 {total_users} 个关注用户")
            
            # 确定处理范围
            end_pos = min(start_pos + count, total_users) if count else total_users
            process_users = following_list[start_pos:end_pos]
            actual_count = len(process_users)
            
            self.logger.info(f"🎯 将处理位置 {start_pos+1}-{end_pos} 的 {actual_count} 个用户")
            
            # 保守处理用户
            failed_count = 0
            results = []
            
            for i, user in enumerate(process_users):
                current_pos = start_pos + i + 1
                
                # 检查是否应该停止（失败过多）
                if failed_count >= max_failures:
                    self.logger.error(f"❌ 失败次数过多 ({failed_count})，停止处理")
                    break
                
                self.logger.info(f"🔄 处理用户 {current_pos}/{total_users}: {user.get('uname', 'Unknown')}")
                
                # 保守处理单个用户
                success = await self._process_user_conservatively(user)
                results.append((success, user))
                
                if success:
                    self.stats['successful_users'] += 1
                    self.logger.info(f"✅ 用户 {user.get('uname')} 处理成功")
                else:
                    self.stats['failed_users'] += 1
                    failed_count += 1
                    self.logger.warning(f"❌ 用户 {user.get('uname')} 处理失败")
                
                self.stats['processed_users'] += 1
                
                # 显示进度和统计
                self._show_progress(current_pos, total_users)
                
                # 每处理5个用户显示详细统计
                if i % 5 == 4:
                    await self._show_detailed_stats()
                
                # 保守的用户间延迟
                if i < len(process_users) - 1:  # 不是最后一个用户
                    delay = await self._get_inter_user_delay()
                    self.logger.info(f"⏱️  等待 {delay:.1f} 秒后处理下一个用户...")
                    await asyncio.sleep(delay)
            
            self.stats['end_time'] = datetime.now()
            await self._show_final_stats()
            
            return self.stats['successful_users'] > 0
            
        except Exception as e:
            self.logger.error(f"❌ 同步过程发生错误: {e}")
            return False
        finally:
            # 清理资源
            await self.db.close()
            await self.api.close()
    
    async def _get_following_list_safely(self) -> List[Dict[str, Any]]:
        """安全获取关注列表"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.logger.info(f"🔍 尝试获取关注列表 (第 {retry_count + 1} 次)")
                
                # 使用保守延迟
                if retry_count > 0:
                    wait_time = 30 * retry_count
                    self.logger.info(f"⏳ 等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
                
                # 获取关注列表（不获取详细信息）
                following_list = await self.api.get_all_following(fetch_user_details=False)
                
                if following_list:
                    self.logger.info(f"✅ 成功获取 {len(following_list)} 个关注用户")
                    return following_list
                else:
                    self.logger.warning("⚠️  获取的关注列表为空")
                    retry_count += 1
                    
            except Exception as e:
                self.logger.error(f"❌ 获取关注列表失败: {e}")
                retry_count += 1
                
                # 检查是否是风控错误
                if '-352' in str(e) or '-503' in str(e):
                    wait_time = 60 * (retry_count + 1)
                    self.logger.error(f"🚫 检测到风控，等待 {wait_time} 秒...")
                    await asyncio.sleep(wait_time)
        
        return []
    
    async def _process_user_conservatively(self, user: Dict[str, Any]) -> bool:
        """保守地处理单个用户"""
        uid = user.get('uid') or user.get('mid')
        uname = user.get('uname', 'Unknown')
        
        if not uid:
            self.logger.warning(f"⚠️  用户 {uname} 缺少UID，跳过")
            return False
        
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # 检查是否需要更新
                if await self._should_skip_user(uid):
                    self.logger.info(f"⏭️  用户 {uname} 数据较新，跳过")
                    self.stats['skipped_users'] += 1
                    return True
                
                # 获取用户统计信息
                self.logger.debug(f"📊 获取用户 {uname} 的统计信息...")
                
                # 保守的API调用
                await asyncio.sleep(0.5)  # 额外的小延迟
                user_stats = await self.api.get_user_stats(uid)
                
                if not user_stats:
                    raise Exception("无法获取用户统计信息")
                
                # 检查是否是风控响应
                if isinstance(user_stats, dict) and user_stats.get('code') in [-352, -503]:
                    self.stats['wind_control_hits'] += 1
                    raise Exception(f"风控错误: {user_stats.get('code')}")
                
                # 更新数据库
                await self._update_user_data(uid, user, user_stats)
                
                return True
                
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                
                # 风控错误处理
                if '-352' in error_msg or '-503' in error_msg or '风控' in error_msg:
                    wait_time = 60 * retry_count
                    self.logger.error(f"🚫 用户 {uname} 触发风控，等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
                    continue
                
                # 其他错误
                if retry_count <= max_retries:
                    wait_time = 10 * retry_count
                    self.logger.warning(f"⚠️  用户 {uname} 处理失败，{wait_time}秒后重试: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"❌ 用户 {uname} 最终处理失败: {e}")
        
        return False
    
    async def _should_skip_user(self, uid: int) -> bool:
        """检查是否应该跳过用户"""
        try:
            # 检查数据库中是否存在该用户的最近更新记录
            cursor = await self.db._connection.execute(
                "SELECT updated_at FROM following_list WHERE uid = ?", (uid,)
            )
            result = await cursor.fetchone()
            if not result:
                return False
            
            user_data = {'last_updated': result[0]}
            
            # 检查最后更新时间（如果最近1小时内更新过，跳过）
            last_updated = user_data.get('last_updated')
            if last_updated:
                import datetime
                last_time = datetime.datetime.fromisoformat(last_updated)
                now = datetime.datetime.now()
                if (now - last_time).total_seconds() < 3600:  # 1小时
                    return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"检查用户跳过状态失败: {e}")
            return False
    
    async def _update_user_data(self, uid: int, user: Dict[str, Any], user_stats: Dict[str, Any]):
        """更新用户数据"""
        try:
            # 更新user_stats表
            cursor = await self.db._connection.execute(
                "SELECT uid FROM user_stats WHERE uid = ?", (uid,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # 更新现有记录
                await self.db._connection.execute("""
                    UPDATE user_stats SET 
                        fans_count = ?, following_count = ?, video_count = ?,
                        total_views = ?, last_video_time = ?, activity_score = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE uid = ?
                """, (
                    user_stats.get("fans_count", 0), user_stats.get("following_count", 0),
                    user_stats.get("video_count", 0), user_stats.get("total_views", 0),
                    user_stats.get("last_video_time", 0), user_stats.get("activity_score", 0.5), uid
                ))
            else:
                # 插入新记录
                await self.db._connection.execute("""
                    INSERT INTO user_stats 
                    (uid, fans_count, following_count, video_count, total_views, 
                     last_video_time, activity_score) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    uid, user_stats.get("fans_count", 0), user_stats.get("following_count", 0),
                    user_stats.get("video_count", 0), user_stats.get("total_views", 0),
                    user_stats.get("last_video_time", 0), user_stats.get("activity_score", 0.5)
                ))
            
            await self.db._connection.commit()
            
        except Exception as e:
            self.logger.error(f"更新用户数据失败: {e}")
            raise
    
    async def _get_inter_user_delay(self) -> float:
        """获取用户间延迟"""
        # 基础延迟
        base_delay = 3.0
        
        # 根据统计信息调整
        optimizer_stats = self.optimizer.get_performance_stats()
        
        # 如果有风控，增加延迟
        if optimizer_stats.get('wind_control_detected'):
            base_delay *= 2.0
        
        # 根据失败率调整
        failure_rate = optimizer_stats.get('recent_failure_rate', 0)
        if failure_rate > 0.2:
            base_delay *= (1 + failure_rate)
        
        # 随机抖动
        import random
        jitter = random.uniform(0.8, 1.3)
        
        return base_delay * jitter
    
    def _show_progress(self, current: int, total: int):
        """显示进度"""
        percentage = (current / total) * 100
        processed = self.stats['processed_users']
        successful = self.stats['successful_users']
        failed = self.stats['failed_users']
        skipped = self.stats['skipped_users']
        
        success_rate = (successful / processed * 100) if processed > 0 else 0
        
        self.logger.info(f"📈 进度: {current}/{total} ({percentage:.1f}%) | "
                        f"处理: {processed} | 成功: {successful} | 失败: {failed} | 跳过: {skipped} | "
                        f"成功率: {success_rate:.1f}%")
    
    async def _show_detailed_stats(self):
        """显示详细统计"""
        optimizer_stats = self.optimizer.get_performance_stats()
        
        self.logger.info("📊 详细统计:")
        self.logger.info(f"   🎯 成功率: {optimizer_stats.get('success_rate', 0):.1%}")
        self.logger.info(f"   ⏱️  平均响应时间: {optimizer_stats.get('avg_response_time', 0):.2f}秒")
        self.logger.info(f"   💾 缓存命中率: {optimizer_stats.get('cache_hit_rate', 0):.1%}")
        self.logger.info(f"   🚫 风控检测次数: {optimizer_stats.get('wind_control_hits', 0)}")
        self.logger.info(f"   🔄 当前延迟: {optimizer_stats.get('current_delay', 0):.1f}秒")
        
        if optimizer_stats.get('wind_control_detected'):
            self.logger.warning(f"   ⚠️  当前处于风控状态")
    
    async def _show_final_stats(self):
        """显示最终统计"""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        self.logger.info("🎉 保守同步完成!")
        self.logger.info("=" * 50)
        self.logger.info(f"总用户数: {self.stats['total_users']}")
        self.logger.info(f"处理用户数: {self.stats['processed_users']}")
        self.logger.info(f"成功用户数: {self.stats['successful_users']}")
        self.logger.info(f"失败用户数: {self.stats['failed_users']}")
        self.logger.info(f"跳过用户数: {self.stats['skipped_users']}")
        self.logger.info(f"风控触发次数: {self.stats['wind_control_hits']}")
        self.logger.info(f"总耗时: {duration:.1f}秒 ({duration/60:.1f}分钟)")
        
        if self.stats['processed_users'] > 0:
            avg_time = duration / self.stats['processed_users']
            success_rate = self.stats['successful_users'] / self.stats['processed_users'] * 100
            self.logger.info(f"平均处理时间: {avg_time:.1f}秒/用户")
            self.logger.info(f"成功率: {success_rate:.1f}%")
        
        self.logger.info("=" * 50)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='B站关注列表保守同步工具')
    parser.add_argument('start', type=int, nargs='?', default=0, 
                       help='开始位置 (从0开始)')
    parser.add_argument('count', type=int, nargs='?', default=None, 
                       help='处理数量 (不指定则处理全部)')
    parser.add_argument('--max-failures', type=int, default=10,
                       help='最大失败次数 (默认10)')
    parser.add_argument('--config', type=str, default=None,
                       help='配置文件路径')
    
    args = parser.parse_args()
    
    # 创建同步管理器
    sync_manager = ConservativeSyncManager(args.config)
    
    # 显示启动信息
    print("🐌 B站关注列表保守同步工具")
    print("=" * 50)
    print("📋 模式说明:")
    print("   • 单线程顺序处理，避免触发风控")
    print("   • 更长的延迟时间 (2-15秒)")
    print("   • 智能风控检测和恢复")
    print("   • 缓存机制减少重复请求")
    print("=" * 50)
    
    if args.count:
        print(f"🎯 将处理位置 {args.start+1} 开始的 {args.count} 个用户")
    else:
        print(f"🎯 将从位置 {args.start+1} 开始处理所有用户")
    
    print(f"🛡️  最大失败次数: {args.max_failures}")
    print("=" * 50)
    
    # 确认开始
    try:
        input("按回车键开始，或 Ctrl+C 取消...")
    except KeyboardInterrupt:
        print("\n❌ 用户取消操作")
        return
    
    # 开始同步
    try:
        success = await sync_manager.sync_conservative(
            start_pos=args.start,
            count=args.count,
            max_failures=args.max_failures
        )
        
        if success:
            print("✅ 同步完成")
        else:
            print("❌ 同步失败")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️  用户中断操作")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 