"""
Claude-Hive Configuration Management

Handles loading and parsing of worker configuration files.
"""

import os
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

# ============================================================================
# Configuration Models
# ============================================================================

class WorkerConfig(BaseModel):
    """Configuration for a single worker"""
    name: str
    host: str
    port: int = 8765
    capabilities: list[str] = []
    tags: list[str] = []

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

class RoutingRule(BaseModel):
    """Routing rule for task distribution"""
    pattern: str
    worker: str

class HiveConfig(BaseModel):
    """Main Hive configuration"""
    workers: dict[str, WorkerConfig] = {}
    routing: list[RoutingRule] = []
    default_worker: Optional[str] = None

# ============================================================================
# Configuration Loader
# ============================================================================

DEFAULT_CONFIG_PATHS = [
    Path.home() / ".claude-hive" / "config.yaml",
    Path.home() / ".claude-hive" / "config.yml",
    Path.cwd() / "claude-hive.yaml",
    Path.cwd() / "claude-hive.yml",
]

def find_config_file() -> Optional[Path]:
    """Find configuration file in default locations"""
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return path
    return None

def load_config(config_path: Optional[str] = None) -> HiveConfig:
    """Load configuration from file"""

    # Determine config path
    if config_path:
        path = Path(config_path).expanduser()
    else:
        path = find_config_file()

    if not path or not path.exists():
        # Return empty config if no file found
        return HiveConfig()

    # Load YAML
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    # Parse workers
    workers = {}
    for name, worker_data in data.get("workers", {}).items():
        if isinstance(worker_data, dict):
            workers[name] = WorkerConfig(
                name=name,
                host=worker_data.get("host", "localhost"),
                port=worker_data.get("port", 8765),
                capabilities=worker_data.get("capabilities", []),
                tags=worker_data.get("tags", [])
            )

    # Parse routing rules
    routing = []
    for rule in data.get("routing", []):
        if isinstance(rule, dict):
            if "pattern" in rule and "worker" in rule:
                routing.append(RoutingRule(
                    pattern=rule["pattern"],
                    worker=rule["worker"]
                ))
            elif "default" in rule:
                # Handle default worker
                pass

    # Get default worker
    default_worker = None
    for rule in data.get("routing", []):
        if isinstance(rule, dict) and "default" in rule:
            default_worker = rule["default"]
            break

    if not default_worker and workers:
        default_worker = list(workers.keys())[0]

    return HiveConfig(
        workers=workers,
        routing=routing,
        default_worker=default_worker
    )

# ============================================================================
# Router
# ============================================================================

class TaskRouter:
    """Routes tasks to appropriate workers based on patterns"""

    def __init__(self, config: HiveConfig):
        self.config = config
        self._compiled_patterns: list[tuple[re.Pattern, str]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile routing patterns for faster matching"""
        for rule in self.config.routing:
            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE)
                self._compiled_patterns.append((pattern, rule.worker))
            except re.error:
                # Invalid regex, skip
                pass

    def route(self, task: str) -> Optional[str]:
        """Route a task to the appropriate worker"""

        # Check patterns
        for pattern, worker in self._compiled_patterns:
            if pattern.search(task):
                if worker in self.config.workers:
                    return worker

        # Return default worker
        return self.config.default_worker

    def get_worker(self, name: str) -> Optional[WorkerConfig]:
        """Get worker configuration by name"""
        return self.config.workers.get(name)

    def list_workers(self) -> list[WorkerConfig]:
        """List all configured workers"""
        return list(self.config.workers.values())
