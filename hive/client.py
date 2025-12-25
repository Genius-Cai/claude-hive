"""
Claude-Hive Worker Client

HTTP client for communicating with Hive workers.
"""

import asyncio
from typing import Optional

import httpx
from pydantic import BaseModel

from .config import WorkerConfig

# ============================================================================
# Response Models
# ============================================================================

class TaskResult(BaseModel):
    """Result from task execution"""
    success: bool
    result: str
    session_id: Optional[str] = None
    execution_time: float
    timestamp: str
    worker: str

class WorkerStatus(BaseModel):
    """Worker health status"""
    name: str
    url: str
    online: bool
    session_id: Optional[str] = None
    claude_version: Optional[str] = None
    uptime: Optional[float] = None
    error: Optional[str] = None

# ============================================================================
# Worker Client
# ============================================================================

class WorkerClient:
    """HTTP client for a single worker"""

    def __init__(self, config: WorkerConfig, timeout: float = 30.0):
        self.config = config
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.url,
                timeout=httpx.Timeout(self.timeout, read=300.0)
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health(self) -> WorkerStatus:
        """Check worker health"""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            response.raise_for_status()
            data = response.json()

            return WorkerStatus(
                name=self.config.name,
                url=self.config.url,
                online=True,
                session_id=data.get("session_id"),
                claude_version=data.get("claude_version"),
                uptime=data.get("uptime")
            )
        except Exception as e:
            return WorkerStatus(
                name=self.config.name,
                url=self.config.url,
                online=False,
                error=str(e)
            )

    async def execute(
        self,
        task: str,
        new_session: bool = False,
        timeout: int = 300,
        allowed_tools: Optional[list[str]] = None
    ) -> TaskResult:
        """Execute a task on this worker"""
        try:
            client = await self._get_client()

            payload = {
                "task": task,
                "new_session": new_session,
                "timeout": timeout
            }
            if allowed_tools:
                payload["allowed_tools"] = allowed_tools

            response = await client.post("/task", json=payload)
            response.raise_for_status()
            data = response.json()

            return TaskResult(
                success=data.get("success", False),
                result=data.get("result", ""),
                session_id=data.get("session_id"),
                execution_time=data.get("execution_time", 0),
                timestamp=data.get("timestamp", ""),
                worker=self.config.name
            )
        except httpx.TimeoutException:
            return TaskResult(
                success=False,
                result=f"Request to {self.config.name} timed out",
                execution_time=0,
                timestamp="",
                worker=self.config.name
            )
        except Exception as e:
            return TaskResult(
                success=False,
                result=f"Error communicating with {self.config.name}: {str(e)}",
                execution_time=0,
                timestamp="",
                worker=self.config.name
            )

    async def new_session(self) -> bool:
        """Start a new session on this worker"""
        try:
            client = await self._get_client()
            response = await client.post("/session/new")
            response.raise_for_status()
            return True
        except Exception:
            return False

    async def get_session(self) -> Optional[dict]:
        """Get session info from worker"""
        try:
            client = await self._get_client()
            response = await client.get("/session")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

# ============================================================================
# Hive Client (Multi-Worker)
# ============================================================================

class HiveClient:
    """Client for managing multiple workers"""

    def __init__(self, workers: dict[str, WorkerConfig]):
        self.workers = workers
        self._clients: dict[str, WorkerClient] = {}

    def _get_client(self, name: str) -> Optional[WorkerClient]:
        """Get or create client for a worker"""
        if name not in self.workers:
            return None

        if name not in self._clients:
            self._clients[name] = WorkerClient(self.workers[name])

        return self._clients[name]

    async def close(self) -> None:
        """Close all clients"""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()

    async def status_all(self) -> list[WorkerStatus]:
        """Check health of all workers"""
        tasks = []
        for name in self.workers:
            client = self._get_client(name)
            if client:
                tasks.append(client.health())

        return await asyncio.gather(*tasks)

    async def execute(
        self,
        worker: str,
        task: str,
        new_session: bool = False,
        timeout: int = 300
    ) -> TaskResult:
        """Execute task on a specific worker"""
        client = self._get_client(worker)
        if not client:
            return TaskResult(
                success=False,
                result=f"Worker '{worker}' not found",
                execution_time=0,
                timestamp="",
                worker=worker
            )

        return await client.execute(task, new_session, timeout)

    async def broadcast(
        self,
        task: str,
        new_session: bool = False,
        timeout: int = 300
    ) -> list[TaskResult]:
        """Execute task on all workers"""
        tasks = []
        for name in self.workers:
            client = self._get_client(name)
            if client:
                tasks.append(client.execute(task, new_session, timeout))

        return await asyncio.gather(*tasks)

    async def parallel(
        self,
        task_assignments: list[tuple[str, str]],
        timeout: int = 300
    ) -> list[TaskResult]:
        """Execute multiple tasks in parallel"""
        tasks = []
        for worker, task in task_assignments:
            client = self._get_client(worker)
            if client:
                tasks.append(client.execute(task, timeout=timeout))

        return await asyncio.gather(*tasks)
