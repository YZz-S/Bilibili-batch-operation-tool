# -*- coding: utf-8 -*-
"""
高性能同步模块
High Performance Synchronization Module

提供智能的高性能同步策略，结合并发处理、智能风控检测和自适应优化
实现3-5倍的同步速度提升，同时保持数据准确性和避免风控
"""

import asyncio
import aiohttp
import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple, Union
from dataclasses import dataclass
from enum import Enum

from .performance_optimizer import PerformanceOptimizer, OptimizationConfig
from .conservative_optimizer import ConservativePerformanceOptimizer, ConservativeOptimizationConfig
from .logger import get_logger


class SyncStrategy(Enum):
    """同步策略枚举"""
    AGGRESSIVE = "aggressive"  # 激进模式：高并发，快速处理
    BALANCED = "balanced"     # 平衡模式：中等并发，稳定处理
    CONSERVATIVE = "conservative"  # 保守模式：低并发，安全处理
    ADAPTIVE = "adaptive"     # 自适应模式：根据环境动态调整


@dataclass
class HighPerformanceConfig:
    """高性能同步配置"""
    # 策略选择
    initial_strategy: SyncStrategy = SyncStrategy.ADAPTIVE
    auto_strategy_switch: bool = True  # 是否自动切换策略
    
    # 激进模式配置
    aggressive_concurrent: int = 8
    aggressive_batch_size: int = 100
    aggressive_delay: float = 0.1
    
    # 平衡模式配置
    balanced_concurrent: int = 3
    balanced_batch_size: int = 50
    balanced_delay: float = 0.5
    
    # 智能检测
    strategy_switch_threshold: float = 0.5  # 策略切换失败率阈值
    performance_monitor_window: int = 50  # 性能监控窗口大小
    
    # 数据完整性检查
    enable_data_validation: bool = True
    validation_sample_rate: float = 0.1  # 验证采样率
    
    # 智能重试
    smart_retry_enabled: bool = True
    max_strategy_retries: int = 2  # 每种策略最大重试次数


