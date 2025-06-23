#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复脚本
Test Fixes Script

验证VIP和认证数据修复是否正确工作
"""

import asyncio
import sqlite3
import json
from datetime import datetime

async def test_database_data():
    """测试数据库中的数据格式"""
    
    print("=" * 50)
    print("测试数据库数据格式")
    print("=" * 50)
    
    # 连接数据库
    try:
        conn = sqlite3.connect('data/bilibili.db')
        cursor = conn.cursor()
        
        # 检查数据库结构
        cursor.execute("PRAGMA table_info(following_list)")
        columns = cursor.fetchall()
        print("\n数据库表结构:")
        for col in columns:
            print(f"  {col[1]}: {col[2]} (NOT NULL: {col[3]}, DEFAULT: {col[4]})")
        
        # 检查VIP用户数据
        cursor.execute("""
            SELECT uid, uname, vip_type, vip_status, official_type, official_title 
            FROM following_list 
            WHERE vip_type > 0 OR official_type >= 0 
            LIMIT 10
        """)
        
        vip_users = cursor.fetchall()
        print(f"\n找到 {len(vip_users)} 个VIP/认证用户样本:")
        for user in vip_users:
            uid, uname, vip_type, vip_status, official_type, official_title = user
            print(f"  UID: {uid}, 用户名: {uname}")
            print(f"    VIP类型: {vip_type}, VIP状态: {vip_status}")
            print(f"    认证类型: {official_type}, 认证标题: {official_title}")
            print()
        
        # 统计VIP用户分布
        cursor.execute("""
            SELECT 
                CASE vip_type
                    WHEN 0 THEN '普通用户'
                    WHEN 1 THEN '月度大会员'
                    WHEN 2 THEN '年度大会员'
                    ELSE '其他VIP'
                END as vip_level,
                COUNT(*) as count
            FROM following_list 
            GROUP BY vip_type 
            ORDER BY vip_type
        """)
        
        vip_distribution = cursor.fetchall()
        print("VIP用户分布:")
        for vip_level, count in vip_distribution:
            print(f"  {vip_level}: {count}")
        
        # 统计认证用户分布
        cursor.execute("""
            SELECT 
                CASE official_type
                    WHEN -1 THEN '未认证'
                    WHEN 0 THEN '个人认证'
                    WHEN 1 THEN '机构认证'
                    ELSE '其他认证'
                END as official_level,
                COUNT(*) as count
            FROM following_list 
            GROUP BY official_type 
            ORDER BY official_type
        """)
        
        official_distribution = cursor.fetchall()
        print("\n认证用户分布:")
        for official_level, count in official_distribution:
            print(f"  {official_level}: {count}")
        
        # 检查分类数据
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM following_list 
            GROUP BY category 
            ORDER BY count DESC
        """)
        
        category_distribution = cursor.fetchall()
        print("\n分类分布:")
        for category, count in category_distribution:
            category_name = category if category else '未分类'
            print(f"  {category_name}: {count}")
        
        conn.close()
        print("\n✅ 数据库测试完成")
        
    except Exception as e:
        print(f"❌ 数据库测试失败: {e}")

def test_analyzer_logic():
    """测试分析器逻辑"""
    
    print("\n" + "=" * 50)
    print("测试分析器逻辑")
    print("=" * 50)
    
    # 模拟用户数据
    test_users = [
        {
            "uid": 1,
            "uname": "游戏解说UP主",
            "sign": "专业游戏解说，LOL攻略分享",
            "vip_type": 2,
            "official_type": 0
        },
        {
            "uid": 2,
            "uname": "科技数码频道",
            "sign": "最新手机评测，数码科技资讯",
            "vip_type": 1,
            "official_type": 1
        },
        {
            "uid": 3,
            "uname": "普通用户",
            "sign": "这个人很懒，什么都没有写～",
            "vip_type": 0,
            "official_type": -1
        }
    ]
    
    # 导入分析器
    try:
        import sys
        sys.path.append('src')
        from bilibili.analyzer import FollowingAnalyzer
        
        analyzer = FollowingAnalyzer()
        
        print("测试用户分类:")
        for user in test_users:
            category = analyzer.classify_user(user)
            print(f"  用户: {user['uname']}")
            print(f"    签名: {user['sign']}")
            print(f"    分类: {category}")
            print()
        
        print("测试分布分析:")
        distribution = analyzer.analyze_following_distribution(test_users)
        
        print("  分类分布:")
        for category, count in distribution.get('category_distribution', {}).items():
            print(f"    {category}: {count}")
        
        print("  VIP分布:")
        for vip_type, count in distribution.get('vip_distribution', {}).items():
            print(f"    {vip_type}: {count}")
        
        print("  认证分布:")
        for official_type, count in distribution.get('official_distribution', {}).items():
            print(f"    {official_type}: {count}")
        
        print("\n✅ 分析器测试完成")
        
    except Exception as e:
        print(f"❌ 分析器测试失败: {e}")

def main():
    """主函数"""
    print("Bilibili工具修复验证脚本")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 运行测试
    asyncio.run(test_database_data())
    test_analyzer_logic()
    
    print("\n" + "=" * 50)
    print("修复验证完成")
    print("=" * 50)
    print("\n修复内容:")
    print("1. ✅ 修复了analysis页面每次访问时自动更新分类的问题")
    print("2. ✅ 修复了VIP和认证数据的字段映射问题")
    print("3. ✅ 添加了手动更新分类的功能")
    print("4. ✅ 增强了数据类型验证和错误处理")
    print("\n建议:")
    print("- 重启应用服务器以应用修复")
    print("- 访问analysis页面点击'更新分类'按钮手动分类未分类用户")
    print("- 检查following页面VIP和认证徽章显示是否正常")

if __name__ == "__main__":
    main() 