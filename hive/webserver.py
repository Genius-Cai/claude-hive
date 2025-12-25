#!/usr/bin/env python3
"""
Claude-Hive Dashboard Web Server

Serves the monitoring dashboard and provides API endpoints.
The dashboard connects directly to workers for SSE - no token overhead.
"""

import asyncio
import webbrowser
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Configuration
DEFAULT_CONFIG_PATH = Path.home() / ".claude-hive" / "config.yaml"
WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(
    title="Claude-Hive Dashboard",
    description="Real-time monitoring dashboard for Claude-Hive workers",
    version="0.3.0"
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load hive configuration"""
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {"workers": {}}

@app.get("/")
async def index():
    """Serve the dashboard HTML"""
    return FileResponse(WEB_DIR / "index.html")

@app.get("/api/config")
async def get_config():
    """Return worker configuration for the dashboard"""
    config = load_config()
    # Only return what the dashboard needs (no passwords)
    workers = {}
    for name, worker in config.get("workers", {}).items():
        workers[name] = {
            "host": worker.get("host"),
            "port": worker.get("port", 8765),
            "capabilities": worker.get("capabilities", []),
            "tags": worker.get("tags", [])
        }
    return {"workers": workers}

@app.get("/api/workers")
async def list_workers():
    """List all workers with their connection info"""
    config = load_config()
    workers = []
    for name, worker in config.get("workers", {}).items():
        workers.append({
            "name": name,
            "host": worker.get("host"),
            "port": worker.get("port", 8765),
            "stream_url": f"http://{worker.get('host')}:{worker.get('port', 8765)}/stream",
            "status_url": f"http://{worker.get('host')}:{worker.get('port', 8765)}/status"
        })
    return {"workers": workers}

# Mount static files (CSS, JS)
app.mount("/css", StaticFiles(directory=WEB_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=WEB_DIR / "js"), name="js")

def run_server(
    host: str = "0.0.0.0",
    port: int = 8800,
    open_browser: bool = False
):
    """Run the dashboard server"""
    import uvicorn

    print(f"""
+--------------------------------------------------------------+
|                 Claude-Hive Dashboard                         |
+--------------------------------------------------------------+
|  URL:  http://localhost:{port:<43} |
|                                                              |
|  Workers connect via SSE - zero token overhead               |
+--------------------------------------------------------------+
    """)

    if open_browser:
        asyncio.get_event_loop().call_later(
            1.0,
            lambda: webbrowser.open(f"http://localhost:{port}")
        )

    uvicorn.run(app, host=host, port=port, log_level="info")

def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Claude-Hive Dashboard Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8800, help="Port to bind to")
    parser.add_argument("--open", action="store_true", help="Open browser automatically")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, open_browser=args.open)

if __name__ == "__main__":
    main()