class HighPerformanceSyncManager:
    """高性能同步管理器"""
    
    def __init__(self, config: HighPerformanceConfig = None):
        self.config = config or HighPerformanceConfig()
        self.logger = get_logger()
        
        # 当前策略和优化器
        self.current_strategy = self.config.initial_strategy
        self.current_optimizer = None
        
        # 性能监控
        self.performance_history = []
        self.strategy_performance = {
            SyncStrategy.AGGRESSIVE: [],
            SyncStrategy.BALANCED: [],
            SyncStrategy.CONSERVATIVE: []
        }
        
        # 统计信息
        self.sync_stats = {
            "total_synced": 0,
            "successful_synced": 0,
            "failed_synced": 0,
            "strategy_switches": 0,
            "total_time": 0.0,
            "avg_speed": 0.0,
            "data_validation_passed": 0,
            "data_validation_failed": 0
        }
        
        # 初始化优化器
        self._initialize_optimizer()
    
    def _initialize_optimizer(self):
        """初始化当前策略的优化器"""
        if self.current_strategy == SyncStrategy.AGGRESSIVE:
            config = OptimizationConfig()
            config.max_concurrent_requests = self.config.aggressive_concurrent
            config.batch_size = self.config.aggressive_batch_size
            config.base_delay = self.config.aggressive_delay
            config.min_delay = 0.05
            config.adaptive_delay = True
            self.current_optimizer = PerformanceOptimizer(config)
            
        elif self.current_strategy == SyncStrategy.BALANCED:
            config = OptimizationConfig()
            config.max_concurrent_requests = self.config.balanced_concurrent
            config.batch_size = self.config.balanced_batch_size
            config.base_delay = self.config.balanced_delay
            config.adaptive_delay = True
            self.current_optimizer = PerformanceOptimizer(config)
            
        elif self.current_strategy == SyncStrategy.CONSERVATIVE:
            self.current_optimizer = ConservativePerformanceOptimizer()
            
        elif self.current_strategy == SyncStrategy.ADAPTIVE:
            # 自适应模式从平衡模式开始
            self.current_strategy = SyncStrategy.BALANCED
            self._initialize_optimizer()
            self.current_strategy = SyncStrategy.ADAPTIVE
        
        self.logger.info(f"初始化优化器: {self.current_strategy.value}")
    
    async def sync_following_list(self, 
                                users: List[Dict[str, Any]], 
                                sync_func: Callable,
                                progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """同步关注列表"""
        start_time = time.time()
        total_users = len(users)
        
        self.logger.info(f"开始高性能同步 {total_users} 个用户，策略: {self.current_strategy.value}")
        
        # 执行同步
        results = await self._execute_sync_with_strategy(users, sync_func, progress_callback)
        
        # 计算统计信息
        end_time = time.time()
        total_time = end_time - start_time
        successful_count = sum(1 for success, _ in results if success)
        
        # 更新统计
        self.sync_stats["total_synced"] += total_users
        self.sync_stats["successful_synced"] += successful_count
        self.sync_stats["failed_synced"] += (total_users - successful_count)
        self.sync_stats["total_time"] += total_time
        self.sync_stats["avg_speed"] = self.sync_stats["total_synced"] / self.sync_stats["total_time"] if self.sync_stats["total_time"] > 0 else 0
        
        # 记录性能
        performance_data = {
            "strategy": self.current_strategy,
            "users_count": total_users,
            "success_rate": successful_count / total_users if total_users > 0 else 0,
            "time_taken": total_time,
            "speed": total_users / total_time if total_time > 0 else 0,
            "timestamp": datetime.now()
        }
        self.performance_history.append(performance_data)
        
        # 数据验证
        if self.config.enable_data_validation:
            validation_results = await self._validate_sync_results(results, users)
            self.sync_stats["data_validation_passed"] += validation_results["passed"]
            self.sync_stats["data_validation_failed"] += validation_results["failed"]
        
        self.logger.info(f"同步完成: 成功 {successful_count}/{total_users}, 耗时 {total_time:.2f}秒, 速度 {total_users/total_time:.2f}用户/秒")
        
        return {
            "success": True,
            "total_users": total_users,
            "successful_count": successful_count,
            "failed_count": total_users - successful_count,
            "time_taken": total_time,
            "speed": total_users / total_time if total_time > 0 else 0,
            "strategy_used": self.current_strategy.value,
            "results": results
        }
    
    async def _execute_sync_with_strategy(self, 
                                        users: List[Dict[str, Any]], 
                                        sync_func: Callable,
                                        progress_callback: Optional[Callable] = None) -> List[Tuple[bool, Any]]:
        """使用当前策略执行同步"""
        strategy_attempts = 0
        max_attempts = self.config.max_strategy_retries
        
        while strategy_attempts < max_attempts:
            try:
                # 根据策略选择处理方法
                if self.current_strategy == SyncStrategy.CONSERVATIVE:
                    results = await self.current_optimizer.process_users_conservatively(
                        users, sync_func, progress_callback
                    )
                else:
                    results = await self.current_optimizer.process_users_concurrently(
                        users, sync_func, progress_callback
                    )
                
                # 检查结果质量
                success_rate = sum(1 for success, _ in results if success) / len(results) if results else 0
                
                # 如果成功率太低且启用自动策略切换，尝试切换策略
                if (success_rate < self.config.strategy_switch_threshold and 
                    self.config.auto_strategy_switch and 
                    strategy_attempts < max_attempts - 1):
                    
                    self.logger.warning(f"当前策略 {self.current_strategy.value} 成功率过低 ({success_rate:.2%})，尝试切换策略")
                    await self._switch_to_safer_strategy()
                    strategy_attempts += 1
                    continue
                
                return results
                
            except Exception as e:
                self.logger.error(f"策略 {self.current_strategy.value} 执行失败: {e}")
                strategy_attempts += 1
                
                if strategy_attempts < max_attempts:
                    await self._switch_to_safer_strategy()
                else:
                    raise e
        
        raise Exception(f"所有策略尝试失败，最大尝试次数: {max_attempts}")
    
    async def _switch_to_safer_strategy(self):
        """切换到更安全的策略"""
        old_strategy = self.current_strategy
        
        if self.current_strategy == SyncStrategy.AGGRESSIVE:
            self.current_strategy = SyncStrategy.BALANCED
        elif self.current_strategy == SyncStrategy.BALANCED:
            self.current_strategy = SyncStrategy.CONSERVATIVE
        elif self.current_strategy == SyncStrategy.ADAPTIVE:
            self.current_strategy = SyncStrategy.CONSERVATIVE
        # CONSERVATIVE 已经是最安全的，不再切换
        
        if old_strategy != self.current_strategy:
            self.sync_stats["strategy_switches"] += 1
            self.logger.info(f"策略切换: {old_strategy.value} -> {self.current_strategy.value}")
            self._initialize_optimizer()
            
            # 给新策略一些时间初始化
            await asyncio.sleep(2.0)
    
    async def _validate_sync_results(self, results: List[Tuple[bool, Any]], users: List[Dict[str, Any]]) -> Dict[str, int]:
        """验证同步结果的数据完整性"""
        validation_results = {"passed": 0, "failed": 0}
        
        # 采样验证
        sample_size = max(1, int(len(results) * self.config.validation_sample_rate))
        sample_indices = list(range(0, len(results), len(results) // sample_size))[:sample_size]
        
        for i in sample_indices:
            if i < len(results) and results[i][0]:  # 只验证成功的结果
                try:
                    # 验证数据结构完整性
                    result_data = results[i][1]
                    user_data = users[i]
                    
                    if self._is_valid_sync_result(result_data, user_data):
                        validation_results["passed"] += 1
                    else:
                        validation_results["failed"] += 1
                        self.logger.warning(f"数据验证失败: 用户 {user_data.get('uid', 'unknown')}")
                        
                except Exception as e:
                    validation_results["failed"] += 1
                    self.logger.error(f"数据验证异常: {e}")
        
        return validation_results
    
    def _is_valid_sync_result(self, result_data: Any, user_data: Dict[str, Any]) -> bool:
        """检查同步结果是否有效"""
        if not result_data:
            return False
        
        # 检查基本数据结构
        if isinstance(result_data, dict):
            # 检查是否包含必要字段
            required_fields = ['uid', 'uname']
            for field in required_fields:
                if field not in result_data and field not in user_data:
                    return False
            
            # 检查UID一致性
            result_uid = result_data.get('uid') or result_data.get('mid')
            user_uid = user_data.get('uid') or user_data.get('mid')
            if result_uid and user_uid and str(result_uid) != str(user_uid):
                return False
        
        return True
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        report = {
            "sync_stats": self.sync_stats.copy(),
            "current_strategy": self.current_strategy.value,
            "performance_history": self.performance_history[-10:],  # 最近10次记录
            "optimizer_stats": self.current_optimizer.get_performance_stats() if self.current_optimizer else {}
        }
        
        # 计算策略性能统计
        strategy_stats = {}
        for strategy, performances in self.strategy_performance.items():
            if performances:
                avg_success_rate = sum(p["success_rate"] for p in performances) / len(performances)
                avg_speed = sum(p["speed"] for p in performances) / len(performances)
                strategy_stats[strategy.value] = {
                    "avg_success_rate": avg_success_rate,
                    "avg_speed": avg_speed,
                    "usage_count": len(performances)
                }
        
        report["strategy_performance"] = strategy_stats
        
        return report
    
    def reset_stats(self):
        """重置统计信息"""
        self.sync_stats = {
            "total_synced": 0,
            "successful_synced": 0,
            "failed_synced": 0,
            "strategy_switches": 0,
            "total_time": 0.0,
            "avg_speed": 0.0,
            "data_validation_passed": 0,
            "data_validation_failed": 0
        }
        self.performance_history.clear()
        for strategy_list in self.strategy_performance.values():
            strategy_list.clear()
        
        if self.current_optimizer:
            self.current_optimizer.reset_stats()
    
    async def optimize_for_environment(self, test_users: List[Dict[str, Any]], test_func: Callable) -> SyncStrategy:
        """为当前环境优化策略选择"""
        self.logger.info("开始环境优化测试...")
        
        # 测试样本（取前10个用户）
        test_sample = test_users[:min(10, len(test_users))]
        strategy_results = {}
        
        # 测试不同策略
        for strategy in [SyncStrategy.AGGRESSIVE, SyncStrategy.BALANCED, SyncStrategy.CONSERVATIVE]:
            try:
                self.logger.info(f"测试策略: {strategy.value}")
                old_strategy = self.current_strategy
                self.current_strategy = strategy
                self._initialize_optimizer()
                
                start_time = time.time()
                results = await self._execute_sync_with_strategy(test_sample, test_func)
                end_time = time.time()
                
                success_rate = sum(1 for success, _ in results if success) / len(results) if results else 0
                speed = len(test_sample) / (end_time - start_time) if end_time > start_time else 0
                
                strategy_results[strategy] = {
                    "success_rate": success_rate,
                    "speed": speed,
                    "score": success_rate * 0.7 + (speed / 10) * 0.3  # 成功率权重70%，速度权重30%
                }
                
                self.logger.info(f"策略 {strategy.value} 测试结果: 成功率 {success_rate:.2%}, 速度 {speed:.2f}用户/秒")
                
                # 恢复原策略
                self.current_strategy = old_strategy
                
                # 测试间隔
                await asyncio.sleep(5.0)
                
            except Exception as e:
                self.logger.error(f"策略 {strategy.value} 测试失败: {e}")
                strategy_results[strategy] = {"success_rate": 0, "speed": 0, "score": 0}
        
        # 选择最佳策略
        best_strategy = max(strategy_results.keys(), key=lambda s: strategy_results[s]["score"])
        
        self.logger.info(f"环境优化完成，推荐策略: {best_strategy.value}")
        self.logger.info(f"策略评分: {strategy_results}")
        
        # 应用最佳策略
        self.current_strategy = best_strategy
        self._initialize_optimizer()
        
        return best_strategy


# 创建全局实例
_high_performance_sync_manager = None


def get_high_performance_sync_manager(config: HighPerformanceConfig = None) -> HighPerformanceSyncManager:
    """获取高性能同步管理器实例"""
    global _high_performance_sync_manager
    if _high_performance_sync_manager is None or config is not None:
        _high_performance_sync_manager = HighPerformanceSyncManager(config)
    return _high_performance_sync_manager


# 便捷函数
async def high_performance_sync(users: List[Dict[str, Any]], 
                              sync_func: Callable,
                              config: HighPerformanceConfig = None,
                              progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
    """高性能同步便捷函数"""
    manager = get_high_performance_sync_manager(config)
    return await manager.sync_following_list(users, sync_func, progress_callback)