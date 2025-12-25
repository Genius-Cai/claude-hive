# Claude-Hive Web UI / Log Visualization Design

## Overview

A lightweight web dashboard for visualizing Claude-Hive task execution, conversation history, and system metrics.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude-Hive Controller                        │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   CLI        │  │   Router     │  │   Event Logger       │   │
│  │   (hive cmd) │  │              │  │   (SQLite/JSON)      │   │
│  └──────┬───────┘  └──────────────┘  └──────────┬───────────┘   │
│         │                                        │               │
│         │  ┌─────────────────────────────────────┤               │
│         │  │                                     │               │
│         ▼  ▼                                     ▼               │
│  ┌──────────────┐                       ┌──────────────┐         │
│  │  Task Queue  │──────────────────────▶│  Web Server  │         │
│  │              │  (SSE/WebSocket)      │  (FastAPI)   │         │
│  └──────────────┘                       └──────┬───────┘         │
│                                                 │                │
└─────────────────────────────────────────────────│────────────────┘
                                                  │ :8800
                                                  ▼
                                         ┌──────────────┐
                                         │  Browser UI  │
                                         │  (Vue/React) │
                                         └──────────────┘
```

## Components

### 1. Event Logger (`hive/logger.py`)

```python
from dataclasses import dataclass
from datetime import datetime
import sqlite3
import json

@dataclass
class TaskEvent:
    id: str
    timestamp: datetime
    event_type: str  # task_sent, task_completed, task_failed, session_new
    worker: str
    task: str
    result: str | None
    duration_ms: int
    tokens_used: int | None
    session_id: str | None

class EventLogger:
    def __init__(self, db_path: str = "~/.claude-hive/events.db"):
        self.db_path = os.path.expanduser(db_path)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    event_type TEXT,
                    worker TEXT,
                    task TEXT,
                    result TEXT,
                    duration_ms INTEGER,
                    tokens_used INTEGER,
                    session_id TEXT
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_worker ON events(worker)')

    def log(self, event: TaskEvent):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.id, event.timestamp.isoformat(), event.event_type,
                event.worker, event.task, event.result, event.duration_ms,
                event.tokens_used, event.session_id
            ))

    def query(self, hours: int = 24, worker: str = None) -> list[TaskEvent]:
        ...
```

### 2. Web Server (`hive/web.py`)

```python
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio

app = FastAPI(title="Claude-Hive Dashboard")

# Serve static frontend
app.mount("/static", StaticFiles(directory="web/dist"), name="static")

@app.get("/")
async def index():
    return HTMLResponse(open("web/dist/index.html").read())

@app.get("/api/events")
async def get_events(hours: int = 24, worker: str = None):
    """Get recent task events"""
    return logger.query(hours=hours, worker=worker)

