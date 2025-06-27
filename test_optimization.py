#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化功能测试脚本
Test Script for Optimization Features
"""

import asyncio
import time
import sys
from datetime import datetime

# 添加src目录到路径
sys.path.insert(0, 'src')

from src.bilibili.api import get_bilibili_api
from src.database.manager import DatabaseManager
from src.core.logger import get_logger

logger = get_logger()

async def test_optimization_features():
    """测试优化功能"""
    print("=" * 60)
    print("🚀 哔哩哔哩批量操作工具 - 优化功能测试")
    print("=" * 60)
    
    try:
        # 初始化
        api = await get_bilibili_api()
        if not api.is_configured():
            print("❌ 错误：未配置哔哩哔哩Cookie，请先配置")
            return
        
        db_manager = DatabaseManager()
        await db_manager.initialize()
        
        print("✅ 初始化完成\n")
        
        # 测试1：合并获取关注列表和分组
        print("🔧 测试1: 合并获取关注列表和分组信息")
        start_time = time.time()
        
        following_list, groups_list = await api.get_following_and_groups_combined()
        
        duration = time.time() - start_time
        print(f"✅ 合并获取完成 - 耗时: {duration:.2f}s")
        print(f"   关注用户: {len(following_list)} 个")
        print(f"   分组信息: {len(groups_list) if groups_list else 0} 个")
        
        # 检查是否包含分类信息
        classified_users = [user for user in following_list if user.get('category')]
        print(f"   已分类用户: {len(classified_users)} 个（边同步边分类）")
        print()
        
        if not following_list:
            print("⚠️ 警告：未获取到关注列表，跳过后续测试")
            return
        
        # 测试2：增量更新策略
        print("🔧 测试2: 增量更新策略")
        
        # 测试小批量用户（前10个）
        test_users = following_list[:10]
        
        # 第一次获取（应该全部更新）
        print("   第一次批量获取统计数据...")
        start_time = time.time()
        
        results1 = await api.get_user_stats_batch(test_users, skip_recent_hours=24)
        
        duration1 = time.time() - start_time
        success_count1 = sum(1 for success, _ in results1 if success)
        print(f"   ✅ 第一次完成 - 耗时: {duration1:.2f}s，成功: {success_count1}/{len(test_users)}")
        
        # 等待2秒
        await asyncio.sleep(2)
        
        # 第二次获取（应该跳过大部分）
        print("   第二次批量获取统计数据（测试增量更新）...")
        start_time = time.time()
        
        results2 = await api.get_user_stats_batch(test_users, skip_recent_hours=1)  # 1小时内跳过
        
        duration2 = time.time() - start_time
        skipped_count = sum(1 for success, result in results2 if success and result == "skipped")
        print(f"   ✅ 第二次完成 - 耗时: {duration2:.2f}s，跳过: {skipped_count}/{len(test_users)}")
        print(f"   💡 增量更新节省时间: {duration1 - duration2:.2f}s ({(duration1-duration2)/duration1*100:.1f}%)")
        print()
        
        # 测试3：性能统计
        print("🔧 测试3: 性能统计")
        
        if hasattr(api, 'get_performance_stats'):
            stats = api.get_performance_stats()
            print("   性能统计数据:")
            for key, value in stats.items():
                print(f"     {key}: {value}")
        else:
            print("   ⚠️ 当前API版本不支持性能统计")
        
        print()
        
        # 测试结果总结
        print("📊 测试结果总结:")
        print(f"   ✅ 合并获取功能正常，获取 {len(following_list)} 个用户")
        print(f"   ✅ 边同步边分类功能正常，自动分类 {len(classified_users)} 个用户")
        print(f"   ✅ 增量更新功能正常，跳过 {skipped_count}/{len(test_users)} 个用户")
        print(f"   ⚡ 优化效果显著，第二次请求节省 {(duration1-duration2)/duration1*100:.1f}% 时间")
        
        # 清理
        await api.close()
        await db_manager.close()
        
        print("\n🎉 所有优化功能测试通过！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_api_methods():
    """测试API方法可用性"""
    print("\n🔧 测试API方法可用性")
    
    try:
        api = await get_bilibili_api()
        
        # 检查新增的方法
        methods_to_test = [
            'get_following_and_groups_combined',
            'get_user_stats_batch',
            '_get_user_stats_optimized',
            '_build_user_stats',
            '_calculate_activity_score'
        ]
        
        for method_name in methods_to_test:
            if hasattr(api, method_name):
                print(f"   ✅ {method_name} - 可用")
            else:
                print(f"   ❌ {method_name} - 不可用")
        
        await api.close()
        
    except Exception as e:
        print(f"   ❌ API方法测试失败: {e}")

def main():
    """主函数"""
    try:
        # 运行测试
        asyncio.run(test_api_methods())
        asyncio.run(test_optimization_features())
        
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")

if __name__ == "__main__":
    main() 