# -*- coding: utf-8 -*-
"""
保守性能优化器
Conservative Performance Optimizer

专门针对容易触发风控的环境，采用更保守的策略
"""

import asyncio
import time
import random
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple

from .performance_optimizer import PerformanceOptimizer, OptimizationConfig
from .logger import get_logger


class ConservativeOptimizationConfig(OptimizationConfig):
    """保守优化配置"""
    
    def __init__(self):
        super().__init__()
        # 更保守的默认配置
        self.max_concurrent_requests = 1  # 降低到单线程
        self.batch_size = 10  # 减小批次
        self.base_delay = 2.0  # 增加基础延迟
        self.min_delay = 1.0  # 最小延迟也增加
        self.max_delay = 15.0  # 最大延迟增加
        self.adaptive_delay = True
        self.enable_cache = True
        self.cache_ttl = 1800  # 增加缓存时间到30分钟
        self.failure_rate_threshold = 0.3  # 更严格的失败率阈值
        self.failure_window_size = 10  # 减小窗口大小
        self.rate_limit_cooldown = 120  # 增加冷却时间到2分钟


class ConservativePerformanceOptimizer(PerformanceOptimizer):
    """保守性能优化器"""
    
    def __init__(self, config: ConservativeOptimizationConfig = None):
        self.config = config or ConservativeOptimizationConfig()
        self.logger = get_logger()
        
        # 更严格的风控检测
        self.wind_control_detected = False
        self.last_wind_control_time = 0
        self.wind_control_recovery_time = 300  # 5分钟恢复时间
        
        # 更保守的统计
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "wind_control_hits": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "rate_limit_hits": 0
        }
        
        # 单线程处理，不需要信号量
        self.current_delay = self.config.base_delay
        self.recent_response_times = []
        self.failure_window = []
        
        # 缓存
        self.cache = {} if self.config.enable_cache else None
        self.cache_timestamps = {} if self.config.enable_cache else None
        
        # 更严格的失败检测
        self.consecutive_wind_control = 0
        self.max_consecutive_wind_control = 3
    
    async def process_users_conservatively(self, 
                                         users: List[Dict[str, Any]], 
                                         process_func: Callable,
                                         progress_callback: Optional[Callable] = None) -> List[Tuple[bool, Any]]:
        """保守地处理用户列表（单线程顺序处理）"""
        self.logger.info(f"开始保守处理 {len(users)} 个用户（单线程模式）")
        
        results = []
        processed_count = 0
        
        for i, user in enumerate(users):
            # 检查风控状态
            if await self._check_wind_control_status():
                self.logger.warning("检测到风控状态，暂停处理...")
                break
            
            # 处理单个用户
            result = await self._process_single_user_conservatively(user, process_func)
            results.append(result)
            processed_count += 1
            
            # 调用进度回调
            if progress_callback:
                progress_callback(processed_count, len(users))
            
            # 保守的用户间延迟
            user_delay = await self._get_conservative_delay()
            self.logger.debug(f"用户 {i+1}/{len(users)} 处理完成，等待 {user_delay:.1f}秒")
            await asyncio.sleep(user_delay)
            
            # 每处理5个用户检查一次状态
            if (i + 1) % 5 == 0:
                self.logger.info(f"保守处理进度: {i+1}/{len(users)}")
                
                # 如果检测到问题，主动增加休息时间
                if self._should_take_break():
                    break_time = 60  # 1分钟休息
                    self.logger.info(f"主动休息 {break_time} 秒以避免风控...")
                    await asyncio.sleep(break_time)
        
        success_count = sum(1 for success, _ in results if success)
        self.logger.info(f"保守处理完成: 成功 {success_count}/{processed_count}")
        
        return results
    
    async def _process_single_user_conservatively(self, user: Dict[str, Any], process_func: Callable) -> Tuple[bool, Any]:
        """保守地处理单个用户"""
        uid = user.get('uid') or user.get('mid')
        if not uid:
            return False, "Missing UID"
        
        # 检查缓存
        if self.config.enable_cache:
            cached_result = self._get_from_cache(str(uid))
            if cached_result is not None:
                self.stats["cache_hits"] += 1
                return True, cached_result
            self.stats["cache_misses"] += 1
        
        # 保守的重试策略
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                self.stats["total_requests"] += 1
                start_time = time.time()
                
                # 执行处理
                result = await process_func(user)
                
                # 检查结果是否表明风控
                if self._is_wind_control_response(result):
                    self._handle_wind_control_detection()
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 30 * retry_count  # 递增等待时间
                        self.logger.warning(f"检测到风控响应，等待 {wait_time} 秒后重试...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        return False, "Wind control detected"
                
                # 记录成功
                end_time = time.time()
                response_time = end_time - start_time
                self._record_success(response_time)
                
                # 缓存结果
                if self.config.enable_cache and result:
                    self._cache_result(str(uid), result)
                
                return True, result
                
            except Exception as e:
                self._record_failure()
                retry_count += 1
                
                # 检查是否是风控相关异常
                error_str = str(e).lower()
                if '-352' in error_str or '-503' in error_str or '频繁' in error_str:
                    self._handle_wind_control_detection()
                    wait_time = 60 * retry_count  # 风控异常等待更长时间
                    if retry_count <= max_retries:
                        self.logger.error(f"风控异常，等待 {wait_time} 秒后重试: {e}")
                        await asyncio.sleep(wait_time)
                        continue
                
                if retry_count <= max_retries:
                    wait_time = 10 * retry_count
                    self.logger.warning(f"处理用户 {uid} 失败，{wait_time}秒后重试: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"处理用户 {uid} 最终失败: {e}")
                    return False, str(e)
        
        return False, "Max retries exceeded"
    
    async def _get_conservative_delay(self) -> float:
        """获取保守延迟"""
        base_delay = self.config.base_delay
        
        # 如果最近有风控，增加延迟
        if self.wind_control_detected:
            base_delay *= 2.0
        
        # 根据连续风控次数调整
        if self.consecutive_wind_control > 0:
            base_delay *= (1.5 ** self.consecutive_wind_control)
        
        # 根据失败率调整
        if len(self.failure_window) >= 5:
            recent_failure_rate = sum(self.failure_window[-5:]) / 5
            if recent_failure_rate > 0.2:  # 20%失败率就增加延迟
                base_delay *= (1 + recent_failure_rate)
        
        # 添加随机抖动
        jitter = random.uniform(0.8, 1.2)
        final_delay = base_delay * jitter
        
        # 确保在合理范围内
        return max(self.config.min_delay, min(final_delay, self.config.max_delay))
    
    async def _check_wind_control_status(self) -> bool:
        """检查是否处于风控状态"""
        current_time = time.time()
        
        # 如果最近检测到风控，检查是否可以恢复
        if self.wind_control_detected:
            if current_time - self.last_wind_control_time > self.wind_control_recovery_time:
                self.wind_control_detected = False
                self.consecutive_wind_control = 0
                self.logger.info("风控状态恢复，继续处理")
                return False
            else:
                remaining_time = self.wind_control_recovery_time - (current_time - self.last_wind_control_time)
                self.logger.warning(f"仍处于风控恢复期，剩余 {remaining_time:.0f} 秒")
                return True
        
        return False
    
    def _handle_wind_control_detection(self):
        """处理风控检测"""
        self.wind_control_detected = True
        self.last_wind_control_time = time.time()
        self.consecutive_wind_control += 1
        self.stats["wind_control_hits"] += 1
        
        self.logger.error(f"检测到风控！连续风控次数: {self.consecutive_wind_control}")
        
        # 如果连续风控次数过多，增加恢复时间
        if self.consecutive_wind_control >= self.max_consecutive_wind_control:
            self.wind_control_recovery_time = 600  # 增加到10分钟
            self.logger.error(f"连续风控次数过多，增加恢复时间到 {self.wind_control_recovery_time} 秒")
    
    def _is_wind_control_response(self, result) -> bool:
        """判断响应是否表明风控"""
        if result is None:
            return False
        
        # 检查结果中是否包含风控指示
        if isinstance(result, dict):
            code = result.get('code')
            if code in [-352, -503, -799]:
                return True
            
            message = result.get('message', '').lower()
            if any(keyword in message for keyword in ['频繁', '限制', 'limit', 'control']):
                return True
        
        return False
    
    def _should_take_break(self) -> bool:
        """判断是否应该主动休息"""
        # 如果最近失败率高，主动休息
        if len(self.failure_window) >= 5:
            recent_failure_rate = sum(self.failure_window[-5:]) / 5
            if recent_failure_rate > 0.4:  # 40%失败率
                return True
        
        # 如果响应时间过长，主动休息
        if len(self.recent_response_times) >= 3:
            avg_response_time = sum(self.recent_response_times[-3:]) / 3
            if avg_response_time > 5.0:  # 响应时间超过5秒
                return True
        
        return False
    
    def _record_success(self, response_time: float):
        """记录成功请求"""
        self.stats["successful_requests"] += 1
        self.stats["total_time"] += response_time
        self.stats["avg_response_time"] = self.stats["total_time"] / self.stats["total_requests"]
        
        # 更新响应时间历史
        self.recent_response_times.append(response_time)
        if len(self.recent_response_times) > 10:  # 保持较小的历史记录
            self.recent_response_times.pop(0)
        
        # 更新失败窗口
        self.failure_window.append(0)
        if len(self.failure_window) > self.config.failure_window_size:
            self.failure_window.pop(0)
        
        # 成功时重置某些计数器
        if response_time < 2.0:  # 响应时间正常
            self.current_delay = max(self.current_delay * 0.95, self.config.base_delay)
    
    def _record_failure(self):
        """记录失败请求"""
        self.stats["failed_requests"] += 1
        
        # 更新失败窗口
        self.failure_window.append(1)
        if len(self.failure_window) > self.config.failure_window_size:
            self.failure_window.pop(0)
        
        # 失败时增加延迟
        self.current_delay = min(self.current_delay * 1.2, self.config.max_delay)
    
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
        if len(self.cache) > 500:  # 减小缓存大小
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
            "wind_control_detected": self.wind_control_detected,
            "consecutive_wind_control": self.consecutive_wind_control,
            "recent_failure_rate": sum(self.failure_window[-5:]) / min(5, len(self.failure_window)) if self.failure_window else 0
        })
        
        return stats


# 创建保守优化器实例
def get_conservative_optimizer() -> ConservativePerformanceOptimizer:
    """获取保守性能优化器实例"""
    return ConservativePerformanceOptimizer() 