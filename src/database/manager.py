# -*- coding: utf-8 -*-
"""
数据库管理模块
Database Management Module

负责SQLite数据库的连接、表创建和数据操作
"""

import sqlite3
import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from ..core.config import get_config_value
from ..core.logger import get_logger


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.db_path = get_config_value("database.path", "data/bilibili.db")
        self.logger = get_logger()
        self._connection: Optional[aiosqlite.Connection] = None
        
    async def initialize(self):
        """初始化数据库"""
        try:
            # 确保数据库目录存在
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建数据库连接
            self._connection = await aiosqlite.connect(self.db_path)
            
            # 创建必要的表
            await self._create_tables()
            
            self.logger.info("数据库初始化完成")
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭数据库连接"""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def _create_tables(self):
        """创建数据库表"""
        # 关注列表表
        await self._connection.execute('''
            CREATE TABLE IF NOT EXISTS following_list (
                uid INTEGER PRIMARY KEY,
                uname TEXT NOT NULL,
                face TEXT,
                sign TEXT,
                level INTEGER DEFAULT 0,
                vip_type INTEGER DEFAULT 0,
                vip_status INTEGER DEFAULT 0,
                official_type INTEGER DEFAULT 0,
                official_title TEXT,
                category TEXT DEFAULT '',
                follow_time INTEGER,
                mtime INTEGER,
                tags TEXT,
                group_id INTEGER DEFAULT 0,
                special_attention INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 观看历史表
        await self._connection.execute('''
            CREATE TABLE IF NOT EXISTS watch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                watch_time INTEGER NOT NULL,
                progress INTEGER DEFAULT 0,
                duration INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uid) REFERENCES following_list (uid)
            )
        ''')
        
        # 分组信息表
        await self._connection.execute('''
            CREATE TABLE IF NOT EXISTS follow_groups (
                group_id INTEGER PRIMARY KEY,
                group_name TEXT NOT NULL,
                group_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # UP主统计表
        await self._connection.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                uid INTEGER PRIMARY KEY,
                fans_count INTEGER DEFAULT 0,
                following_count INTEGER DEFAULT 0,
                video_count INTEGER DEFAULT 0,
                total_views INTEGER DEFAULT 0,
                last_video_time INTEGER DEFAULT 0,
                activity_score REAL DEFAULT 0.0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uid) REFERENCES following_list (uid)
            )
        ''')
        
        # 数据同步记录表
        await self._connection.execute('''
            CREATE TABLE IF NOT EXISTS sync_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                total_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await self._connection.commit()
        
        # 创建索引
        await self._create_indexes()
    
    async def _create_indexes(self):
        """创建数据库索引"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_following_category ON following_list(category)",
            "CREATE INDEX IF NOT EXISTS idx_following_follow_time ON following_list(follow_time)",
            "CREATE INDEX IF NOT EXISTS idx_following_group_id ON following_list(group_id)",
            "CREATE INDEX IF NOT EXISTS idx_watch_uid ON watch_history(uid)",
            "CREATE INDEX IF NOT EXISTS idx_watch_time ON watch_history(watch_time)",
            "CREATE INDEX IF NOT EXISTS idx_sync_type ON sync_records(sync_type)",
            "CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_records(status)"
        ]
        
        for index_sql in indexes:
            await self._connection.execute(index_sql)
        
        await self._connection.commit()
    
    async def insert_following_user(self, user_data: Dict[str, Any]) -> bool:
        """插入或更新关注用户"""
        try:
            # 数据验证 - 优先使用uid，如果没有则使用mid
            uid = user_data.get('uid') or user_data.get('mid')
            if not uid:
                self.logger.warning(f"跳过无效用户：缺少UID/MID，用户数据: {user_data}")
                return False
            
            # 确保UID是有效的数字
            try:
                uid = int(uid)
                if uid <= 0:
                    self.logger.warning(f"跳过无效用户：UID无效 ({uid})，用户数据: {user_data}")
                    return False
            except (ValueError, TypeError):
                self.logger.warning(f"跳过无效用户：UID格式错误 ({uid})，用户数据: {user_data}")
                return False
            
            # 统一使用uid字段
            user_data['uid'] = uid
            
            # 检查是否已存在
            cursor = await self._connection.execute(
                "SELECT uid FROM following_list WHERE uid = ?", (uid,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # 如果已存在，更新数据（而不是替换）
                sql = '''
                    UPDATE following_list 
                    SET uname = ?, face = ?, sign = ?, level = ?, vip_type = ?, vip_status = ?, 
                        official_type = ?, official_title = ?, category = ?, follow_time = ?, 
                        mtime = ?, tags = ?, group_id = ?, special_attention = ?, updated_at = ?
                    WHERE uid = ?
                '''
                
                await self._connection.execute(sql, (
                    user_data.get('uname', ''),
                    user_data.get('face', ''),
                    user_data.get('sign', ''),
                    user_data.get('level', 0),
                    user_data.get('vip', {}).get('vipType', 0),  # B站API使用vipType
                    user_data.get('vip', {}).get('vipStatus', 0),  # B站API使用vipStatus
                    user_data.get('official_verify', {}).get('type', 0),  # B站API使用official_verify
                    user_data.get('official_verify', {}).get('desc', ''),  # B站API使用desc而不是title
                    user_data.get('category', ''),
                    user_data.get('mtime', 0),
                    user_data.get('mtime', 0),
                    json.dumps(user_data.get('tag', []), ensure_ascii=False),
                    user_data.get('group_id', 0),  # 使用处理后的group_id
                    user_data.get('special', 0),
                    datetime.now().isoformat(),
                    uid
                ))
            else:
                # 如果不存在，插入新记录
                sql = '''
                    INSERT INTO following_list 
                    (uid, uname, face, sign, level, vip_type, vip_status, 
                     official_type, official_title, category, follow_time, 
                     mtime, tags, group_id, special_attention, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
                
                await self._connection.execute(sql, (
                    uid,
                    user_data.get('uname', ''),
                    user_data.get('face', ''),
                    user_data.get('sign', ''),
                    user_data.get('level', 0),
                    user_data.get('vip', {}).get('vipType', 0),  # B站API使用vipType
                    user_data.get('vip', {}).get('vipStatus', 0),  # B站API使用vipStatus
                    user_data.get('official_verify', {}).get('type', 0),  # B站API使用official_verify
                    user_data.get('official_verify', {}).get('desc', ''),  # B站API使用desc而不是title
                    user_data.get('category', ''),
                    user_data.get('mtime', 0),
                    user_data.get('mtime', 0),
                    json.dumps(user_data.get('tag', []), ensure_ascii=False),
                    user_data.get('attribute', 0),
                    user_data.get('special', 0),
                    datetime.now().isoformat()
                ))
            
            await self._connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"插入关注用户失败: {e}")
            return False
    
    async def get_following_list(self, limit: int = None, offset: int = 0, 
                                 category: str = None, search: str = None, 
                                 sort_by: str = "follow_time", sort_order: str = "desc") -> List[Dict[str, Any]]:
        """获取关注列表"""
        try:
            sql = "SELECT * FROM following_list WHERE 1=1"
            params = []
            
            if category:
                sql += " AND category = ?"
                params.append(category)
            
            if search:
                sql += " AND (uname LIKE ? OR sign LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            
            # 排序逻辑
            valid_sort_fields = {
                "follow_time": "follow_time",
                "uname": "uname",
                "level": "level", 
                "vip_type": "vip_type",
                "category": "category",
                "created_at": "created_at"
            }
            
            if sort_by in valid_sort_fields:
                sort_field = valid_sort_fields[sort_by]
                order = "DESC" if sort_order.lower() == "desc" else "ASC"
                sql += f" ORDER BY {sort_field} {order}"
            else:
                sql += " ORDER BY follow_time DESC"
            
            if limit:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor = await self._connection.execute(sql, params)
            rows = await cursor.fetchall()
            
            # 转换为字典列表
            columns = [description[0] for description in cursor.description]
            result = []
            for row in rows:
                user_dict = dict(zip(columns, row))
                # 解析tags字段
                if user_dict.get('tags'):
                    try:
                        user_dict['tags'] = json.loads(user_dict['tags'])
                    except:
                        user_dict['tags'] = []
                result.append(user_dict)
            
            return result
        except Exception as e:
            self.logger.error(f"获取关注列表失败: {e}")
            return []
    
    async def get_following_count(self, category: str = None) -> int:
        """获取关注数量"""
        try:
            sql = "SELECT COUNT(*) FROM following_list WHERE 1=1"
            params = []
            
            if category:
                sql += " AND category = ?"
                params.append(category)
            
            cursor = await self._connection.execute(sql, params)
            row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            self.logger.error(f"获取关注数量失败: {e}")
            return 0
    
    async def get_categories_stats(self) -> List[Dict[str, Any]]:
        """获取分类统计"""
        try:
            sql = '''
                SELECT category, COUNT(*) as count 
                FROM following_list 
                GROUP BY category 
                ORDER BY count DESC
            '''
            
            cursor = await self._connection.execute(sql)
            rows = await cursor.fetchall()
            
            return [{"category": row[0], "count": row[1]} for row in rows]
        except Exception as e:
            self.logger.error(f"获取分类统计失败: {e}")
            return []
    
    async def get_follow_groups(self) -> List[Dict[str, Any]]:
        """获取关注分组列表，包含实际用户数量"""
        try:
            sql = '''
                SELECT g.group_id, g.group_name, g.group_count, g.created_at, g.updated_at,
                       COALESCE(actual_counts.actual_count, 0) as actual_count
                FROM follow_groups g
                LEFT JOIN (
                    SELECT group_id, COUNT(*) as actual_count
                    FROM following_list 
                    WHERE group_id IS NOT NULL AND group_id > 0
                    GROUP BY group_id
                ) actual_counts ON g.group_id = actual_counts.group_id
                ORDER BY g.group_id
            '''
            
            cursor = await self._connection.execute(sql)
            rows = await cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            groups = [dict(zip(columns, row)) for row in rows]
            
            # 添加未分组用户统计（作为特殊分组）
            ungrouped_count = await self.get_following_count_by_group(0)
            if ungrouped_count > 0:
                groups.insert(0, {
                    'group_id': 0,
                    'group_name': '未分组',
                    'group_count': ungrouped_count,
                    'actual_count': ungrouped_count,
                    'created_at': None,
                    'updated_at': None
                })
            
            self.logger.debug(f"获取到 {len(groups)} 个分组，未分组用户 {ungrouped_count} 个")
            return groups
        except Exception as e:
            self.logger.error(f"获取关注分组失败: {e}")
            return []
    
    async def insert_or_update_follow_group(self, group_id: int, group_name: str, group_count: int = 0) -> bool:
        """插入或更新关注分组"""
        try:
            # 检查是否已存在
            cursor = await self._connection.execute(
                "SELECT group_id FROM follow_groups WHERE group_id = ?", (group_id,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # 更新现有分组
                sql = '''
                    UPDATE follow_groups 
                    SET group_name = ?, group_count = ?, updated_at = ?
                    WHERE group_id = ?
                '''
                await self._connection.execute(sql, (
                    group_name, group_count, datetime.now().isoformat(), group_id
                ))
            else:
                # 插入新分组
                sql = '''
                    INSERT INTO follow_groups (group_id, group_name, group_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                '''
                now = datetime.now().isoformat()
                await self._connection.execute(sql, (
                    group_id, group_name, group_count, now, now
                ))
            
            await self._connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"插入或更新分组失败: {e}")
            return False
    
    async def update_user_group(self, uid: int, group_id: int) -> bool:
        """更新用户分组"""
        try:
            sql = '''
                UPDATE following_list 
                SET group_id = ?, updated_at = ?
                WHERE uid = ?
            '''
            await self._connection.execute(sql, (
                group_id, datetime.now().isoformat(), uid
            ))
            await self._connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"更新用户分组失败: {e}")
            return False
    
    async def get_following_by_group(self, group_id: int = None, limit: int = None, offset: int = 0,
                                    search: str = None, sort_by: str = "follow_time", 
                                    sort_order: str = "desc") -> List[Dict[str, Any]]:
        """按分组获取关注列表"""
        try:
            sql = "SELECT * FROM following_list WHERE 1=1"
            params = []
            
            if group_id is not None:
                if group_id == 0:
                    # 未分组用户：group_id为0或NULL
                    sql += " AND (group_id = 0 OR group_id IS NULL)"
                else:
                    sql += " AND group_id = ?"
                    params.append(group_id)
            
            if search:
                sql += " AND (uname LIKE ? OR sign LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            
            # 排序逻辑
            valid_sort_fields = {
                "follow_time": "follow_time",
                "uname": "uname",
                "level": "level", 
                "vip_type": "vip_type",
                "category": "category",
                "created_at": "created_at"
            }
            
            if sort_by in valid_sort_fields:
                sort_field = valid_sort_fields[sort_by]
                order = "DESC" if sort_order.lower() == "desc" else "ASC"
                sql += f" ORDER BY {sort_field} {order}"
            else:
                sql += " ORDER BY follow_time DESC"
            
            if limit:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor = await self._connection.execute(sql, params)
            rows = await cursor.fetchall()
            
            # 转换为字典列表
            columns = [description[0] for description in cursor.description]
            result = []
            for row in rows:
                user_dict = dict(zip(columns, row))
                # 解析tags字段
                if user_dict.get('tags'):
                    try:
                        user_dict['tags'] = json.loads(user_dict['tags'])
                    except:
                        user_dict['tags'] = []
                result.append(user_dict)
            
            return result
        except Exception as e:
            self.logger.error(f"按分组获取关注列表失败: {e}")
            return []
    
    async def get_following_count_by_group(self, group_id: int = None) -> int:
        """获取指定分组的关注数量"""
        try:
            sql = "SELECT COUNT(*) FROM following_list WHERE 1=1"
            params = []
            
            if group_id is not None:
                if group_id == 0:
                    # 未分组用户：group_id为0或NULL
                    sql += " AND (group_id = 0 OR group_id IS NULL)"
                else:
                    sql += " AND group_id = ?"
                    params.append(group_id)
            
            cursor = await self._connection.execute(sql, params)
            row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            self.logger.error(f"获取分组关注数量失败: {e}")
            return 0
    
    async def update_user_category(self, uid: int, category: str) -> bool:
        """更新用户分类"""
        try:
            sql = "UPDATE following_list SET category = ?, updated_at = ? WHERE uid = ?"
            await self._connection.execute(sql, (category, datetime.now().isoformat(), uid))
            await self._connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"更新用户分类失败: {e}")
            return False
    
    async def batch_unfollow(self, uids: List[int]) -> Tuple[int, int]:
        """批量取消关注"""
        success_count = 0
        error_count = 0
        
        for uid in uids:
            try:
                await self._connection.execute("DELETE FROM following_list WHERE uid = ?", (uid,))
                success_count += 1
            except Exception as e:
                self.logger.error(f"删除用户 {uid} 失败: {e}")
                error_count += 1
        
        await self._connection.commit()
        return success_count, error_count
    
    async def insert_sync_record(self, sync_type: str, total_count: int = 0) -> int:
        """插入同步记录"""
        try:
            sql = '''
                INSERT INTO sync_records (sync_type, start_time, total_count)
                VALUES (?, ?, ?)
            '''
            cursor = await self._connection.execute(sql, (
                sync_type, datetime.now().isoformat(), total_count
            ))
            await self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"插入同步记录失败: {e}")
            return 0
    
    async def update_sync_record(self, record_id: int, success_count: int = 0, 
                                error_count: int = 0, status: str = "completed", 
                                error_message: str = None) -> bool:
        """更新同步记录"""
        try:
            sql = '''
                UPDATE sync_records 
                SET end_time = ?, success_count = ?, error_count = ?, 
                    status = ?, error_message = ?
                WHERE id = ?
            '''
            await self._connection.execute(sql, (
                datetime.now().isoformat(), success_count, error_count,
                status, error_message, record_id
            ))
            await self._connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"更新同步记录失败: {e}")
            return False 