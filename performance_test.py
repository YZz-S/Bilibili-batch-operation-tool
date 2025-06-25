#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能测试脚本
Performance Testing Script

用于测试和对比优化前后的同步效率
"""

import asyncio
import time
import sys
from datetime import datetime
from typing import List, Dict, Any

from src.database.manager import DatabaseManager
from src.bilibili.api import BilibiliAPI
from src.bilibili.optimized_api import OptimizedBilibiliAPI
from src.core.performance_optimizer import OptimizationConfig
from src.core.logger import get_logger

logger = get_logger()


class PerformanceTest:
    """性能测试类"""
    
    def __init__(self):
        self.db_manager = None
        self.original_api = None
        self.optimized_api = None
    
    async def initialize(self):
        """初始化测试环境"""
        self.db_manager = DatabaseManager()
        await self.db_manager.initialize()
        
        # 创建原始API和优化API
        self.original_api = BilibiliAPI()
        
        # 配置优化API
        optimization_config = OptimizationConfig(
            max_concurrent_requests=8,
            batch_size=20,  # 测试用较小批次
            base_delay=0.2,
            min_delay=0.1,
            max_delay=5.0,
            adaptive_delay=True,
            enable_cache=True,
            cache_ttl=300
        )
        self.optimized_api = OptimizedBilibiliAPI(optimization_config)
    
    async def cleanup(self):
        """清理测试环境"""
        if self.original_api:
            await self.original_api.close()
        if self.optimized_api:
            await self.optimized_api.close()
        if self.db_manager:
            await self.db_manager.close()
    
    async def test_user_stats_performance(self, test_users: List[Dict[str, Any]], test_name: str = ""):
        """测试用户统计信息获取性能"""
        print(f"\n🧪 开始性能测试: {test_name}")
        print(f"测试用户数量: {len(test_users)}")
        print("=" * 60)
        
        # 测试原始方法
        print("📊 测试原始方法...")
        original_start = time.time()
        original_results = []
        original_success = 0
        
        for i, user in enumerate(test_users):
            try:
                uid = user.get('uid') or user.get('mid')
                result = await self.original_api.get_user_stats(uid)
                original_results.append((True, result))
                if result:
                    original_success += 1
                
                if (i + 1) % 5 == 0:
                    elapsed = time.time() - original_start
                    print(f"  原始方法进度: {i+1}/{len(test_users)}, 耗时: {elapsed:.1f}秒, 速率: {(i+1)/elapsed:.2f}用户/秒")
                
                # 原始方法的延迟
                await asyncio.sleep(self.original_api.api_delay)
                
            except Exception as e:
                original_results.append((False, str(e)))
        
        original_time = time.time() - original_start
        original_rate = len(test_users) / original_time
        
        print(f"✅ 原始方法完成:")
        print(f"  总耗时: {original_time:.1f}秒 ({original_time/60:.2f}分钟)")
        print(f"  成功数: {original_success}/{len(test_users)}")
        print(f"  成功率: {original_success/len(test_users):.1%}")
        print(f"  处理速率: {original_rate:.2f}用户/秒")
        print(f"  平均每用户: {original_time/len(test_users):.2f}秒")
        
        # 等待一段时间避免API限制
        print("\n⏳ 等待30秒后开始优化方法测试...")
        await asyncio.sleep(30)
        
        # 测试优化方法
        print("\n🚀 测试优化方法...")
        optimized_start = time.time()
        
        def progress_callback(current, total):
            elapsed = time.time() - optimized_start
            rate = current / elapsed if elapsed > 0 else 0
            print(f"  优化方法进度: {current}/{total}, 耗时: {elapsed:.1f}秒, 速率: {rate:.2f}用户/秒")
        
        optimized_results = await self.optimized_api.get_users_stats_batch(
            test_users, progress_callback
        )
        
        optimized_time = time.time() - optimized_start
        optimized_success = sum(1 for success, _ in optimized_results if success)
        optimized_rate = len(test_users) / optimized_time
        
        print(f"\n✅ 优化方法完成:")
        print(f"  总耗时: {optimized_time:.1f}秒 ({optimized_time/60:.2f}分钟)")
        print(f"  成功数: {optimized_success}/{len(test_users)}")
        print(f"  成功率: {optimized_success/len(test_users):.1%}")
        print(f"  处理速率: {optimized_rate:.2f}用户/秒")
        print(f"  平均每用户: {optimized_time/len(test_users):.2f}秒")
        
        # 性能对比
        print(f"\n📈 性能对比:")
        speedup = original_time / optimized_time if optimized_time > 0 else 0
        time_saved = original_time - optimized_time
        time_saved_percent = (time_saved / original_time) * 100 if original_time > 0 else 0
        
        print(f"  速度提升: {speedup:.2f}x 倍")
        print(f"  时间节省: {time_saved:.1f}秒 ({time_saved_percent:.1f}%)")
        print(f"  速率提升: {optimized_rate/original_rate:.2f}x 倍" if original_rate > 0 else "  速率提升: N/A")
        
        # 获取优化方法的性能统计
        perf_stats = self.optimized_api.get_performance_stats()
        print(f"\n📊 优化方法性能统计:")
        print(f"  总请求数: {perf_stats['total_requests']}")
        print(f"  成功率: {perf_stats.get('success_rate', 0):.1%}")
        print(f"  平均响应时间: {perf_stats['avg_response_time']:.2f}秒")
        print(f"  缓存命中率: {perf_stats.get('cache_hit_rate', 0):.1%}")
        print(f"  风控触发次数: {perf_stats['rate_limit_hits']}")
        
        return {
            "original": {
                "time": original_time,
                "success": original_success,
                "rate": original_rate
            },
            "optimized": {
                "time": optimized_time,
                "success": optimized_success,
                "rate": optimized_rate,
                "stats": perf_stats
            },
            "improvement": {
                "speedup": speedup,
                "time_saved": time_saved,
                "time_saved_percent": time_saved_percent
            }
        }
    
    async def test_following_list_performance(self):
        """测试关注列表获取性能"""
        print(f"\n🧪 测试关注列表获取性能")
        print("=" * 60)
        
        # 测试原始方法
        print("📊 测试原始方法获取关注列表...")
        original_start = time.time()
        original_following = await self.original_api.get_all_following(fetch_user_details=True)
        original_time = time.time() - original_start
        
        print(f"✅ 原始方法完成:")
        print(f"  总耗时: {original_time:.1f}秒 ({original_time/60:.2f}分钟)")
        print(f"  获取用户数: {len(original_following)}")
        print(f"  速率: {len(original_following)/original_time:.2f}用户/秒")
        
        # 等待
        print("\n⏳ 等待30秒后开始优化方法测试...")
        await asyncio.sleep(30)
        
        # 测试优化方法
        print("\n🚀 测试优化方法获取关注列表...")
        optimized_start = time.time()
        optimized_following = await self.optimized_api.get_all_following_optimized(fetch_user_details=True)
        optimized_time = time.time() - optimized_start
        
        print(f"✅ 优化方法完成:")
        print(f"  总耗时: {optimized_time:.1f}秒 ({optimized_time/60:.2f}分钟)")
        print(f"  获取用户数: {len(optimized_following)}")
        print(f"  速率: {len(optimized_following)/optimized_time:.2f}用户/秒")
        
        # 性能对比
        print(f"\n📈 关注列表获取性能对比:")
        speedup = original_time / optimized_time if optimized_time > 0 else 0
        print(f"  速度提升: {speedup:.2f}x 倍")
        print(f"  时间节省: {original_time - optimized_time:.1f}秒")
        
        return original_following[:50]  # 返回前50个用户用于后续测试
    
    async def run_comprehensive_test(self, max_test_users: int = 50):
        """运行综合性能测试"""
        print("🔬 B站批量操作工具 - 性能测试")
        print("=" * 60)
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"最大测试用户数: {max_test_users}")
        
        try:
            await self.initialize()
            
            # 检查API配置
            if not self.original_api.is_configured():
                print("❌ 错误: 未配置哔哩哔哩Cookie，请先配置")
                return
            
            # 1. 测试关注列表获取性能
            test_users = await self.test_following_list_performance()
            
            if len(test_users) == 0:
                print("❌ 错误: 无法获取测试用户，请检查API配置")
                return
            
            # 限制测试用户数量
            if len(test_users) > max_test_users:
                test_users = test_users[:max_test_users]
                print(f"\n📝 限制测试用户数为 {max_test_users} 个")
            
            # 2. 测试小批量用户统计信息获取（10个用户）
            small_batch = test_users[:min(10, len(test_users))]
            small_results = await self.test_user_stats_performance(small_batch, "小批量测试 (10用户)")
            
            # 3. 测试中批量用户统计信息获取（20个用户）
            if len(test_users) >= 20:
                medium_batch = test_users[:20]
                medium_results = await self.test_user_stats_performance(medium_batch, "中批量测试 (20用户)")
            
            # 4. 测试大批量用户统计信息获取（所有测试用户）
            if len(test_users) >= 30:
                large_results = await self.test_user_stats_performance(test_users, f"大批量测试 ({len(test_users)}用户)")
            
            # 总结报告
            print(f"\n🎯 性能测试总结报告")
            print("=" * 60)
            print(f"测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            if 'small_results' in locals():
                print(f"\n小批量测试 (10用户):")
                print(f"  速度提升: {small_results['improvement']['speedup']:.2f}x")
                print(f"  时间节省: {small_results['improvement']['time_saved_percent']:.1f}%")
            
            if 'medium_results' in locals():
                print(f"\n中批量测试 (20用户):")
                print(f"  速度提升: {medium_results['improvement']['speedup']:.2f}x")
                print(f"  时间节省: {medium_results['improvement']['time_saved_percent']:.1f}%")
            
            if 'large_results' in locals():
                print(f"\n大批量测试 ({len(test_users)}用户):")
                print(f"  速度提升: {large_results['improvement']['speedup']:.2f}x")
                print(f"  时间节省: {large_results['improvement']['time_saved_percent']:.1f}%")
            
            print(f"\n💡 优化建议:")
            print(f"  - 使用优化版API可以显著提升同步效率")
            print(f"  - 建议并发数设置为 6-10")
            print(f"  - 批处理大小建议设置为 20-40")
            print(f"  - 启用缓存可以进一步提升重复查询的效率")
            print(f"  - 对于 {len(test_users)} 个用户规模，预计可节省 {small_results['improvement']['time_saved_percent']:.0f}% 的时间")
            
            # 针对1300用户的预估
            if len(test_users) >= 20:
                avg_speedup = small_results['improvement']['speedup']
                estimated_original_time = 1300 * (small_results['original']['time'] / len(small_batch))
                estimated_optimized_time = estimated_original_time / avg_speedup
                estimated_savings = estimated_original_time - estimated_optimized_time
                
                print(f"\n🔮 1300用户规模预估:")
                print(f"  原始方法预估时间: {estimated_original_time/60:.1f}分钟")
                print(f"  优化方法预估时间: {estimated_optimized_time/60:.1f}分钟")
                print(f"  预估节省时间: {estimated_savings/60:.1f}分钟")
                print(f"  预估速度提升: {avg_speedup:.2f}x倍")
            
        except Exception as e:
            logger.error(f"性能测试失败: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    max_test_users = 50
    
    if len(sys.argv) > 1:
        try:
            max_test_users = int(sys.argv[1])
            max_test_users = max(5, min(max_test_users, 100))  # 限制在5-100之间
        except ValueError:
            print("错误: 测试用户数必须是数字")
            sys.exit(1)
    
    test = PerformanceTest()
    await test.run_comprehensive_test(max_test_users)


if __name__ == "__main__":
    asyncio.run(main()) 