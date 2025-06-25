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
                                self._log_error_with_counter(f"wind_control_{error_code}", 
                                    f"遇到风控限制 (-352)，建议检查Cookie和API频率限制", "error")
                                await asyncio.sleep(10)  # 遇到风控错误时等待更长时间
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
        """批量获取用户详细信息以补充等级等字段"""
        enriched_users = []
        consecutive_failures = 0
        base_delay = 0.5
        
        for i, user in enumerate(users):
            try:
                uid = user.get('uid') or user.get('mid')
                
                # 获取用户详细信息
                user_detail = await self.get_user_info(uid)
                if user_detail and user_detail.get('card'):
                    card_info = user_detail['card']
                    
                    # 更新用户等级信息
                    if 'level_info' in card_info:
                        user['level'] = card_info['level_info'].get('current_level', 0)
                        self.logger.debug(f"获取用户 {user.get('uname', 'Unknown')} 等级: {user['level']}")
                    
                    # 更新其他可能缺失的字段
                    if 'face' not in user or not user['face']:
                        user['face'] = card_info.get('face', '')
                    if 'sign' not in user or not user['sign']:
                        user['sign'] = card_info.get('sign', '')
                    
                    # 成功获取，重置失败计数
                    consecutive_failures = 0
                elif user_detail is None:
                    # API调用失败，增加失败计数
                    consecutive_failures += 1
                    self.logger.warning(f"获取用户 {user.get('uname', 'Unknown')} 详细信息失败，连续失败 {consecutive_failures} 次")
                    
                    # 如果连续失败次数过多，增加延迟时间
                    if consecutive_failures >= 3:
                        extended_delay = base_delay * (2 ** min(consecutive_failures - 2, 4))
                        self.logger.warning(f"连续失败次数过多，延长等待时间至 {extended_delay:.1f} 秒")
                        await asyncio.sleep(extended_delay)
                        consecutive_failures = 0  # 重置计数器
                
                enriched_users.append(user)
                
                # 动态调整延迟时间
                current_delay = base_delay
                if consecutive_failures > 0:
                    current_delay = base_delay * (1 + consecutive_failures * 0.5)
                
                # 每获取10个用户信息后稍微休息，避免API频率限制
                if (i + 1) % 10 == 0:
                    await asyncio.sleep(current_delay)
                    self.logger.info(f"已获取 {i + 1}/{len(users)} 个用户的详细信息")
                elif (i + 1) % 5 == 0:
                    # 每5个用户也稍微休息一下
                    await asyncio.sleep(current_delay * 0.5)
                
            except Exception as e:
                consecutive_failures += 1
                self.logger.error(f"获取用户 {user.get('uname', 'Unknown')} 详细信息失败: {e}")
                # 即使获取详细信息失败，也保留原始用户数据
                enriched_users.append(user)
        
        self.logger.info(f"批量获取用户详细信息完成，处理 {len(users)} 个用户")
        return enriched_users
    
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
        result = await self._request("GET", url)
        
        # 添加API延迟
        await asyncio.sleep(self.api_delay)
        
        return result
    
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
            elif 'card' in user_info:
                # 格式2: 直接包含card信息的格式
                card_info = user_info.get('card', {})
                archive_count = user_info.get('archive_count', 0)
            else:
                self.logger.warning(f"用户 {uid} 响应格式未知: {list(user_info.keys())}")
                return None
            
            # 2. 获取用户视频列表（第一页，用于获取总数和最新视频时间）
            videos_info = await self.get_user_videos(uid, pn=1, ps=1)
            
            # 提取统计信息
            stats = {
                "uid": uid,
                "fans_count": card_info.get('fans', 0),  # 粉丝数
                "following_count": card_info.get('friend', 0),  # 关注数
                "video_count": 0,
                "total_views": 0,
                "last_video_time": 0,
                "activity_score": 0.5  # 默认活跃度
            }
            
            # 处理视频信息
            # 首先尝试从用户信息中直接获取视频数量
            if archive_count > 0:
                stats["video_count"] = archive_count
            
            # 然后尝试从视频列表API获取详细信息
            if videos_info and 'data' in videos_info and videos_info['data']:
                video_data = videos_info['data']
                
                # 如果之前没有获取到视频数量，从这里获取
                if stats["video_count"] == 0:
                    stats["video_count"] = video_data.get('page', {}).get('count', 0)
                
                # 最新视频信息
                vlist = video_data.get('list', {}).get('vlist', [])
                if vlist:
                    latest_video = vlist[0]  # 第一个是最新的
                    stats["last_video_time"] = latest_video.get('created', 0)
                    
                    # 计算总播放量 - 遍历前几页获取更准确的数据
                    total_views = 0
                    for video in vlist:
                        total_views += video.get('play', 0)
                    
                    # 如果只有一页数据，可能需要获取更多页来计算总播放量
                    # 但为了避免API调用过多，这里只使用当前页的数据
                    stats["total_views"] = total_views
            
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
            
            self.logger.info(f"✅ 用户 {uid} 统计信息获取成功: 粉丝{stats['fans_count']}, 视频{stats['video_count']}, 活跃度{stats['activity_score']}")
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


# 全局API实例
_bilibili_api = BilibiliAPI()


async def get_bilibili_api() -> BilibiliAPI:
    """获取哔哩哔哩API实例"""
    return _bilibili_api 