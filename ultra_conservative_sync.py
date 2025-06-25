# -*- coding: utf-8 -*-
"""
超级保守同步工具
Ultra Conservative Sync Tool

使用最保守的策略，完全避免API频率限制
专为容易触发风控的环境设计
"""

import asyncio
import sys
import time
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

# 添加项目根目录到 Python 路径
sys.path.append('.')

from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.database.manager import DatabaseManager
from src.bilibili.api import BilibiliAPI


class UltraConservativeSyncManager:
    """超级保守同步管理器"""
    
    def __init__(self):
        """初始化管理器"""
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        self.logger = get_logger()
        
        # 初始化数据库和API
        self.db = DatabaseManager()
        self.api = BilibiliAPI()
        
        # 超级保守的配置
        self.ultra_conservative_config = {
            'base_delay': 10.0,  # 基础延迟10秒
            'min_delay': 8.0,    # 最小延迟8秒
            'max_delay': 30.0,   # 最大延迟30秒
            'api_call_delay': 3.0,  # API调用前额外延迟
            'retry_delay_multiplier': 2.0,  # 重试延迟倍数
            'batch_rest_interval': 120,  # 每批次后休息2分钟
            'batch_size': 10,    # 更小的批次大小
        }
        
        # 统计信息
        self.stats = {
            'total_users': 0,
            'processed_users': 0,
            'successful_users': 0,
            'failed_users': 0,
            'skipped_users': 0,
            'api_warnings': 0,
            'start_time': None,
            'end_time': None
        }
    
    async def sync_ultra_conservative(self, 
                                    start_pos: int = 0, 
                                    count: Optional[int] = None,
                                    max_failures: int = 5) -> bool:
        """超级保守同步关注列表"""
        self.logger.info("🐌🐌 开始超级保守同步模式")
        self.logger.info("⚠️⚠️  此模式使用最长延迟，完全避免API频率限制")
        
        self.stats['start_time'] = datetime.now()
        
        try:
            # 初始化数据库
            await self.db.initialize()
            
            # 获取关注列表
            self.logger.info("📋 获取关注列表...")
            following_list = await self._get_following_list_ultra_safely()
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
            self.logger.info(f"⏰ 预计总时间: {actual_count * 15 / 60:.1f} 分钟")
            
            # 超级保守处理用户
            failed_count = 0
            
            for i, user in enumerate(process_users):
                current_pos = start_pos + i + 1
                
                # 检查是否应该停止（失败过多）
                if failed_count >= max_failures:
                    self.logger.error(f"❌ 失败次数过多 ({failed_count})，停止处理")
                    break
                
                # 批次休息
                if i > 0 and i % self.ultra_conservative_config['batch_size'] == 0:
                    rest_time = self.ultra_conservative_config['batch_rest_interval']
                    self.logger.info(f"😴 批次休息 {rest_time} 秒，避免累积API压力...")
                    await asyncio.sleep(rest_time)
                
                self.logger.info(f"🔄 处理用户 {current_pos}/{total_users}: {user.get('uname', 'Unknown')}")
                
                # 超级保守处理单个用户
                success = await self._process_user_ultra_conservatively(user)
                
                if success:
                    self.stats['successful_users'] += 1
                    self.logger.info(f"✅ 用户 {user.get('uname')} 处理成功")
                else:
                    self.stats['failed_users'] += 1
                    failed_count += 1
                    self.logger.warning(f"❌ 用户 {user.get('uname')} 处理失败")
                
                self.stats['processed_users'] += 1
                
                # 显示进度
                self._show_progress(current_pos, total_users)
                
                # 超级保守的用户间延迟
                if i < len(process_users) - 1:  # 不是最后一个用户
                    delay = await self._get_ultra_conservative_delay()
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
    
    async def _get_following_list_ultra_safely(self) -> List[Dict[str, Any]]:
        """超级安全获取关注列表"""
        self.logger.info("🔍 使用超级保守模式获取关注列表...")
        
        # 预先等待，确保API状态清洁
        self.logger.info("⏳ 预热等待 10 秒...")
        await asyncio.sleep(10)
        
        try:
            # 获取关注列表（不获取详细信息，减少API调用）
            following_list = await self.api.get_all_following(fetch_user_details=False)
            
            if following_list:
                self.logger.info(f"✅ 成功获取 {len(following_list)} 个关注用户")
                return following_list
            else:
                self.logger.error("❌ 获取的关注列表为空")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ 获取关注列表失败: {e}")
            return []
    
    async def _process_user_ultra_conservatively(self, user: Dict[str, Any]) -> bool:
        """超级保守地处理单个用户"""
        uid = user.get('uid') or user.get('mid')
        uname = user.get('uname', 'Unknown')
        
        if not uid:
            self.logger.warning(f"⚠️  用户 {uname} 缺少UID，跳过")
            return False
        
        try:
            # 检查是否需要更新
            if await self._should_skip_user(uid):
                self.logger.info(f"⏭️  用户 {uname} 数据较新，跳过")
                self.stats['skipped_users'] += 1
                return True
            
            # API调用前的额外延迟
            api_delay = self.ultra_conservative_config['api_call_delay']
            self.logger.debug(f"⏳ API调用前等待 {api_delay} 秒...")
            await asyncio.sleep(api_delay)
            
            # 获取用户统计信息
            self.logger.debug(f"📊 获取用户 {uname} 的统计信息...")
            user_stats = await self.api.get_user_stats(uid)
            
            if not user_stats:
                raise Exception("无法获取用户统计信息")
            
            # 检查是否是风控响应
            if isinstance(user_stats, dict) and user_stats.get('code') in [-352, -503]:
                raise Exception(f"API限制错误: {user_stats.get('code')}")
            
            # 更新数据库
            await self._update_user_data(uid, user, user_stats)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 处理用户 {uname} 失败: {e}")
            
            # 如果是API限制，额外等待
            error_msg = str(e).lower()
            if 'api' in error_msg or '限制' in error_msg or '频繁' in error_msg:
                self.stats['api_warnings'] += 1
                extra_wait = 60  # 额外等待1分钟
                self.logger.warning(f"🚫 检测到API限制，额外等待 {extra_wait} 秒...")
                await asyncio.sleep(extra_wait)
            
            return False
    
    async def _should_skip_user(self, uid: int) -> bool:
        """检查是否应该跳过用户"""
        try:
            cursor = await self.db._connection.execute(
                "SELECT updated_at FROM following_list WHERE uid = ?", (uid,)
            )
            result = await cursor.fetchone()
            if not result:
                return False
            
            # 检查最后更新时间（如果最近6小时内更新过，跳过）
            last_updated = result[0]
            if last_updated:
                import datetime
                try:
                    last_time = datetime.datetime.fromisoformat(last_updated)
                    now = datetime.datetime.now()
                    if (now - last_time).total_seconds() < 21600:  # 6小时
                        return True
                except:
                    pass
            
            return False
            
        except Exception as e:
            self.logger.debug(f"检查用户跳过状态失败: {e}")
            return False
    
    async def _update_user_data(self, uid: int, user: Dict[str, Any], user_stats: Dict[str, Any]):
        """更新用户数据"""
        try:
            user_data = {
                'uid': uid,
                'uname': user.get('uname'),
                'face': user.get('face'),
                'following': user_stats.get('following', 0),
                'follower': user_stats.get('follower', 0),
                'video_count': user_stats.get('video_count', 0),
                'last_updated': datetime.now().isoformat()
            }
            
            await self.db.insert_following_user(user_data)
            
        except Exception as e:
            self.logger.error(f"更新用户数据失败: {e}")
            raise
    
    async def _get_ultra_conservative_delay(self) -> float:
        """获取超级保守延迟"""
        config = self.ultra_conservative_config
        base_delay = config['base_delay']
        
        # 根据API警告次数调整延迟
        if self.stats['api_warnings'] > 0:
            base_delay *= (1.0 + self.stats['api_warnings'] * 0.5)
        
        # 根据失败率调整
        if self.stats['processed_users'] > 0:
            failure_rate = self.stats['failed_users'] / self.stats['processed_users']
            if failure_rate > 0.1:  # 10%失败率就增加延迟
                base_delay *= (1.0 + failure_rate * 2)
        
        # 随机抖动
        import random
        jitter = random.uniform(0.9, 1.3)
        final_delay = base_delay * jitter
        
        # 确保在合理范围内
        return max(config['min_delay'], min(final_delay, config['max_delay']))
    
    def _show_progress(self, current: int, total: int):
        """显示进度"""
        percentage = (current / total) * 100
        processed = self.stats['processed_users']
        successful = self.stats['successful_users']
        failed = self.stats['failed_users']
        skipped = self.stats['skipped_users']
        api_warnings = self.stats['api_warnings']
        
        success_rate = (successful / processed * 100) if processed > 0 else 0
        
        self.logger.info(f"📈 进度: {current}/{total} ({percentage:.1f}%) | "
                        f"处理: {processed} | 成功: {successful} | 失败: {failed} | "
                        f"跳过: {skipped} | API警告: {api_warnings} | 成功率: {success_rate:.1f}%")
    
    async def _show_final_stats(self):
        """显示最终统计"""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        self.logger.info("🎉 超级保守同步完成!")
        self.logger.info("=" * 60)
        self.logger.info(f"总用户数: {self.stats['total_users']}")
        self.logger.info(f"处理用户数: {self.stats['processed_users']}")
        self.logger.info(f"成功用户数: {self.stats['successful_users']}")
        self.logger.info(f"失败用户数: {self.stats['failed_users']}")
        self.logger.info(f"跳过用户数: {self.stats['skipped_users']}")
        self.logger.info(f"API警告次数: {self.stats['api_warnings']}")
        self.logger.info(f"总耗时: {duration:.1f}秒 ({duration/60:.1f}分钟)")
        
        if self.stats['processed_users'] > 0:
            avg_time = duration / self.stats['processed_users']
            success_rate = self.stats['successful_users'] / self.stats['processed_users'] * 100
            self.logger.info(f"平均处理时间: {avg_time:.1f}秒/用户")
            self.logger.info(f"成功率: {success_rate:.1f}%")
            
            # 预估完成全部用户的时间
            if self.stats['total_users'] > self.stats['processed_users']:
                remaining = self.stats['total_users'] - self.stats['processed_users']
                estimated_time = remaining * avg_time / 3600
                self.logger.info(f"预估完成剩余用户时间: {estimated_time:.1f}小时")
        
        self.logger.info("=" * 60)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='B站关注列表超级保守同步工具')
    parser.add_argument('start', type=int, nargs='?', default=0, 
                       help='开始位置 (从0开始)')
    parser.add_argument('count', type=int, nargs='?', default=None, 
                       help='处理数量 (不指定则处理全部)')
    parser.add_argument('--max-failures', type=int, default=5,
                       help='最大失败次数 (默认5)')
    
    args = parser.parse_args()
    
    # 创建同步管理器
    sync_manager = UltraConservativeSyncManager()
    
    # 显示启动信息
    print("🐌🐌 B站关注列表超级保守同步工具")
    print("=" * 60)
    print("📋 模式说明:")
    print("   • 单线程处理，8-30秒延迟")
    print("   • 每10个用户休息2分钟")
    print("   • API调用前额外等待3秒")
    print("   • 智能跳过最近6小时内更新的用户")
    print("   • 完全避免API频率限制")
    print("=" * 60)
    
    if args.count:
        print(f"🎯 将处理位置 {args.start+1} 开始的 {args.count} 个用户")
        estimated_time = args.count * 15 / 60
        print(f"⏰ 预计耗时: {estimated_time:.1f} 分钟")
    else:
        print(f"🎯 将从位置 {args.start+1} 开始处理所有用户")
    
    print(f"🛡️  最大失败次数: {args.max_failures}")
    print("=" * 60)
    print("⚠️  注意: 此模式非常缓慢但极其稳定")
    print("💡 建议: 先测试10-20个用户，确认无问题后处理更多")
    print("=" * 60)
    
    # 确认开始
    try:
        input("按回车键开始，或 Ctrl+C 取消...")
    except KeyboardInterrupt:
        print("\n❌ 用户取消操作")
        return
    
    # 开始同步
    try:
        success = await sync_manager.sync_ultra_conservative(
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