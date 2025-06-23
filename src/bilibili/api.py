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
        self.retry_times = get_config_value("bilibili.retry_times", 3)
        self.timeout = get_config_value("bilibili.timeout", 30)
        
        # API端点
        self.endpoints = {
            "following_list": "https://api.bilibili.com/x/relation/followings",
            "user_info": "https://api.bilibili.com/x/web-interface/card",
            "user_stat": "https://api.bilibili.com/x/relation/stat",
            "modify_relation": "https://api.bilibili.com/x/relation/modify",
            "follow_groups": "https://api.bilibili.com/x/relation/tags",
            "batch_modify": "https://api.bilibili.com/x/relation/batch/modify",
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
                            error_msg = data.get('message', '未知错误')
                            self.logger.warning(f"API返回错误: {error_msg} (code: {data.get('code')})")
                            # 记录更多详细信息
                            self.logger.debug(f"完整API响应: {data}")
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
    
    async def get_all_following(self, progress_callback=None) -> List[Dict[str, Any]]:
        """获取所有关注用户"""
        all_following = []
        page = 1
        page_size = 50
        invalid_users = 0
        
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


# 全局API实例
_bilibili_api = BilibiliAPI()


async def get_bilibili_api() -> BilibiliAPI:
    """获取哔哩哔哩API实例"""
    return _bilibili_api 