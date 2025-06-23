#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改进版等级修复脚本 - 支持断点续传和更智能的错误处理
"""

import asyncio
import aiosqlite
import time
import random
import json
from datetime import datetime
from src.bilibili.api import get_bilibili_api
from src.core.logger import get_logger

logger = get_logger()

class LevelFixResumer:
    def __init__(self):
        self.progress_file = "level_fix_progress.json"
        self.max_consecutive_failures = 5
        self.base_delay = 3  # 基础延迟时间（秒）
        self.max_delay = 30  # 最大延迟时间（秒）
        self.failure_backoff = 1.5  # 失败后延迟倍数

    async def load_progress(self):
        """加载之前的进度"""
        try:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "processed_uids": [],
                "last_success_time": None,
                "consecutive_failures": 0,
                "current_delay": self.base_delay
            }

    async def save_progress(self, progress):
        """保存当前进度"""
        progress["last_update"] = datetime.now().isoformat()
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

    async def get_users_to_fix(self, processed_uids):
        """获取需要修复等级的用户（排除已处理的）"""
        async with aiosqlite.connect("data/bilibili.db") as db:
            if processed_uids:
                placeholders = ','.join('?' * len(processed_uids))
                cursor = await db.execute(f"""
                    SELECT uid, uname FROM following_list 
                    WHERE (level IS NULL OR level = 0) 
                    AND uid NOT IN ({placeholders})
                    ORDER BY uid
                """, processed_uids)
            else:
                cursor = await db.execute("""
                    SELECT uid, uname FROM following_list 
                    WHERE (level IS NULL OR level = 0) 
                    ORDER BY uid
                """)
            return await cursor.fetchall()

    async def fix_user_level(self, api, uid, uname):
        """修复单个用户的等级"""
        try:
            user_info = await api.get_user_info(uid)
            if user_info and 'level' in user_info:
                level = user_info['level']
                
                # 更新数据库
                async with aiosqlite.connect("data/bilibili.db") as db:
                    await db.execute(
                        "UPDATE following_list SET level = ? WHERE uid = ?",
                        (level, uid)
                    )
                    await db.commit()
                
                return True, level, None
            else:
                return False, None, "无法获取用户信息"
        except Exception as e:
            return False, None, str(e)

    async def check_current_status(self):
        """检查当前等级修复状态"""
        async with aiosqlite.connect("data/bilibili.db") as db:
            # 统计需要修复的用户数
            cursor = await db.execute("""
                SELECT COUNT(*) FROM following_list 
                WHERE (level IS NULL OR level = 0)
            """)
            need_fix_count = (await cursor.fetchone())[0]
            
            # 统计总用户数
            cursor = await db.execute("SELECT COUNT(*) FROM following_list")
            total_count = (await cursor.fetchone())[0]
            
            # 统计已有等级的用户数
            cursor = await db.execute("""
                SELECT COUNT(*) FROM following_list 
                WHERE level > 0
            """)
            with_level_count = (await cursor.fetchone())[0]
            
            return {
                "total": total_count,
                "with_level": with_level_count,
                "need_fix": need_fix_count,
                "progress_percent": (with_level_count / total_count) * 100 if total_count > 0 else 0
            }

    async def start_fix(self):
        """开始等级修复任务"""
        print("=" * 60)
        print("🔧 智能等级修复工具")
        print("=" * 60)
        
        # 检查当前状态
        status = await self.check_current_status()
        print(f"📊 当前状态:")
        print(f"  - 总用户数: {status['total']}")
        print(f"  - 已有等级: {status['with_level']}")
        print(f"  - 需要修复: {status['need_fix']}")
        print(f"  - 完成进度: {status['progress_percent']:.1f}%")
        
        if status['need_fix'] == 0:
            print("✅ 所有用户都已有等级信息，无需修复！")
            return
        
        # 加载之前的进度
        progress = await self.load_progress()
        processed_count = len(progress["processed_uids"])
        
        if processed_count > 0:
            print(f"\n📂 发现之前的进度记录，已处理 {processed_count} 个用户")
            print(f"  - 连续失败次数: {progress['consecutive_failures']}")
            print(f"  - 当前延迟: {progress['current_delay']}秒")
        
        # 获取需要处理的用户列表
        users_to_fix = await self.get_users_to_fix(progress["processed_uids"])
        
        if not users_to_fix:
            print("✅ 没有新的用户需要修复等级！")
            return
        
        print(f"\n🎯 准备修复 {len(users_to_fix)} 个用户的等级信息")
        print("💡 提示: 遇到API限制时会自动增加延迟，按 Ctrl+C 可安全退出")
        
        # 等待用户确认
        try:
            input("\n按回车键开始修复，或 Ctrl+C 退出...")
        except KeyboardInterrupt:
            print("\n❌ 用户取消操作")
            return
        
        # 开始修复
        api = await get_bilibili_api()
        start_time = time.time()
        success_count = 0
        error_count = 0
        consecutive_failures = progress["consecutive_failures"]
        current_delay = progress["current_delay"]
        
        print(f"\n🚀 开始等级修复...")
        
        try:
            for i, (uid, uname) in enumerate(users_to_fix, 1):
                print(f"[{i}/{len(users_to_fix)}] 正在修复: {uname} (UID: {uid})")
                
                # 检查连续失败次数
                if consecutive_failures >= self.max_consecutive_failures:
                    wait_time = min(current_delay * (self.failure_backoff ** consecutive_failures), self.max_delay)
                    print(f"⚠️  连续失败 {consecutive_failures} 次，暂停 {wait_time:.1f} 秒...")
                    await asyncio.sleep(wait_time)
                    consecutive_failures = 0  # 重置计数
                
                # 尝试修复用户等级
                success, level, error = await self.fix_user_level(api, uid, uname)
                
                if success:
                    success_count += 1
                    consecutive_failures = 0
                    current_delay = self.base_delay  # 重置延迟
                    print(f"✅ 成功: {uname} -> 等级 {level}")
                    
                    # 记录成功处理的用户
                    progress["processed_uids"].append(uid)
                    progress["consecutive_failures"] = 0
                    progress["current_delay"] = current_delay
                    progress["last_success_time"] = datetime.now().isoformat()
                    
                else:
                    error_count += 1
                    consecutive_failures += 1
                    current_delay = min(current_delay * self.failure_backoff, self.max_delay)
                    print(f"❌ 失败: {uname} - {error}")
                    
                    progress["consecutive_failures"] = consecutive_failures
                    progress["current_delay"] = current_delay
                
                # 保存进度（每10个用户保存一次）
                if i % 10 == 0:
                    await self.save_progress(progress)
                    print(f"📈 进度保存: {i}/{len(users_to_fix)}, 成功: {success_count}, 失败: {error_count}")
                
                # 正常延迟
                delay = random.uniform(current_delay, current_delay + 2)
                await asyncio.sleep(delay)
                
        except KeyboardInterrupt:
            print(f"\n⏸️  用户中断操作，进度已保存")
            await self.save_progress(progress)
            return
        
        # 最终保存进度
        await self.save_progress(progress)
        
        # 输出总结
        end_time = time.time()
        duration = end_time - start_time
        duration_str = f"{int(duration // 60)}分{int(duration % 60)}秒"
        
        print(f"\n" + "=" * 60)
        print("🎉 等级修复任务完成！")
        print("=" * 60)
        print(f"⏱️  耗时: {duration_str}")
        print(f"✅ 成功修复: {success_count} 个")
        print(f"❌ 修复失败: {error_count} 个")
        print(f"📁 总计处理: {len(progress['processed_uids'])} 个用户")
        
        # 最终状态检查
        final_status = await self.check_current_status()
        print(f"\n📊 最终状态:")
        print(f"  - 仍需修复: {final_status['need_fix']} 个")
        print(f"  - 完成进度: {final_status['progress_percent']:.1f}%")
        
        if final_status['need_fix'] > 0:
            print(f"\n💡 提示: 还有 {final_status['need_fix']} 个用户需要修复")
            print("  可以稍后重新运行此脚本继续修复")
        else:
            print("\n🎊 所有用户等级修复完成！")

async def main():
    fixer = LevelFixResumer()
    await fixer.start_fix()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 程序已安全退出") 