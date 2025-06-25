# -*- coding: utf-8 -*-
"""
优化版哔哩哔哩API接口模块
Optimized Bilibili API Interface Module

使用性能优化器提升API调用效率
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .api import BilibiliAPI
from ..core.performance_optimizer import PerformanceOptimizer, OptimizationConfig
from ..core.logger import get_logger


class OptimizedBilibiliAPI(BilibiliAPI):
    """优化版哔哩哔哩API客户端"""
    
    def __init__(self, optimization_config: OptimizationConfig = None):
        super().__init__()
        
        # 性能优化器
        self.optimizer = PerformanceOptimizer(optimization_config or OptimizationConfig(
            max_concurrent_requests=8,  # 增加并发数
            batch_size=30,  # 减小批次大小以更好控制
            base_delay=0.3,  # 减少基础延迟
            min_delay=0.1,
            max_delay=8.0,
            adaptive_delay=True,
            enable_cache=True,
            cache_ttl=600  # 10分钟缓存
        ))
        
        self.logger = get_logger()
        
        # 智能重试配置
        self.smart_retry_config = {
            "user_info": {"max_retries": 2, "backoff": 1.5},
            "user_stats": {"max_retries": 3, "backoff": 2.0},
            "user_videos": {"max_retries": 2, "backoff": 1.5},
            "following_list": {"max_retries": 3, "backoff": 2.0}
        }
    
    async def get_users_stats_batch(self, users: List[Dict[str, Any]], 
                                  progress_callback=None) -> List[Tuple[bool, Any]]:
        """批量获取用户统计信息（优化版）"""
        self.logger.info(f"开始批量获取 {len(users)} 个用户的统计信息（优化版）")
        
        async def process_user_stats(user):
            """处理单个用户统计信息"""
            uid = user.get('uid') or user.get('mid')
            return await self._get_user_stats_optimized(uid)
        
        results = await self.optimizer.process_users_concurrently(
            users, process_user_stats, progress_callback
        )
        
        # 统计结果
        success_count = sum(1 for success, _ in results if success)
        self.logger.info(f"批量统计信息获取完成: 成功 {success_count}/{len(users)}")
        
        return results
    
    async def get_users_info_batch(self, users: List[Dict[str, Any]], 
                                 include_level=True, progress_callback=None) -> List[Tuple[bool, Any]]:
        """批量获取用户详细信息（优化版）"""
        self.logger.info(f"开始批量获取 {len(users)} 个用户的详细信息（优化版）")
        
        async def process_user_info(user):
            """处理单个用户详细信息"""
            uid = user.get('uid') or user.get('mid')
            return await self._get_user_info_optimized(uid, include_level)
        
        results = await self.optimizer.process_users_concurrently(
            users, process_user_info, progress_callback
        )
        
        # 统计结果
        success_count = sum(1 for success, _ in results if success)
        self.logger.info(f"批量用户信息获取完成: 成功 {success_count}/{len(users)}")
        
        return results
    
    async def _get_user_stats_optimized(self, uid: int) -> Optional[Dict[str, Any]]:
        """优化版获取用户统计信息"""
        cache_key = f"stats_{uid}"
        
        try:
            # 优化的用户信息获取策略
            tasks = []
            
            # 并行获取用户基本信息和视频信息
            tasks.append(self._get_user_info_with_retry(uid, "user_info"))
            tasks.append(self._get_user_videos_with_retry(uid, 1, 1, "user_videos"))  # 只获取第一页第一个视频
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            user_info_result, videos_result = results
            
            # 处理用户信息
            if isinstance(user_info_result, Exception) or not user_info_result:
                self.logger.warning(f"获取用户 {uid} 基本信息失败")
                return None
            
            # 处理视频信息（允许失败）
            if isinstance(videos_result, Exception):
                videos_result = None
            
            # 构建统计信息
            stats = self._build_user_stats(uid, user_info_result, videos_result)
            
            if stats:
                self.logger.debug(f"✅ 优化获取用户 {uid} 统计信息成功")
                return stats
            else:
                self.logger.warning(f"❌ 构建用户 {uid} 统计信息失败")
                return None
                
        except Exception as e:
            self.logger.error(f"优化获取用户 {uid} 统计信息异常: {e}")
            return None
    
    async def _get_user_info_optimized(self, uid: int, include_level=True) -> Optional[Dict[str, Any]]:
        """优化版获取用户详细信息"""
        try:
            user_info = await self._get_user_info_with_retry(uid, "user_info")
            
            if not user_info:
                return None
            
            # 简化信息提取
            if 'data' in user_info:
                card_info = user_info['data'].get('card', {})
            elif 'card' in user_info:
                card_info = user_info['card']
            else:
                return None
            
            # 构建返回信息
            result = {
                "uid": uid,
                "face": card_info.get('face', ''),
                "sign": card_info.get('sign', ''),
                "level": card_info.get('level_info', {}).get('current_level', 0) if include_level else 0,
                "vip_type": card_info.get('vip', {}).get('vipType', 0),
                "vip_status": card_info.get('vip', {}).get('vipStatus', 0),
                "official_type": card_info.get('official', {}).get('type', 0),
                "official_title": card_info.get('official', {}).get('title', '')
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"优化获取用户 {uid} 详细信息异常: {e}")
            return None
    
    async def _get_user_info_with_retry(self, uid: int, operation_type: str) -> Optional[Dict[str, Any]]:
        """带智能重试的用户信息获取"""
        config = self.smart_retry_config.get(operation_type, {"max_retries": 2, "backoff": 1.5})
        
        for attempt in range(config["max_retries"] + 1):
            try:
                # 使用父类的方法，但减少延迟
                result = await super().get_user_info(uid)
                if result:
                    return result
                    
            except Exception as e:
                if attempt < config["max_retries"]:
                    wait_time = config["backoff"] ** attempt
                    self.logger.debug(f"获取用户 {uid} 信息失败，{wait_time:.1f}秒后重试 ({attempt + 1}/{config['max_retries']})")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.warning(f"获取用户 {uid} 信息最终失败: {e}")
                    break
        
        return None
    
    async def _get_user_videos_with_retry(self, uid: int, pn: int, ps: int, operation_type: str) -> Optional[Dict[str, Any]]:
        """带智能重试的用户视频获取"""
        config = self.smart_retry_config.get(operation_type, {"max_retries": 2, "backoff": 1.5})
        
        for attempt in range(config["max_retries"] + 1):
            try:
                result = await super().get_user_videos(uid, pn, ps)
                if result:
                    return result
                    
            except Exception as e:
                if attempt < config["max_retries"]:
                    wait_time = config["backoff"] ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    break
        
        return None
    
    def _build_user_stats(self, uid: int, user_info: Dict[str, Any], videos_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """构建用户统计信息"""
        try:
            # 处理用户基本信息
            card_info = {}
            archive_count = 0
            
            if 'data' in user_info:
                data = user_info['data']
                if not data:
                    return None
                card_info = data.get('card', {})
            elif 'card' in user_info:
                card_info = user_info.get('card', {})
                archive_count = user_info.get('archive_count', 0)
            else:
                return None
            
            # 基础统计信息
            stats = {
                "uid": uid,
                "fans_count": card_info.get('fans', 0),
                "following_count": card_info.get('friend', 0),
                "video_count": archive_count,
                "total_views": 0,
                "last_video_time": 0,
                "activity_score": 0.5
            }
            
            # 处理视频信息
            if videos_info and 'data' in videos_info and videos_info['data']:
                video_data = videos_info['data']
                
                # 获取视频数量
                if stats["video_count"] == 0:
                    stats["video_count"] = video_data.get('page', {}).get('count', 0)
                
                # 获取最新视频信息
                vlist = video_data.get('list', {}).get('vlist', [])
                if vlist:
                    latest_video = vlist[0]
                    stats["last_video_time"] = latest_video.get('created', 0)
                    
                    # 计算总播放量 - 当前页所有视频的播放量之和
                    total_views = 0
                    for video in vlist:
                        total_views += video.get('play', 0)
                    stats["total_views"] = total_views
            
            # 计算活跃度 - 使用改进的算法
            if stats["last_video_time"] > 0:
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
                
                # 根据播放量调整
                if stats["total_views"] > 10000000:  # 1000万以上
                    view_adjustment = 0.1
                elif stats["total_views"] > 1000000:  # 100万以上
                    view_adjustment = 0.05
                else:
                    view_adjustment = 0
                
                final_activity = base_activity + activity_adjustment + view_adjustment
                stats["activity_score"] = max(0.1, min(0.9, final_activity))
            elif stats["video_count"] > 0:
                # 无法获取最新视频时间，根据视频数量估算
                if stats["video_count"] > 100:
                    stats["activity_score"] = 0.6
                elif stats["video_count"] > 20:
                    stats["activity_score"] = 0.4
                else:
                    stats["activity_score"] = 0.3
            
            return stats
            
        except Exception as e:
            self.logger.error(f"构建用户 {uid} 统计信息失败: {e}")
            return None
    
    async def get_all_following_optimized(self, progress_callback=None, fetch_user_details=True) -> List[Dict[str, Any]]:
        """优化版获取所有关注用户"""
        self.logger.info("开始优化获取关注列表...")
        
        # 首先快速获取基础关注列表
        all_following = await super().get_all_following(progress_callback, fetch_user_details=False)
        
        if not fetch_user_details:
            return all_following
        
        # 批量获取用户详细信息
        self.logger.info(f"开始批量获取 {len(all_following)} 个用户的详细信息...")
        
        async def enrich_user(user):
            """补充用户详细信息"""
            uid = user.get('uid') or user.get('mid')
            user_detail = await self._get_user_info_optimized(uid, include_level=True)
            
            if user_detail:
                # 更新用户信息
                user.update({
                    'level': user_detail.get('level', 0),
                    'face': user_detail.get('face', user.get('face', '')),
                    'sign': user_detail.get('sign', user.get('sign', ''))
                })
            
            return user
        
        # 使用优化器批量处理
        enriched_results = await self.optimizer.process_users_concurrently(
            all_following, enrich_user, progress_callback
        )
        
        # 提取成功的结果
        enriched_users = []
        for success, result in enriched_results:
            if success and result:
                enriched_users.append(result)
        
        self.logger.info(f"优化获取关注列表完成，成功获取 {len(enriched_users)} 个用户的详细信息")
        return enriched_users
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        return self.optimizer.get_performance_stats()
    
    def reset_performance_stats(self):
        """重置性能统计"""
        self.optimizer.reset_stats()
    
    async def close(self):
        """关闭资源"""
        await super().close()


# 全局优化API实例
_optimized_bilibili_api = None


async def get_optimized_bilibili_api() -> OptimizedBilibiliAPI:
    """获取优化版哔哩哔哩API实例"""
    global _optimized_bilibili_api
    if _optimized_bilibili_api is None:
        _optimized_bilibili_api = OptimizedBilibiliAPI()
    return _optimized_bilibili_api 