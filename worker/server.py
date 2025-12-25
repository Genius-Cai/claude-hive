#!/usr/bin/env python3
"""
Claude-Hive Worker Server

A lightweight HTTP API server that wraps Claude Code CLI,
providing session persistence and remote task execution.

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
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
        """Execute a task using Claude Code CLI"""

        start_time = time.time()

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
            # Run Claude Code
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            execution_time = time.time() - start_time

            # Parse output
            output = result.stdout
            new_session_id = None

            # Try to extract session_id from JSON output
            try:
                # Claude Code JSON output may have multiple JSON objects
                for line in output.strip().split('\n'):
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
            self._log_history(task, output, execution_time)

            # Ensure result is always a valid string
            final_result = output if result.returncode == 0 else result.stderr
            if final_result is None:
                final_result = result.stdout or result.stderr or "(No output)"

            return TaskResponse(
                success=result.returncode == 0,
                result=final_result,
                session_id=new_session_id or session_id,
                execution_time=execution_time,
                timestamp=datetime.now().isoformat()
            )

        except subprocess.TimeoutExpired:
            return TaskResponse(
                success=False,
                result=f"Task timed out after {timeout} seconds",
                execution_time=time.time() - start_time,
                timestamp=datetime.now().isoformat()
            )
        except FileNotFoundError:
            return TaskResponse(
                success=False,
                result="Claude Code CLI not found. Please install: npm install -g @anthropic-ai/claude-code",
                execution_time=time.time() - start_time,
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            # Catch-all for any unexpected errors - return gracefully instead of 500
            return TaskResponse(
                success=False,
                result=f"Unexpected error during execution: {type(e).__name__}: {str(e)}",
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
start_time = time.time()

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
        uptime=time.time() - start_time,
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
