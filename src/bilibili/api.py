# -*- coding: utf-8 -*-
"""
哔哩哔哩API接口模块
Bilibili API Interface Module

封装哔哩哔哩相关的API接口调用
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlencode

from ..core.config import get_config_value
from ..core.logger import get_logger
from .analyzer import FollowingAnalyzer
from ..database.manager import DatabaseManager


class BilibiliAPI:
    """哔哩哔哩API客户端"""
    
    def __init__(self):
        self.logger = get_logger()
        self.cookie = get_config_value("bilibili.cookie", "")
        self.user_agent = get_config_value("bilibili.user_agent", "")
        self.api_delay = get_config_value("bilibili.api_delay", 1.0)
        self.retry_times = get_config_value("bilibili.retry_times", 8)  # 增加重试次数以应对频率限制
        self.timeout = get_config_value("bilibili.timeout", 30)
        self.fetch_user_details = get_config_value("bilibili.fetch_user_details", True)
        
        # 错误计数器，用于合并重复的错误日志
        self._error_counters = {}
        self._last_error_log_time = {}
        
        # API端点
        self.endpoints = {
            "following_list": "https://api.bilibili.com/x/relation/followings",
            "user_info": "https://api.bilibili.com/x/web-interface/card",
            "user_stat": "https://api.bilibili.com/x/relation/stat",
            "modify_relation": "https://api.bilibili.com/x/relation/modify",
            "follow_groups": "https://api.bilibili.com/x/relation/tags",
            "batch_modify": "https://api.bilibili.com/x/relation/batch/modify",
            "move_to_group": "https://api.bilibili.com/x/relation/tags/addUsers",
            "user_videos": "https://api.bilibili.com/x/space/arc/search",
            "video_info": "https://api.bilibili.com/x/web-interface/view"
        }
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取HTTP会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": self.user_agent,
                    "Referer": "https://www.bilibili.com",
                    "Cookie": self.cookie
                }
            )
        return self._session
    
    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """发送HTTP请求"""
        session = await self._get_session()
        
        for attempt in range(self.retry_times):
            try:
                async with session.request(method, url, **kwargs) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 0:
                            return data.get("data", {})
                        else:
                            error_code = data.get('code')
                            error_msg = data.get('message', '未知错误')
                            
                            # 对特定错误代码进行特殊处理
                            if error_code == -352:
                                # 风控限制计数
                                if not hasattr(self, '_wind_control_count'):
                                    self._wind_control_count = 0
                                self._wind_control_count += 1
                                
                                # 根据风控次数调整等待时间
                                if self._wind_control_count <= 5:
                                    wait_time = 10
                                elif self._wind_control_count <= 15:
                                    wait_time = 30
                                elif self._wind_control_count <= 30:
                                    wait_time = 60
                                else:
                                    wait_time = 120  # 最长等待2分钟
                                
                                self._log_error_with_counter(f"wind_control_{error_code}", 
                                    f"遇到风控限制 (-352)，第{self._wind_control_count}次，等待{wait_time}秒后重试", "error")
                                
                                # 如果风控次数过多，考虑暂停更长时间
                                if self._wind_control_count > 50:
                                    self.logger.warning(f"风控限制过于频繁({self._wind_control_count}次)，建议暂停任务检查Cookie状态")
                                    # 可以在这里抛出特殊异常来通知上层暂停任务
                                    
                                await asyncio.sleep(wait_time)
                                continue  # 重试
                            elif error_code == -503 or error_code == -799 or "频繁" in error_msg:
                                wait_time = 5 + attempt * 2  # 递增等待时间
                                self._log_error_with_counter(f"rate_limit_{error_code}", 
                                    f"API调用过于频繁，等待 {wait_time} 秒后重试", "warning")
                                await asyncio.sleep(wait_time)
                                continue  # 重试
                            elif error_code in [-101, -102]:
                                self._log_error_with_counter(f"auth_error_{error_code}", 
                                    "账号登录状态异常，请检查Cookie", "error")
                                return None
                            else:
                                # 其他错误不重试
                                self._log_error_with_counter(f"api_error_{error_code}", 
                                    f"API返回错误: {error_msg} (code: {error_code})", "warning")
                                return None
                    else:
                        self.logger.warning(f"HTTP错误: {response.status}")
                        response_text = await response.text()
                        self.logger.debug(f"HTTP响应内容: {response_text[:500]}")
                        
            except Exception as e:
                self.logger.error(f"请求失败 (尝试 {attempt + 1}/{self.retry_times}): {e}")
                if attempt < self.retry_times - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
        
        return None
    
    async def get_following_list(self, pn: int = 1, ps: int = 50, 
                                order: str = "desc") -> Optional[Dict[str, Any]]:
        """获取关注列表"""
        params = {
            "vmid": await self._get_current_uid(),
            "pn": pn,
            "ps": ps,
            "order": order,
            "order_type": "attention"
        }
        
        url = f"{self.endpoints['following_list']}?{urlencode(params)}"
        
        self.logger.info(f"获取关注列表 - 页码: {pn}, 每页: {ps}")
        result = await self._request("GET", url)
        
        # 添加API延迟
        await asyncio.sleep(self.api_delay)
        
        return result
    
    async def get_all_following(self, progress_callback=None, fetch_user_details=None) -> List[Dict[str, Any]]:
        """获取所有关注用户
        
        Args:
            progress_callback: 进度回调函数
            fetch_user_details: 是否获取用户详细信息（包括等级），如果为None则使用配置文件设置
        """
        if fetch_user_details is None:
            fetch_user_details = self.fetch_user_details
            
        all_following = []
        page = 1
        page_size = 50
        invalid_users = 0
        
        self.logger.info(f"开始获取关注列表，获取用户详细信息: {'开启' if fetch_user_details else '关闭'}")
        
        while True:
            data = await self.get_following_list(pn=page, ps=page_size)
            if not data or not data.get("list"):
                break
            
            following_list = data.get("list", [])
            
            # 过滤有效用户数据
            valid_users = []
            for user in following_list:
                if self._validate_user_data(user):
                    valid_users.append(user)
                else:
                    invalid_users += 1
                    self.logger.warning(f"发现无效用户数据: {user}")
            
            # 批量获取用户详细信息
            if fetch_user_details and valid_users:
                valid_users = await self._batch_enrich_user_info(valid_users)
            
            all_following.extend(valid_users)
            
            # 调用进度回调
            if progress_callback:
                total = data.get("total", 0)
                current = len(all_following)
                progress_callback(current, total)
            
            # 检查是否还有更多数据
            if len(following_list) < page_size:
                break
            
            page += 1
            self.logger.info(f"已获取 {len(all_following)} 个关注用户")
        
        self.logger.info(f"获取关注列表完成，总计: {len(all_following)} 个用户，跳过无效用户: {invalid_users}")
        return all_following
    
    async def _batch_enrich_user_info(self, users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量获取用户详细信息以补充等级等字段（优化版）"""
        analyzer = FollowingAnalyzer()
        
        enriched_users = []
        consecutive_failures = 0
        base_delay = 0.5
        max_concurrent = 5  # 并发限制
        
        # 分批处理以控制并发
        batch_size = max_concurrent
        for i in range(0, len(users), batch_size):
            batch = users[i:i + batch_size]
            
            # 并发获取这一批用户的详细信息
            tasks = []
            for user in batch:
                uid = user.get('uid') or user.get('mid')
                if uid:
                    tasks.append(self._enrich_single_user(user, uid, analyzer))
            
            # 等待这一批完成
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    self.logger.warning(f"获取用户详细信息失败: {result}")
                    enriched_users.append(batch[j])  # 使用原始数据
                    consecutive_failures += 1
                elif result:
                    enriched_users.append(result)
                    consecutive_failures = 0
                else:
                    enriched_users.append(batch[j])  # 使用原始数据
                    consecutive_failures += 1
            
            # 如果连续失败次数过多，增加延迟
            if consecutive_failures >= 3:
                delay = min(base_delay * (consecutive_failures - 2), 10)
                self.logger.warning(f"连续 {consecutive_failures} 次失败，等待 {delay:.1f} 秒")
                await asyncio.sleep(delay)
            else:
                # 正常的批次间延迟
                await asyncio.sleep(base_delay)
            
            # 记录进度
            self.logger.info(f"已处理 {len(enriched_users)}/{len(users)} 个用户详细信息")
        
        self.logger.info(f"批量获取用户详细信息完成，共处理 {len(enriched_users)} 个用户")
        return enriched_users
    
    async def _enrich_single_user(self, user: Dict[str, Any], uid: int, analyzer) -> Optional[Dict[str, Any]]:
        """获取单个用户的详细信息并进行智能分类（边同步边分类优化）"""
        try:
            # 获取用户详细信息
            user_info = await self.get_user_info(uid)
            if not user_info:
                # 进行基础分类，即使没有获取到详细信息
                category = analyzer.classify_user(user)
                user["category"] = category
                return user
            
            # 更新用户信息
            if 'data' in user_info:
                card_info = user_info['data'].get('card', {})
            elif 'card' in user_info:
                card_info = user_info['card']
            else:
                card_info = {}
            
            # 更新字段
            if card_info.get('face'):
                user['face'] = card_info['face']
            if card_info.get('sign'):
                user['sign'] = card_info['sign']
            
            # 获取等级信息
            level_info = card_info.get('level_info', {})
            if level_info:
                user['level'] = level_info.get('current_level', 0)
            
            # 获取VIP信息
            vip_info = card_info.get('vip', {})
            if vip_info:
                user['vip_type'] = vip_info.get('vipType', 0)
                user['vip_status'] = vip_info.get('vipStatus', 0)
            
            # 获取认证信息
            official_info = card_info.get('official', {})
            if official_info:
                user['official_type'] = official_info.get('type', 0)
                user['official_title'] = official_info.get('title', '')
            
            # 边同步边分类 - 立即计算分类
            category = analyzer.classify_user(user)
            user["category"] = category
            
            return user
            
        except Exception as e:
            self.logger.debug(f"获取用户 {uid} 详细信息失败: {e}")
            # 即使失败也进行分类
            category = analyzer.classify_user(user)
            user["category"] = category
            return user
    
    async def unfollow_user(self, uid: int) -> bool:
        """取消关注用户"""
        data = {
            "fid": uid,
            "act": 2,  # 取消关注
            "re_src": 11,
            "csrf": self._extract_csrf_token()
        }
        
        result = await self._request("POST", self.endpoints["modify_relation"], data=data)
        await asyncio.sleep(self.api_delay)
        
        if result is not None:
            self.logger.info(f"成功取消关注用户: {uid}")
            return True
        else:
            self.logger.warning(f"取消关注用户失败: {uid}")
            return False
    
    async def get_follow_groups(self) -> Optional[List[Dict[str, Any]]]:
        """获取关注分组列表"""
        result = await self._request("GET", self.endpoints["follow_groups"])
        await asyncio.sleep(self.api_delay)
        
        if result is not None:
            groups = result if isinstance(result, list) else []
            self.logger.info(f"获取到 {len(groups)} 个关注分组")
            return groups
        else:
            self.logger.warning("获取关注分组失败")
            return None
    
    async def modify_user_group(self, uid: int, group_id: int) -> bool:
        """修改用户分组"""
        data = {
            "fids": str(uid),
            "tagids": str(group_id),
            "csrf": self._extract_csrf_token()
        }
        
        # 添加详细的调试日志
        self.logger.debug(f"修改分组API请求 - URL: {self.endpoints['move_to_group']}")
        self.logger.debug(f"修改分组API请求 - 数据: {data}")
        
        # 使用正确的移动到分组API端点
        result = await self._request("POST", self.endpoints["move_to_group"], data=data)
        await asyncio.sleep(self.api_delay)
        
        if result is not None:
            self.logger.info(f"成功修改用户 {uid} 的分组为 {group_id}")
            return True
        else:
            self.logger.warning(f"修改用户 {uid} 分组失败")
            return False
    
    async def create_follow_group(self, group_name: str) -> Optional[int]:
        """创建关注分组（注意：此API可能需要特殊权限）"""
        # 注意：B站可能不允许通过API创建新分组，这里仅作预留
        self.logger.warning("创建关注分组功能可能需要特殊权限")
        return None
    
    async def batch_unfollow_users(self, uids: List[int]) -> Tuple[int, int]:
        """批量取消关注用户
        
        Returns:
            Tuple[int, int]: (成功数量, 失败数量)
        """
        success_count = 0
        error_count = 0
        
        for uid in uids:
            try:
                if await self.unfollow_user(uid):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                self.logger.error(f"批量取消关注用户 {uid} 时出错: {e}")
                error_count += 1
        
        self.logger.info(f"批量取消关注完成: 成功 {success_count}, 失败 {error_count}")
        return success_count, error_count
    
    def _extract_csrf_token(self) -> str:
        """从Cookie中提取CSRF令牌"""
        if not self.cookie:
            return ""
        
        # 查找bili_jct值
        for item in self.cookie.split(";"):
            if "bili_jct=" in item:
                return item.split("bili_jct=")[1].strip()
        
        return ""
    
    async def _get_current_uid(self) -> int:
        """获取当前用户UID"""
        # 从Cookie中提取DedeUserID
        if not self.cookie:
            return 0
        
        for item in self.cookie.split(";"):
            if "DedeUserID=" in item:
                try:
                    return int(item.split("DedeUserID=")[1].strip())
                except ValueError:
                    pass
        
        return 0
    
    def _validate_user_data(self, user_data: Dict[str, Any]) -> bool:
        """验证用户数据完整性"""
        # B站API返回的是mid字段，需要映射为uid
        mid = user_data.get('mid')
        if not mid:
            return False
        
        # 检查MID格式
        try:
            mid = int(mid)
            if mid <= 0:
                return False
        except (ValueError, TypeError):
            return False
        
        # 检查用户名
        uname = user_data.get('uname', '').strip()
        if not uname or uname == '':
            return False
        
        # 将mid映射为uid，保持数据一致性
        user_data['uid'] = mid
        
        return True
    
    def is_configured(self) -> bool:
        """检查是否已配置Cookie"""
        return bool(self.cookie and self._extract_csrf_token())

    async def get_user_info(self, uid: int) -> Optional[Dict[str, Any]]:
        """获取用户详细信息"""
        params = {
            "mid": uid
        }
        
        url = f"{self.endpoints['user_info']}?{urlencode(params)}"
        
        self.logger.debug(f"获取用户详细信息 - UID: {uid}")
        result = await self._request("GET", url)
        
        # 添加API延迟
        await asyncio.sleep(self.api_delay)
        
        return result

    async def get_user_videos(self, uid: int, pn: int = 1, ps: int = 30) -> Optional[Dict[str, Any]]:
        """获取用户视频列表"""
        params = {
            "mid": uid,
            "pn": pn,  # 页码
            "ps": ps,  # 每页数量
            "order": "pubdate",  # 按发布时间排序
        }
        
        url = f"{self.endpoints['user_videos']}?{urlencode(params)}"
        
        self.logger.debug(f"获取用户视频列表 - UID: {uid}, 页码: {pn}")
        
        # 绕过_request方法的数据过滤，直接处理完整响应
        session = await self._get_session()
        
        for attempt in range(self.retry_times):
            try:
                async with session.request("GET", url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 0:
                            # 添加API延迟
                            await asyncio.sleep(self.api_delay)
                            return data  # 返回完整响应而不是只返回data字段
                        else:
                            error_code = data.get('code')
                            error_msg = data.get('message', '未知错误')
                            
                            # 对特定错误代码进行特殊处理
                            if error_code == -503 or error_code == -799 or "频繁" in error_msg:
                                wait_time = 5 + attempt * 2
                                self._log_error_with_counter(f"rate_limit_videos_{error_code}", 
                                    f"视频API调用过于频繁，等待 {wait_time} 秒后重试", "warning")
                                await asyncio.sleep(wait_time)
                                continue  # 重试
                            else:
                                self._log_error_with_counter(f"video_api_error_{error_code}", 
                                    f"视频API返回错误: {error_msg} (code: {error_code})", "warning")
                                return None
                    else:
                        self.logger.warning(f"视频API HTTP错误: {response.status}")
                        if attempt < self.retry_times - 1:
                            await asyncio.sleep(2 ** attempt)
                        
            except Exception as e:
                self.logger.error(f"视频API请求失败 (尝试 {attempt + 1}/{self.retry_times}): {e}")
                if attempt < self.retry_times - 1:
                    await asyncio.sleep(2 ** attempt)
        
        return None
    
    async def get_user_stats(self, uid: int) -> Optional[Dict[str, Any]]:
        """获取用户真实统计信息（包括粉丝数、关注数、视频数等）"""
        try:
            # 1. 获取用户基本信息
            user_info = await self.get_user_info(uid)
            if not user_info:
                self.logger.warning(f"用户 {uid} API响应为空")
                return None

            # B站API可能返回不同格式的数据，需要兼容处理
            card_info = {}
            archive_count = 0

            if 'data' in user_info:
                # 格式1: 标准API响应格式
                data = user_info['data']
                if not data:
                    self.logger.warning(f"用户 {uid} 可能不存在或已注销")
                    return None
                card_info = data.get('card', {})
                # 某些情况下可能直接在data中包含archive_count
                if 'archive_count' in data:
                    archive_count = data.get('archive_count', 0)
            elif 'card' in user_info:
                # 格式2: 直接包含card信息的格式
                card_info = user_info.get('card', {})
                archive_count = user_info.get('archive_count', 0)
            else:
                self.logger.warning(f"用户 {uid} 响应格式未知: {list(user_info.keys())}")
                return None

            # 2. 获取用户视频列表（第一页30个视频，用于获取总数和最新视频时间）
            videos_info = await self.get_user_videos(uid, pn=1, ps=30)

            # 提取统计信息
            stats = {
                "uid": uid,
                "fans_count": card_info.get('fans', 0),  # 粉丝数
                "following_count": card_info.get('friend', card_info.get('attention', 0)),  # 关注数，兼容不同字段名
                "video_count": archive_count or card_info.get('archive_count', 0),  # 多来源获取视频数
                "total_views": 0,
                "last_video_time": 0,
                "activity_score": 0.5  # 默认活跃度
            }

            # 处理视频信息
            if videos_info and 'data' in videos_info and videos_info['data']:
                video_data = videos_info['data']

                # 如果之前没有获取到视频数量，从这里获取
                if stats["video_count"] == 0:
                    # 多种方式获取视频总数
                    page_info = video_data.get('page', {})
                    stats["video_count"] = (
                        page_info.get('count', 0) or  # 最常见的字段
                        video_data.get('count', 0) or  # 备选字段
                        len(video_data.get('list', {}).get('vlist', []))  # 最后备选：当前页视频数
                    )

                # 获取视频列表
                vlist = []
                list_data = video_data.get('list', {})
                if isinstance(list_data, dict):
                    vlist = list_data.get('vlist', [])
                elif isinstance(list_data, list):
                    vlist = list_data

                if vlist:
                    latest_video = vlist[0]  # 第一个是最新的
                    stats["last_video_time"] = latest_video.get('created', 0)

                    # 计算总播放量 - 处理前30个视频
                    total_views = 0
                    for video in vlist:
                        play_count = video.get('play', 0)
                        # 处理可能的字符串格式播放量
                        if isinstance(play_count, str):
                            try:
                                play_count = int(play_count)
                            except (ValueError, TypeError):
                                play_count = 0
                        total_views += play_count

                    stats["total_views"] = total_views

                    # 如果当前页有30个视频且总视频数大于30，估算总播放量
                    if len(vlist) == 30 and stats["video_count"] > 30:
                        # 基于当前页的平均播放量估算总播放量
                        avg_views_per_video = total_views / len(vlist)
                        estimated_total_views = avg_views_per_video * stats["video_count"]
                        
                        # 为了保险起见，只在估算值合理的情况下使用
                        if estimated_total_views > total_views:
                            stats["total_views"] = int(estimated_total_views)
                        
                        self.logger.debug(f"用户 {uid} 播放量估算: 当前页{total_views}, 估算总计{estimated_total_views}")

            # 如果无法获取视频列表但有视频数量，使用估算的活跃度
            elif stats["video_count"] > 0:
                # 无法获取最新视频时间，根据视频数量估算活跃度
                if stats["video_count"] > 100:
                    stats["activity_score"] = 0.6  # 高产用户
                elif stats["video_count"] > 20:
                    stats["activity_score"] = 0.4  # 中等产出
                else:
                    stats["activity_score"] = 0.3  # 低产用户

            # 重新计算活跃度分数（基于最后视频时间和视频数量）
            if stats["last_video_time"] > 0:
                import time
                current_time = int(time.time())
                days_since_last = (current_time - stats["last_video_time"]) / (24 * 3600)

                # 基于最后视频时间的基础活跃度
                if days_since_last <= 7:
                    base_activity = 0.9
                elif days_since_last <= 30:
                    base_activity = 0.7
                elif days_since_last <= 90:
                    base_activity = 0.5
                elif days_since_last <= 180:
                    base_activity = 0.3
                else:
                    base_activity = 0.1

                # 根据视频数量调整
                if stats["video_count"] > 200:
                    activity_adjustment = 0.15
                elif stats["video_count"] > 100:
                    activity_adjustment = 0.1
                elif stats["video_count"] > 50:
                    activity_adjustment = 0.05
                elif stats["video_count"] < 10:
                    activity_adjustment = -0.1
                else:
                    activity_adjustment = 0

                # 根据播放量调整（如果有的话）
                if stats["total_views"] > 10000000:  # 1000万以上
                    view_adjustment = 0.1
                elif stats["total_views"] > 1000000:  # 100万以上
                    view_adjustment = 0.05
                else:
                    view_adjustment = 0

                final_activity = base_activity + activity_adjustment + view_adjustment
                stats["activity_score"] = max(0.1, min(0.9, final_activity))

            self.logger.info(f"✅ 用户 {uid} 统计信息获取成功: 粉丝{stats['fans_count']}, 视频{stats['video_count']}, "
                           f"播放量{stats['total_views']}, 最后视频{stats['last_video_time']}, 活跃度{stats['activity_score']}")
            return stats

        except Exception as e:
            self.logger.error(f"获取用户 {uid} 统计信息失败: {e}")
            return None

    def _log_error_with_counter(self, error_key: str, message: str, level: str = "warning"):
        """记录错误日志，如果是重复错误则合并显示"""
        current_time = time.time()
        
        # 更新错误计数
        if error_key not in self._error_counters:
            self._error_counters[error_key] = 0
            self._last_error_log_time[error_key] = 0
        
        self._error_counters[error_key] += 1
        
        # 第一次出现错误或距离上次记录超过30秒时才记录日志
        if (self._error_counters[error_key] == 1 or 
            current_time - self._last_error_log_time[error_key] > 30):
            
            if self._error_counters[error_key] > 1:
                message += f" (已重复 {self._error_counters[error_key]} 次)"
            
            if level == "error":
                self.logger.error(message)
            elif level == "warning":
                self.logger.warning(message)
            else:
                self.logger.info(message)
            
            self._last_error_log_time[error_key] = current_time

    async def get_following_and_groups_combined(self, progress_callback=None, fetch_user_details=None) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """
        优化方法：同时获取关注列表和分组信息
        减少网络往返，提升性能
        
        Returns:
            Tuple[following_list, groups_list]
        """
        if fetch_user_details is None:
            fetch_user_details = self.fetch_user_details
            
        self.logger.info("开始并发获取关注列表和分组信息（优化版）")
        
        # 并发获取分组信息和第一页关注列表
        async def get_groups_task():
            return await self.get_follow_groups()
        
        async def get_first_page_task():
            return await self.get_following_list(pn=1, ps=50)
        
        # 并发执行两个任务
        groups_task = asyncio.create_task(get_groups_task())
        first_page_task = asyncio.create_task(get_first_page_task())
        
        groups_result, first_page_result = await asyncio.gather(
            groups_task, first_page_task, return_exceptions=True
        )
        
        # 处理分组结果
        if isinstance(groups_result, Exception):
            self.logger.warning(f"获取分组信息失败: {groups_result}")
            groups_list = None
        else:
            groups_list = groups_result
            self.logger.info(f"成功获取 {len(groups_list) if groups_list else 0} 个分组信息")
        
        # 处理第一页关注列表结果
        if isinstance(first_page_result, Exception) or not first_page_result:
            self.logger.error(f"获取第一页关注列表失败: {first_page_result}")
            return [], groups_list
        
        # 继续获取剩余页面的关注列表
        all_following = []
        total = first_page_result.get("total", 0)
        first_page_list = first_page_result.get("list", [])
        
        # 处理第一页数据
        if fetch_user_details and first_page_list:
            first_page_list = await self._batch_enrich_user_info(first_page_list)
        all_following.extend(first_page_list)
        
        # 更新进度
        if progress_callback:
            progress_callback(len(all_following), total)
        
        # 继续获取后续页面
        page = 2
        page_size = 50
        
        while len(first_page_list) == page_size:  # 说明可能还有更多页面
            data = await self.get_following_list(pn=page, ps=page_size)
            if not data or not data.get("list"):
                break
            
            following_list = data.get("list", [])
            
            # 过滤有效用户数据
            valid_users = []
            for user in following_list:
                if self._validate_user_data(user):
                    valid_users.append(user)
            
            # 批量获取用户详细信息
            if fetch_user_details and valid_users:
                valid_users = await self._batch_enrich_user_info(valid_users)
            
            all_following.extend(valid_users)
            
            # 调用进度回调
            if progress_callback:
                progress_callback(len(all_following), total)
            
            # 检查是否还有更多数据
            if len(following_list) < page_size:
                break
            
            page += 1
            self.logger.info(f"已获取 {len(all_following)} 个关注用户")
        
        self.logger.info(f"合并获取完成，关注用户: {len(all_following)}, 分组: {len(groups_list) if groups_list else 0}")
        return all_following, groups_list

    async def get_user_stats_batch(self, users: List[Dict[str, Any]],
                                  *,
                                  db_manager: "DatabaseManager",
                                  progress_callback=None,
                                  skip_recent_hours: int = 24) -> List[Tuple[bool, Any]]:
        """
        批量获取用户统计信息（优化版）
        支持跳过最近更新的用户，实现增量更新
        
        Args:
            users: 用户列表
            db_manager: 数据库管理器实例
            progress_callback: 进度回调
            skip_recent_hours: 跳过最近N小时内更新过的用户
        """
        if not users:
            return []
        
        self.logger.info(f"开始批量获取用户统计信息，总计 {len(users)} 个用户")
        
        # 检查数据库中最近更新的用户，实现增量更新
        users_to_update = []
        skipped_count = 0
        
        import time
        cutoff_time = time.time() - (skip_recent_hours * 3600)
        
        for user in users:
            uid = user.get('uid') or user.get('mid')
            if not uid:
                continue
                
            # 检查是否需要跳过（最近已更新）
            try:
                cursor = await db_manager._connection.execute(
                    "SELECT updated_at FROM user_stats WHERE uid = ? AND updated_at > ?",
                    (uid, cutoff_time)
                )
                recent_update = await cursor.fetchone()
                
                if recent_update:
                    skipped_count += 1
                    self.logger.debug(f"跳过用户 {uid}，最近 {skip_recent_hours} 小时内已更新")
                    continue
                    
            except Exception as e:
                self.logger.debug(f"检查用户 {uid} 更新状态失败: {e}")
            
            users_to_update.append(user)
        
        self.logger.info(f"增量更新策略：需要更新 {len(users_to_update)} 个用户，跳过 {skipped_count} 个最近更新的用户")
        
        if not users_to_update:
            return [(True, "skipped")] * len(users)
        
        # 初始化统计计数器
        success_count = 0
        failed_count = 0
        video_api_limited_count = 0
        
        # 分批处理，减少并发压力
        batch_size = 3  # 进一步降低并发数
        results = []
        
        for i in range(0, len(users_to_update), batch_size):
            batch = users_to_update[i:i + batch_size]
            
            # 并发处理当前批次
            tasks = []
            for user in batch:
                uid = user.get('uid') or user.get('mid')
                if uid:
                    tasks.append(self._get_user_stats_optimized(uid))
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理批次结果
            for j, result in enumerate(batch_results):
                uid = batch[j].get('uid') or batch[j].get('mid')
                
                if isinstance(result, Exception):
                    failed_count += 1
                    self.logger.error(f"获取用户 {uid} 统计信息异常: {result}")
                    results.append((False, str(result)))
                elif result:
                    # 检查是否因视频API限制导致缺少详细数据
                    has_video_details = (result.get('total_views', 0) > 0 or 
                                       result.get('last_video_time', 0) > 0)
                    
                    if not has_video_details and result.get('video_count', 0) > 0:
                        video_api_limited_count += 1
                        self.logger.info(f"用户 {uid} 基本信息获取成功，视频详情受API限制影响")
                    
                    # 立即保存到数据库
                    try:
                        await self._save_user_stats_to_db(db_manager, uid, result)
                        success_count += 1
                        results.append((True, result))
                    except Exception as e:
                        failed_count += 1
                        self.logger.error(f"保存用户 {uid} 统计信息到数据库失败: {e}")
                        results.append((False, str(e)))
                else:
                    failed_count += 1
                    results.append((False, "No data"))
            
            # 更新进度
            if progress_callback:
                progress_callback(len(results), len(users_to_update))
            
            # 批次间延迟，减少API压力
            if i + batch_size < len(users_to_update):  # 不是最后一批
                await asyncio.sleep(2.0)  # 增加延迟
        
        # 记录详细的执行结果
        self.logger.info(f"批量统计信息获取完成:")
        self.logger.info(f"  - 成功获取: {success_count}/{len(users_to_update)}")
        self.logger.info(f"  - 获取失败: {failed_count}/{len(users_to_update)}")
        self.logger.info(f"  - 视频API受限: {video_api_limited_count}/{len(users_to_update)}")
        self.logger.info(f"  - 增量跳过: {skipped_count}/{len(users)}")
        
        if video_api_limited_count > 0:
            self.logger.warning(f"注意：{video_api_limited_count} 个用户的视频详情（播放量、发布时间）因API频率限制无法获取")
            self.logger.warning("建议：降低同步频率或分批进行，以避免触发B站API限制")
        
        # 为跳过的用户补充结果
        final_results = []
        update_index = 0
        
        for user in users:
            uid = user.get('uid') or user.get('mid')
            if uid in [u.get('uid') or u.get('mid') for u in users_to_update]:
                final_results.append(results[update_index])
                update_index += 1
            else:
                final_results.append((True, "skipped"))
        
        return final_results
    
    async def _get_user_stats_optimized(self, uid: int) -> Optional[Dict[str, Any]]:
        """优化版获取用户统计信息"""
        try:
            # 并行获取用户基本信息和视频信息
            user_info_task = asyncio.create_task(self.get_user_info(uid))
            videos_task = asyncio.create_task(self.get_user_videos(uid, 1, 30))  # 获取前30个视频用于准确计算
            
            user_info, videos_info = await asyncio.gather(
                user_info_task, videos_task, return_exceptions=True
            )
            
            # 处理用户信息
            if isinstance(user_info, Exception):
                self.logger.warning(f"用户 {uid} 基本信息获取失败: {user_info}")
                return None
            
            if not user_info:
                self.logger.warning(f"用户 {uid} 基本信息为空")
                return None
            
            # 处理视频信息（允许失败）
            if isinstance(videos_info, Exception):
                self.logger.warning(f"用户 {uid} 视频信息获取失败: {videos_info}")
                videos_info = None
            
            # 构建统计信息
            return self._build_user_stats(uid, user_info, videos_info)
                
        except Exception as e:
            self.logger.error(f"获取用户 {uid} 统计信息异常: {e}")
            return None
    
    def _build_user_stats(self, uid: int, user_info: Dict[str, Any], videos_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """构建用户统计信息"""
        try:
            # 解析用户基本信息 - 兼容多种API响应格式
            card_info = {}
            archive_count = 0
            
            # 检查API响应格式
            if 'data' in user_info and user_info['data']:
                # 格式1: 标准API响应格式 {"code": 0, "data": {"card": {...}}}
                data = user_info['data']
                card_info = data.get('card', {})
                # 某些情况下可能直接在data中包含archive_count
                if 'archive_count' in data:
                    archive_count = data.get('archive_count', 0)
                    
            elif 'card' in user_info:
                # 格式2: 直接包含card信息的格式 {"card": {...}, "archive_count": 123}
                card_info = user_info.get('card', {})
                archive_count = user_info.get('archive_count', 0)
            else:
                # 格式3: 直接是用户信息（某些API调用的结果）
                # 检查是否直接包含用户字段（如fans, following等）
                if 'fans' in user_info or 'archive_count' in user_info:
                    card_info = user_info
                    archive_count = user_info.get('archive_count', 0)
                else:
                    self.logger.warning(f"用户 {uid} 响应格式未知: {list(user_info.keys())}")
                    return self._get_default_stats(uid)
            
            # 基础统计信息
            stats = {
                "uid": uid,
                "fans_count": card_info.get('fans', 0),
                "following_count": card_info.get('friend', card_info.get('attention', card_info.get('following', 0))),  # 兼容不同字段名
                "video_count": archive_count or card_info.get('archive_count', 0),  # 多来源获取视频数
                "total_views": 0,
                "last_video_time": 0,
                "activity_score": 0.5  # 默认活跃度
            }
            
            # 记录基础信息获取结果
            self.logger.debug(f"用户 {uid} 基础信息: 粉丝={stats['fans_count']}, 关注={stats['following_count']}, 视频数={stats['video_count']}")
            
            # 解析视频信息，获取更详细的统计数据
            self.logger.debug(f"用户 {uid} 视频信息调试: videos_info是否存在: {videos_info is not None}")
            if videos_info:
                self.logger.debug(f"用户 {uid} 视频信息keys: {list(videos_info.keys())}")
                if 'data' in videos_info:
                    self.logger.debug(f"用户 {uid} 视频data存在: {videos_info.get('data') is not None}")
                    if videos_info['data']:
                        self.logger.debug(f"用户 {uid} 视频data keys: {list(videos_info['data'].keys())}")
            
            if videos_info and videos_info.get('data'):
                video_data = videos_info['data']
                
                # 获取视频总数（如果之前没有获取到）
                if stats["video_count"] == 0:
                    # 多种方式获取视频总数
                    page_info = video_data.get('page', {})
                    stats["video_count"] = (
                        page_info.get('count', 0) or  # 最常见的字段
                        video_data.get('count', 0) or  # 备选字段
                        len(video_data.get('list', {}).get('vlist', []))  # 最后备选：当前页视频数
                    )
                    self.logger.debug(f"用户 {uid} 从视频API获取视频数: {stats['video_count']}")
                
                # 获取视频列表
                vlist = []
                list_data = video_data.get('list', {})
                self.logger.debug(f"用户 {uid} list_data类型: {type(list_data)}, 内容预览: {str(list_data)[:200]}")
                
                if isinstance(list_data, dict):
                    vlist = list_data.get('vlist', [])
                elif isinstance(list_data, list):
                    vlist = list_data
                
                self.logger.debug(f"用户 {uid} 视频列表长度: {len(vlist)}")
                
                if vlist:
                    # 最新视频信息
                    latest_video = vlist[0]  # 按发布时间排序，第一个是最新的
                    stats["last_video_time"] = latest_video.get('created', 0)
                    
                    self.logger.debug(f"用户 {uid} 最新视频信息: {latest_video}")
                    self.logger.debug(f"用户 {uid} 最新视频时间: {stats['last_video_time']}")
                    
                    # 计算总播放量
                    total_views = 0
                    for i, video in enumerate(vlist):
                        play_count = video.get('play', 0)
                        # 处理可能的字符串格式播放量
                        if isinstance(play_count, str):
                            try:
                                play_count = int(play_count)
                            except (ValueError, TypeError):
                                play_count = 0
                        total_views += play_count
                        
                        if i < 3:  # 只记录前3个视频的详细信息
                            self.logger.debug(f"用户 {uid} 视频{i+1}: 标题={video.get('title', 'N/A')}, 播放量={play_count}")
                    
                    stats["total_views"] = total_views
                    self.logger.debug(f"用户 {uid} 总播放量计算: {total_views}")
                    
                    # 如果当前页有30个视频且总视频数大于30，尝试获取更多页估算总播放量
                    if len(vlist) == 30 and stats["video_count"] > 30:
                        # 基于当前页的平均播放量估算总播放量
                        avg_views_per_video = total_views / len(vlist)
                        estimated_total_views = avg_views_per_video * stats["video_count"]
                        
                        # 为了保险起见，只在估算值合理的情况下使用
                        if estimated_total_views > total_views:
                            stats["total_views"] = int(estimated_total_views)
                        
                        self.logger.debug(f"用户 {uid} 播放量估算: 当前页{total_views}, 估算总计{estimated_total_views}")
                else:
                    self.logger.debug(f"用户 {uid} 视频列表为空")
            else:
                # 视频信息获取失败，但我们仍然有基础的视频数量信息
                if stats["video_count"] > 0:
                    self.logger.info(f"用户 {uid} 视频详情获取失败，但有视频数量: {stats['video_count']}")
                else:
                    self.logger.debug(f"用户 {uid} 无法获取视频信息")
            
            # 计算活跃度分数
            stats["activity_score"] = self._calculate_activity_score(stats)
            
            self.logger.debug(f"用户 {uid} 统计信息: 粉丝{stats['fans_count']}, 视频{stats['video_count']}, "
                             f"播放量{stats['total_views']}, 最后视频{stats['last_video_time']}, 活跃度{stats['activity_score']}")
            
            return stats
            
        except Exception as e:
            self.logger.error(f"构建用户 {uid} 统计信息失败: {e}")
            return self._get_default_stats(uid)
    
    def _get_default_stats(self, uid: int) -> Dict[str, Any]:
        """获取默认的统计信息结构"""
        return {
            "uid": uid,
            "fans_count": 0,
            "following_count": 0,
            "video_count": 0,
            "total_views": 0,
            "last_video_time": 0,
            "activity_score": 0.5
        }
    
    def _calculate_activity_score(self, stats: Dict[str, Any]) -> float:
        """计算活跃度分数"""
        try:
            import time
            
            current_time = int(time.time())
            last_video_time = stats.get("last_video_time", 0)
            video_count = stats.get("video_count", 0)
            
            # 时间因子（最重要）
            if last_video_time > 0:
                days_since_last = (current_time - last_video_time) / (24 * 3600)
                if days_since_last <= 7:
                    time_factor = 0.9
                elif days_since_last <= 30:
                    time_factor = 0.7
                elif days_since_last <= 90:
                    time_factor = 0.5
                else:
                    time_factor = 0.3
            else:
                time_factor = 0.3
            
            # 内容产出因子
            if video_count >= 100:
                content_factor = 0.1
            elif video_count < 10:
                content_factor = -0.1
            else:
                content_factor = 0.05
            
            # 最终分数
            activity_score = max(0, min(1, time_factor + content_factor))
            return round(activity_score, 2)
            
        except Exception:
            return 0.5
    
    async def _save_user_stats_to_db(self, db_manager, uid: int, stats: Dict[str, Any]):
        """保存用户统计信息到数据库"""
        try:
            # 检查是否已存在
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
                    stats["fans_count"], stats["following_count"], 
                    stats["video_count"], stats["total_views"],
                    stats["last_video_time"], stats["activity_score"], uid
                ))
            else:
                # 插入新记录
                await db_manager._connection.execute("""
                    INSERT INTO user_stats 
                    (uid, fans_count, following_count, video_count, total_views, 
                     last_video_time, activity_score) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    uid, stats["fans_count"], stats["following_count"],
                    stats["video_count"], stats["total_views"],
                    stats["last_video_time"], stats["activity_score"]
                ))
            
            await db_manager._connection.commit()
            
        except Exception as e:
            self.logger.error(f"保存用户 {uid} 统计信息到数据库失败: {e}")
            raise


# 全局API实例
_bilibili_api = BilibiliAPI()


async def get_bilibili_api() -> BilibiliAPI:
    """获取哔哩哔哩API实例"""
    return _bilibili_api 