# -*- coding: utf-8 -*-
"""
性能优化模块
Performance Optimization Module

提供并发处理、智能延迟调整、批量处理等性能优化功能
"""

import asyncio
import aiohttp
import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .logger import get_logger


@dataclass
class OptimizationConfig:
    """优化配置"""
    # 并发控制
    max_concurrent_requests: int = 5  # 最大并发请求数
    request_pool_size: int = 10  # 请求池大小
    
    # 智能延迟
    base_delay: float = 0.5  # 基础延迟(秒)
    min_delay: float = 0.2  # 最小延迟
    max_delay: float = 10.0  # 最大延迟
    adaptive_delay: bool = True  # 是否启用自适应延迟
    
    # 批量处理
    batch_size: int = 50  # 批量处理大小
    enable_batching: bool = True  # 是否启用批量处理
    
    # 重试机制
    max_retries: int = 3  # 最大重试次数
    retry_backoff: float = 2.0  # 重试退避倍数
    
    # 缓存设置
    enable_cache: bool = True  # 是否启用缓存
    cache_ttl: int = 300  # 缓存TTL(秒)
    
    # 风控检测
    failure_rate_threshold: float = 0.7  # 失败率阈值
    failure_window_size: int = 20  # 失败检测窗口大小
    rate_limit_cooldown: int = 30  # 风控冷却时间(秒)


