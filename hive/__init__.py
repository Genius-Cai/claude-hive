"""
Claude-Hive: Distributed Claude Code Orchestration Framework

A lightweight framework for coordinating multiple Claude Code instances
across LAN devices via HTTP API.
"""

__version__ = "0.1.0"
__author__ = "Genius-Cai"

from .config import load_config, HiveConfig, WorkerConfig, TaskRouter
from .client import HiveClient, WorkerClient, TaskResult, WorkerStatus

__all__ = [
    "load_config",
    "HiveConfig",
    "WorkerConfig",
    "TaskRouter",
    "HiveClient",
    "WorkerClient",
    "TaskResult",
    "WorkerStatus",
]
