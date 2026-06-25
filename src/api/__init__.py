# -*- coding: utf-8 -*-
"""
API路由模块包
API Router Module Package
"""

from .bilibili import router as bilibili_router
from .data import router as data_router
from .analysis import router as analysis_router

__all__ = ["bilibili_router", "data_router", "analysis_router"] 