class PerformanceOptimizer:
    """性能优化器"""
    
    def __init__(self, config: OptimizationConfig = None):
        self.config = config or OptimizationConfig()
        self.logger = get_logger()
        
        # 性能统计
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "rate_limit_hits": 0
        }
        
        # 并发控制
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)
        self.request_queue = asyncio.Queue(maxsize=self.config.request_pool_size)
        
        # 自适应延迟
        self.current_delay = self.config.base_delay
        self.recent_response_times = []
        self.failure_window = []
        
        # 缓存
        self.cache = {} if self.config.enable_cache else None
        self.cache_timestamps = {} if self.config.enable_cache else None
        
        # 风控检测
        self.last_rate_limit_time = 0
        self.consecutive_failures = 0
        
    async def process_users_concurrently(self, 
                                       users: List[Dict[str, Any]], 
                                       process_func: Callable,
                                       progress_callback: Optional[Callable] = None) -> List[Tuple[bool, Any]]:
        """并发处理用户列表"""
        if not self.config.enable_batching:
            return await self._process_sequential(users, process_func, progress_callback)
        
        self.logger.info(f"开始并发处理 {len(users)} 个用户，并发数: {self.config.max_concurrent_requests}")
        
        # 分批处理
        batches = [users[i:i + self.config.batch_size] 
                  for i in range(0, len(users), self.config.batch_size)]
        
        all_results = []
        processed_count = 0
        
        for batch_idx, batch in enumerate(batches):
            self.logger.info(f"处理第 {batch_idx + 1}/{len(batches)} 批，用户数: {len(batch)}")
            
            # 检查是否需要冷却
            if await self._should_cooldown():
                cooldown_time = self.config.rate_limit_cooldown
                self.logger.warning(f"检测到高失败率，冷却 {cooldown_time} 秒...")
                await asyncio.sleep(cooldown_time)
                self._reset_failure_detection()
            
            # 并发处理当前批次
            batch_tasks = [
                self._process_user_with_semaphore(user, process_func)
                for user in batch
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # 处理异常结果
            for i, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    self.logger.error(f"用户处理异常: {result}")
                    batch_results[i] = (False, str(result))
            
            all_results.extend(batch_results)
            processed_count += len(batch)
            
            # 调用进度回调
            if progress_callback:
                progress_callback(processed_count, len(users))
            
            # 批次间延迟
            if batch_idx < len(batches) - 1:  # 不是最后一批
                batch_delay = self._calculate_batch_delay()
                self.logger.debug(f"批次间延迟: {batch_delay:.2f}秒")
                await asyncio.sleep(batch_delay)
        
        success_count = sum(1 for success, _ in all_results if success)
        self.logger.info(f"并发处理完成: 成功 {success_count}/{len(users)}")
        
        return all_results
    
    async def _process_user_with_semaphore(self, user: Dict[str, Any], process_func: Callable) -> Tuple[bool, Any]:
        """使用信号量控制的用户处理"""
        async with self.semaphore:
            return await self._process_single_user(user, process_func)
    
    async def _process_single_user(self, user: Dict[str, Any], process_func: Callable) -> Tuple[bool, Any]:
        """处理单个用户"""
        uid = user.get('uid') or user.get('mid')
        if not uid:
            return False, "Missing UID"
        
        # 检查缓存
        if self.config.enable_cache:
            cached_result = self._get_from_cache(uid)
            if cached_result is not None:
                self.stats["cache_hits"] += 1
                return True, cached_result
            self.stats["cache_misses"] += 1
        
        # 执行处理
        start_time = time.time()
        retry_count = 0
        
        while retry_count <= self.config.max_retries:
            try:
                self.stats["total_requests"] += 1
                
                # 应用自适应延迟
                if self.config.adaptive_delay and retry_count == 0:
                    await asyncio.sleep(self._get_adaptive_delay())
                
                result = await process_func(user)
                
                # 记录成功
                end_time = time.time()
                response_time = end_time - start_time
                self._record_success(response_time)
                
                # 缓存结果
                if self.config.enable_cache and result:
                    self._cache_result(uid, result)
                
                return True, result
                
            except Exception as e:
                retry_count += 1
                self._record_failure()
                
                if retry_count <= self.config.max_retries:
                    # 重试延迟
                    retry_delay = self.config.base_delay * (self.config.retry_backoff ** retry_count)
                    retry_delay = min(retry_delay, self.config.max_delay)
                    self.logger.warning(f"处理用户 {uid} 失败，{retry_delay:.2f}秒后重试 ({retry_count}/{self.config.max_retries})")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error(f"处理用户 {uid} 最终失败: {e}")
                    return False, str(e)
        
        return False, "Max retries exceeded"
    
    async def _process_sequential(self, users: List[Dict[str, Any]], 
                                process_func: Callable,
                                progress_callback: Optional[Callable] = None) -> List[Tuple[bool, Any]]:
        """顺序处理（作为并发处理的后备）"""
        self.logger.info(f"开始顺序处理 {len(users)} 个用户")
        
        results = []
        for i, user in enumerate(users):
            result = await self._process_single_user(user, process_func)
            results.append(result)
            
            if progress_callback:
                progress_callback(i + 1, len(users))
        
        return results
    
    def _get_adaptive_delay(self) -> float:
        """获取自适应延迟"""
        if not self.config.adaptive_delay:
            return self.config.base_delay
        
        # 基于近期响应时间调整
        if len(self.recent_response_times) >= 5:
            avg_response_time = sum(self.recent_response_times[-5:]) / 5
            # 响应时间越长，延迟越长
            if avg_response_time > 2.0:
                self.current_delay = min(self.current_delay * 1.2, self.config.max_delay)
            elif avg_response_time < 0.5:
                self.current_delay = max(self.current_delay * 0.9, self.config.min_delay)
        
        # 基于失败率调整
        if len(self.failure_window) >= 10:
            failure_rate = sum(self.failure_window[-10:]) / 10
            if failure_rate > 0.3:  # 30%失败率
                self.current_delay = min(self.current_delay * 1.5, self.config.max_delay)
        
        # 添加随机抖动，避免请求同步
        jitter = random.uniform(-0.1, 0.1) * self.current_delay
        return max(self.config.min_delay, self.current_delay + jitter)
    
    def _calculate_batch_delay(self) -> float:
        """计算批次间延迟"""
        base_delay = 1.0
        
        # 基于失败率调整
        if len(self.failure_window) >= self.config.failure_window_size:
            recent_failures = sum(self.failure_window[-self.config.failure_window_size:])
            failure_rate = recent_failures / self.config.failure_window_size
            
            if failure_rate > 0.5:
                base_delay *= 3.0
            elif failure_rate > 0.3:
                base_delay *= 2.0
        
        return min(base_delay, 5.0)
    
    async def _should_cooldown(self) -> bool:
        """检查是否需要冷却"""
        current_time = time.time()
        
        # 检查最近是否刚刚冷却过
        if current_time - self.last_rate_limit_time < self.config.rate_limit_cooldown:
            return False
        
        # 检查失败率
        if len(self.failure_window) >= self.config.failure_window_size:
            recent_failures = sum(self.failure_window[-self.config.failure_window_size:])
            failure_rate = recent_failures / self.config.failure_window_size
            
            if failure_rate >= self.config.failure_rate_threshold:
                self.last_rate_limit_time = current_time
                self.stats["rate_limit_hits"] += 1
                return True
        
        return False
    
    def _reset_failure_detection(self):
        """重置失败检测"""
        self.failure_window.clear()
        self.consecutive_failures = 0
        self.current_delay = self.config.base_delay
    
    def _record_success(self, response_time: float):
        """记录成功请求"""
        self.stats["successful_requests"] += 1
        self.stats["total_time"] += response_time
        self.stats["avg_response_time"] = self.stats["total_time"] / self.stats["total_requests"]
        
        # 更新响应时间历史
        self.recent_response_times.append(response_time)
        if len(self.recent_response_times) > 20:
            self.recent_response_times.pop(0)
        
        # 更新失败窗口
        self.failure_window.append(0)
        if len(self.failure_window) > self.config.failure_window_size:
            self.failure_window.pop(0)
        
        self.consecutive_failures = 0
    
    def _record_failure(self):
        """记录失败请求"""
        self.stats["failed_requests"] += 1
        self.consecutive_failures += 1
        
        # 更新失败窗口
        self.failure_window.append(1)
        if len(self.failure_window) > self.config.failure_window_size:
            self.failure_window.pop(0)
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if not self.config.enable_cache or key not in self.cache:
            return None
        
        # 检查缓存是否过期
        cache_time = self.cache_timestamps.get(key, 0)
        if time.time() - cache_time > self.config.cache_ttl:
            del self.cache[key]
            del self.cache_timestamps[key]
            return None
        
        return self.cache[key]
    
    def _cache_result(self, key: str, result: Any):
        """缓存结果"""
        if not self.config.enable_cache:
            return
        
        self.cache[key] = result
        self.cache_timestamps[key] = time.time()
        
        # 限制缓存大小
        if len(self.cache) > 1000:
            # 移除最旧的缓存项
            oldest_key = min(self.cache_timestamps, key=self.cache_timestamps.get)
            del self.cache[oldest_key]
            del self.cache_timestamps[oldest_key]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        total_requests = self.stats["total_requests"]
        if total_requests == 0:
            return self.stats.copy()
        
        stats = self.stats.copy()
        stats.update({
            "success_rate": self.stats["successful_requests"] / total_requests,
            "failure_rate": self.stats["failed_requests"] / total_requests,
            "cache_hit_rate": self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"]) if (self.stats["cache_hits"] + self.stats["cache_misses"]) > 0 else 0,
            "current_delay": self.current_delay,
            "recent_failure_rate": sum(self.failure_window[-10:]) / min(10, len(self.failure_window)) if self.failure_window else 0
        })
        
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "rate_limit_hits": 0
        }
        self.recent_response_times.clear()
        self.failure_window.clear()
        self.consecutive_failures = 0
        self.current_delay = self.config.base_delay


# 创建默认优化器实例
default_optimizer = PerformanceOptimizer()


def get_performance_optimizer(config: OptimizationConfig = None) -> PerformanceOptimizer:
    """获取性能优化器实例"""
    if config is None:
        return default_optimizer
    return PerformanceOptimizer(config) 