@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics"""
    return {
        "total_tasks_24h": logger.count(hours=24),
        "success_rate": logger.success_rate(hours=24),
        "avg_duration_ms": logger.avg_duration(hours=24),
        "workers_online": len([w for w in workers if w.is_online]),
        "total_tokens_24h": logger.total_tokens(hours=24)
    }

@app.get("/api/workers")
async def get_workers():
    """Get worker status with recent activity"""
    return [
        {
            "name": w.name,
            "host": w.host,
            "status": "online" if w.is_online else "offline",
            "last_task": logger.last_task(w.name),
            "tasks_24h": logger.count(hours=24, worker=w.name)
        }
        for w in workers
    ]

# Real-time updates via SSE
@app.get("/api/events/stream")
async def event_stream():
    async def generate():
        async for event in event_queue.subscribe():
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### 3. Frontend UI (`web/src/`)

Minimal Vue.js or vanilla JS dashboard:

```
web/
├── index.html
├── css/
│   └── style.css
└── js/
    └── app.js
```

#### Dashboard Layout

```
┌───────────────────────────────────────────────────────────────────┐
│  Claude-Hive Dashboard                              [Auto-refresh]│
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ 127     │  │ 98.5%   │  │ 12.3s   │  │ 3/4     │             │
│  │ Tasks   │  │ Success │  │ Avg Time│  │ Workers │             │
│  │ (24h)   │  │ Rate    │  │         │  │ Online  │             │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘             │
│                                                                   │
├───────────────────────────────────────────────────────────────────┤
│  Workers                                                          │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ docker-vm     ●online   192.168.50.80   45 tasks   2.1s avg ││
│  │ gpu-worker    ●online   192.168.50.92   23 tasks   8.5s avg ││
│  │ dev-server    ○offline  192.168.50.100  --                  ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
├───────────────────────────────────────────────────────────────────┤
│  Recent Tasks                                           [Filter ▼]│
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ 14:32:05  docker-vm  ✓  "检查 Docker 容器状态"     9.2s     ││
│  │ 14:30:12  gpu-worker ✓  "运行 Ollama 推理"        23.5s     ││
│  │ 14:28:45  docker-vm  ✓  "重启 Jellyfin"          12.1s     ││
│  │ 14:25:33  dev-server ✗  "git pull" (timeout)      60.0s     ││
│  │ ...                                                          ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
├───────────────────────────────────────────────────────────────────┤
│  Task Timeline (24h)                                              │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ ████  █████ ███ ██████████ ████  ██ █████ ███████  █        ││
│  │ 00:00      06:00      12:00      18:00      24:00           ││
│  └──────────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────────┘
```

### 4. Integration Points

#### CLI Integration

```python
# hive/cli.py - Add logging to existing commands

from hive.logger import EventLogger, TaskEvent
import uuid

logger = EventLogger()

@cli.command()
def send(worker, task):
    event_id = str(uuid.uuid4())
    start = time.time()

    try:
        result = controller.send(worker, task)
        duration = int((time.time() - start) * 1000)

        logger.log(TaskEvent(
            id=event_id,
            timestamp=datetime.now(),
            event_type="task_completed",
            worker=worker,
            task=task,
            result=result[:500],  # Truncate for storage
            duration_ms=duration,
            tokens_used=None,  # Extract from response if available
            session_id=None
        ))

        click.echo(result)
    except Exception as e:
        logger.log(TaskEvent(
            id=event_id,
            timestamp=datetime.now(),
            event_type="task_failed",
            worker=worker,
            task=task,
            result=str(e),
            duration_ms=int((time.time() - start) * 1000),
            tokens_used=None,
            session_id=None
        ))
        raise
```

#### CLI Command to Start Dashboard

```bash
# Start web dashboard
hive web --port 8800

# Open in browser automatically
hive web --port 8800 --open
```

## Implementation Plan

### Phase 1: Basic Logging (v0.2)
- [ ] Create `hive/logger.py` with SQLite backend
- [ ] Add logging calls to CLI commands
- [ ] Add `hive logs` command for CLI viewing

### Phase 2: Web Dashboard (v0.3)
- [ ] Create FastAPI web server
- [ ] Build minimal HTML/CSS/JS frontend
- [ ] Add `hive web` command
- [ ] Real-time updates via SSE

### Phase 3: Enhanced Features (v0.4)
- [ ] Task detail view (full output, session context)
- [ ] Worker management (restart, reset session)
- [ ] Export logs to JSON/CSV
- [ ] Metrics and charts

## Technology Choices

| Component | Choice | Reason |
|-----------|--------|--------|
| Database | SQLite | Zero config, file-based |
| Web Server | FastAPI | Already a dependency |
| Frontend | Vanilla JS + PicoCSS | Minimal, no build step |
| Real-time | Server-Sent Events | Simple, native browser support |
| Charts | Chart.js | Lightweight, no deps |

## File Structure

```
hive/
├── logger.py          # Event logging
├── web.py             # Web server
└── web/               # Frontend assets
    ├── index.html
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```

## Security Considerations

1. **Local only by default**: Bind to `127.0.0.1`
2. **Optional auth**: Simple token-based auth for LAN exposure
3. **Read-only dashboard**: No task execution from web (for now)

## Example Usage

```bash
# Start dashboard (local only)
hive web

# Start dashboard (LAN accessible)
hive web --host 0.0.0.0 --port 8800

# View recent logs in CLI
hive logs --last 20

# Export logs
hive logs --export json > events.json
```

---

This design keeps the dashboard lightweight while providing essential visibility into Claude-Hive operations.
