#!/usr/bin/env python3
"""
Claude-Hive Worker Server

A lightweight HTTP API server that wraps Claude Code CLI,
providing session persistence and remote task execution.

Features:
- Session persistence across tasks
- Real-time SSE streaming for monitoring
- Autonomous problem solving mode

Usage:
    python server.py [--host 0.0.0.0] [--port 8765]
"""

import asyncio
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Set
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ============================================================================
# Configuration
# ============================================================================

HIVE_DIR = Path.home() / ".claude-hive"
SESSION_FILE = HIVE_DIR / "session_id"
HISTORY_FILE = HIVE_DIR / "history.jsonl"

# Ensure directories exist
HIVE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Worker Status & SSE Broadcasting
# ============================================================================

class WorkerStatus(str, Enum):
    """Worker execution status"""
    IDLE = "idle"
    EXECUTING = "executing"
    ERROR = "error"

class OutputBroadcaster:
    """
    Manages SSE connections and broadcasts events to all connected clients.

    This enables real-time monitoring from the web dashboard without
    adding any token consumption (browser connects directly to workers).
    """

    def __init__(self):
        self._clients: Set[asyncio.Queue] = set()
        self._status = WorkerStatus.IDLE
        self._current_task: Optional[str] = None
        self._task_start_time: Optional[float] = None
        self._last_output: str = ""

    @property
    def status(self) -> WorkerStatus:
        return self._status

    @property
    def current_task(self) -> Optional[str]:
        return self._current_task

    def subscribe(self) -> asyncio.Queue:
        """Add a new SSE client"""
        queue: asyncio.Queue = asyncio.Queue()
        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove an SSE client"""
        self._clients.discard(queue)

    async def broadcast(self, event_type: str, data: dict) -> None:
        """Send event to all connected clients"""
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        dead_clients = []
        for client in self._clients:
            try:
                client.put_nowait(event)
            except asyncio.QueueFull:
                dead_clients.append(client)

        # Clean up dead clients
        for client in dead_clients:
            self._clients.discard(client)

    async def task_start(self, task: str) -> None:
        """Signal task execution started"""
        self._status = WorkerStatus.EXECUTING
        self._current_task = task[:100]  # Truncate for display
        self._task_start_time = time.time()
        self._last_output = ""
        await self.broadcast("task_start", {
            "task": self._current_task,
            "status": self._status.value
        })

    async def task_output(self, line: str) -> None:
        """Send a line of output"""
        self._last_output = line[:500]  # Truncate long lines
        await self.broadcast("output", {
            "line": self._last_output,
            "elapsed": time.time() - (self._task_start_time or time.time())
        })

    async def task_complete(self, success: bool, result_preview: str = "") -> None:
        """Signal task completed"""
        elapsed = time.time() - (self._task_start_time or time.time())
        self._status = WorkerStatus.IDLE
        await self.broadcast("task_complete", {
            "success": success,
            "result_preview": result_preview[:200],
            "elapsed": elapsed,
            "status": self._status.value
        })
        self._current_task = None
        self._task_start_time = None

    async def task_error(self, error: str) -> None:
        """Signal task error"""
        self._status = WorkerStatus.ERROR
        await self.broadcast("task_error", {
            "error": error[:200],
            "status": self._status.value
        })

    def get_state(self) -> dict:
        """Get current worker state for /status endpoint"""
        return {
            "status": self._status.value,
            "current_task": self._current_task,
            "elapsed": time.time() - self._task_start_time if self._task_start_time else None,
            "last_output": self._last_output,
            "connected_clients": len(self._clients)
        }

# Global broadcaster instance
broadcaster = OutputBroadcaster()

# ============================================================================
# Models
# ============================================================================

class TaskRequest(BaseModel):
    """Task execution request"""
    task: str
    new_session: bool = False
    timeout: int = 300
    allowed_tools: Optional[list[str]] = None
    autonomous: bool = True  # If True, prepend instructions for autonomous problem solving

class TaskResponse(BaseModel):
    """Task execution response"""
    success: bool
    result: str
    session_id: Optional[str] = None
    execution_time: float
    timestamp: str

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    session_id: Optional[str] = None
    claude_version: Optional[str] = None
    uptime: float
    worker_name: str

class SessionInfo(BaseModel):
    """Session information"""
    session_id: Optional[str] = None
    created_at: Optional[str] = None
    task_count: int = 0

# ============================================================================
# Session Management
# ============================================================================

class SessionManager:
    """Manages Claude Code session persistence"""

    def __init__(self):
        self.task_count = 0
        self.created_at: Optional[datetime] = None
        self._load_session()

    def _load_session(self) -> None:
        """Load session ID from file if exists"""
        if SESSION_FILE.exists():
            try:
                data = json.loads(SESSION_FILE.read_text())
                self.created_at = datetime.fromisoformat(data.get("created_at", ""))
            except (json.JSONDecodeError, ValueError):
                pass

    def get_session_id(self) -> Optional[str]:
        """Get current session ID"""
        if SESSION_FILE.exists():
            try:
                data = json.loads(SESSION_FILE.read_text())
                return data.get("session_id")
            except json.JSONDecodeError:
                return None
        return None

    def save_session_id(self, session_id: str) -> None:
        """Save session ID to file"""
        if not self.created_at:
            self.created_at = datetime.now()

        data = {
            "session_id": session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        SESSION_FILE.write_text(json.dumps(data, indent=2))

    def clear_session(self) -> None:
        """Clear current session"""
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
        self.created_at = None
        self.task_count = 0

    def increment_task_count(self) -> None:
        """Increment task counter"""
        self.task_count += 1

    def get_info(self) -> SessionInfo:
        """Get session information"""
        return SessionInfo(
            session_id=self.get_session_id(),
            created_at=self.created_at.isoformat() if self.created_at else None,
            task_count=self.task_count
        )

# ============================================================================
# Claude Code Executor
# ============================================================================

class ClaudeExecutor:
    """Executes Claude Code CLI commands"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self._claude_version: Optional[str] = None

    def get_claude_version(self) -> Optional[str]:
        """Get Claude Code version"""
        if self._claude_version:
            return self._claude_version

        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self._claude_version = result.stdout.strip()
                return self._claude_version
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    async def execute(
        self,
        task: str,
        new_session: bool = False,
        timeout: int = 300,
        allowed_tools: Optional[list[str]] = None,
        autonomous: bool = True
    ) -> TaskResponse:
        """Execute a task using Claude Code CLI with real-time SSE broadcasting"""

        start_time = time.time()
        original_task = task  # Keep original for display

        # Broadcast task start (for SSE clients / web dashboard)
        await broadcaster.task_start(original_task)

        # Clear session if requested
        if new_session:
            self.session_manager.clear_session()

        # Prepend autonomous problem-solving instructions if enabled
        if autonomous:
            task = f"""You are a remote worker executing a task autonomously.
IMPORTANT: If you encounter any issues (service not running, missing dependencies, etc.):
1. Try to diagnose and fix the problem yourself
2. Start services if needed (e.g., if Ollama is not running, start it)
3. Install missing dependencies if necessary
4. Retry the original task after fixing issues
5. Only report failure if you truly cannot solve the problem

Task: {task}"""

        # Build command
        cmd = ["claude", "-p", task, "--output-format", "json"]

        # Add session resume if available
        session_id = self.session_manager.get_session_id()
        if session_id and not new_session:
            cmd.extend(["--resume", session_id])

        # Add allowed tools if specified
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        try:
            # Run Claude Code with streaming output capture
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            output_lines = []

            async def read_stream(stream, is_stderr=False):
                """Read stream line by line and broadcast to SSE clients"""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').rstrip()
                    if decoded:
                        output_lines.append(decoded)
                        # Broadcast each line to connected dashboard clients
                        await broadcaster.task_output(decoded)

            # Read stdout and stderr concurrently with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout),
                        read_stream(process.stderr, is_stderr=True)
                    ),
                    timeout=timeout
                )
                await process.wait()
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await broadcaster.task_error(f"Task timed out after {timeout}s")
                return TaskResponse(
                    success=False,
                    result=f"Task timed out after {timeout} seconds",
                    execution_time=time.time() - start_time,
                    timestamp=datetime.now().isoformat()
                )

            execution_time = time.time() - start_time

            # Parse output
            output = '\n'.join(output_lines)
            new_session_id = None

            # Try to extract session_id from JSON output
            try:
                for line in output_lines:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if "session_id" in data:
                                new_session_id = data["session_id"]
                            if "result" in data:
                                output = data["result"]
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

            # Save session ID if found
            if new_session_id:
                self.session_manager.save_session_id(new_session_id)

            # Increment task count
            self.session_manager.increment_task_count()

            # Log to history
            self._log_history(original_task, output, execution_time)

            # Ensure result is always a valid string
            final_result = output if process.returncode == 0 else output
            if not final_result:
                final_result = "(No output)"

            success = process.returncode == 0

            # Broadcast task completion
            await broadcaster.task_complete(success, final_result[:200])

            return TaskResponse(
                success=success,
                result=final_result,
                session_id=new_session_id or session_id,
                execution_time=execution_time,
                timestamp=datetime.now().isoformat()
            )

        except FileNotFoundError:
            error_msg = "Claude Code CLI not found. Please install: npm install -g @anthropic-ai/claude-code"
            await broadcaster.task_error(error_msg)
            return TaskResponse(
                success=False,
                result=error_msg,
                execution_time=time.time() - start_time,
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            # Catch-all for any unexpected errors
            error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
            await broadcaster.task_error(error_msg)
            return TaskResponse(
                success=False,
                result=error_msg,
                execution_time=time.time() - start_time,
                timestamp=datetime.now().isoformat()
            )

    def _log_history(self, task: str, result: str, execution_time: float) -> None:
        """Log task to history file"""
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "task": task[:200],  # Truncate for storage
                "result_preview": result[:200] if result else "",
                "execution_time": execution_time,
                "session_id": self.session_manager.get_session_id()
            }
            with open(HISTORY_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Non-critical, ignore errors

# ============================================================================
# FastAPI Application
# ============================================================================

# Initialize components
session_manager = SessionManager()
executor = ClaudeExecutor(session_manager)
server_start_time = time.time()

# Get worker name from environment or hostname (cross-platform)
import platform
WORKER_NAME = os.environ.get("HIVE_WORKER_NAME", platform.node())

# Create FastAPI app
app = FastAPI(
    title="Claude-Hive Worker",
    description="Distributed Claude Code execution worker",
    version="0.1.0"
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - returns health status"""
    return await health()

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse(
        status="ok",
        session_id=session_manager.get_session_id(),
        claude_version=executor.get_claude_version(),
        uptime=time.time() - server_start_time,
        worker_name=WORKER_NAME
    )

@app.post("/task", response_model=TaskResponse)
async def execute_task(request: TaskRequest):
    """Execute a task using Claude Code"""
    if not request.task.strip():
        raise HTTPException(status_code=400, detail="Task cannot be empty")

    return await executor.execute(
        task=request.task,
        new_session=request.new_session,
        timeout=request.timeout,
        allowed_tools=request.allowed_tools,
        autonomous=request.autonomous
    )

@app.get("/session", response_model=SessionInfo)
async def get_session():
    """Get current session information"""
    return session_manager.get_info()

@app.post("/session/new", response_model=SessionInfo)
async def new_session():
    """Start a new session (clear current)"""
    session_manager.clear_session()
    return session_manager.get_info()

@app.get("/history")
async def get_history(limit: int = 20):
    """Get recent task history"""
    history = []
    if HISTORY_FILE.exists():
        try:
            lines = HISTORY_FILE.read_text().strip().split('\n')
            for line in lines[-limit:]:
                if line.strip():
                    try:
                        history.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
    return {"history": history}

# ============================================================================
# SSE Streaming Endpoints (for Web Dashboard - zero token overhead)
# ============================================================================

@app.get("/status")
async def get_status():
    """
    Get current worker status.
    Used by dashboard for initial state and polling fallback.
    """
    return {
        "worker_name": WORKER_NAME,
        "uptime": time.time() - server_start_time,
        "claude_version": executor.get_claude_version(),
        **broadcaster.get_state()
    }

@app.get("/stream")
async def stream_events():
    """
    SSE endpoint for real-time task output streaming.

    The web dashboard connects directly to each worker's /stream endpoint.
    This does NOT go through Controller Claude, so it adds ZERO token overhead.

    Event types:
    - status: Worker status change (idle/executing/error)
    - task_start: Task execution started
    - output: Real-time output line from Claude
    - task_complete: Task finished successfully
    - task_error: Task failed with error
    """
    queue = broadcaster.subscribe()

    async def event_generator():
        try:
            # Send initial status
            initial = {
                "type": "status",
                "worker_name": WORKER_NAME,
                "timestamp": datetime.now().isoformat(),
                **broadcaster.get_state()
            }
            yield f"data: {json.dumps(initial)}\n\n"

            # Stream events
            while True:
                try:
                    # Wait for events with timeout (for keepalive)
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the worker server"""
    import argparse

    parser = argparse.ArgumentParser(description="Claude-Hive Worker Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind to")
    parser.add_argument("--name", default=None, help="Worker name")
    args = parser.parse_args()

    if args.name:
        os.environ["HIVE_WORKER_NAME"] = args.name

    import uvicorn

    # Use ASCII-safe banner for Windows compatibility
    banner = f"""
+--------------------------------------------------------------+
|                    Claude-Hive Worker                        |
+--------------------------------------------------------------+
|  Worker Name: {WORKER_NAME:<46} |
|  Listening:   http://{args.host}:{args.port:<36} |
|  Health:      http://{args.host}:{args.port}/health{' '*26} |
+--------------------------------------------------------------+
    """
    print(banner)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")

if __name__ == "__main__":
    main()
