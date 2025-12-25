# 🐝 Claude-Hive

**Distributed Claude Code Orchestration Framework for LAN Environments**

[English](#overview) | [中文](#概述)

---

## Overview

Claude-Hive is a lightweight framework that enables multiple devices in a LAN to run their own Claude Code instances, coordinated via HTTP API. Each worker maintains its own session context, enabling true distributed AI agent management with persistent memory.

### Why Claude-Hive?

| Problem | Solution |
|---------|----------|
| SSH/expect overhead (400-700ms) | HTTP API (25-50ms) - **15x faster** |
| High token consumption | Local execution, return results only - **50x reduction** |
| No memory between calls | Session persistence per worker |
| Complex expect scripts | Simple HTTP calls |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Hive Controller (Your Mac/PC)                              │
│  - Receives user commands                                   │
│  - Routes tasks to appropriate workers                      │
│  - Aggregates results                                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP API
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ Worker A    │   │ Worker B    │   │ Worker C    │
│ (Docker VM) │   │ (GPU Node)  │   │ (Dev Server)│
│             │   │             │   │             │
│ Claude Code │   │ Claude Code │   │ Claude Code │
│ + Session   │   │ + Session   │   │ + Session   │
│ (Memory!)   │   │ (Memory!)   │   │ (Memory!)   │
└─────────────┘   └─────────────┘   └─────────────┘
```

## Quick Start

### 1. Install Worker (on remote machines)

```bash
# One-line install
curl -sSL https://raw.githubusercontent.com/Genius-Cai/claude-hive/main/scripts/install-worker.sh | bash

# Or manually
pip install fastapi uvicorn pydantic
python worker/server.py --port 8765 --name docker-vm
```

### 2. Install Controller (on your machine)

```bash
git clone https://github.com/Genius-Cai/claude-hive.git
cd claude-hive
pip install -e .
```

### 3. Configure Workers

Create `~/.claude-hive/config.yaml`:

```yaml
workers:
  docker-vm:
    host: 192.168.50.80
    port: 8765
    capabilities: [docker, containers]

  gpu-worker:
    host: 192.168.50.92
    port: 8765
    capabilities: [gpu, ollama]

routing:
  - pattern: "docker|container"
    worker: docker-vm
  - pattern: "gpu|ollama|model"
    worker: gpu-worker
  - default: docker-vm
```

### 4. Use It!

```bash
# Check worker status
hive status

# Send task to specific worker
hive send docker-vm "Check Docker container status"

# Auto-route based on content
hive ask "Restart Jellyfin service"
# → Automatically routes to docker-vm

# Broadcast to all workers
hive broadcast "Check system status"

# Session management
hive session list
hive session new docker-vm
```

## Features

- ✅ **Distributed Execution** - Each worker runs Claude Code locally
- ✅ **Session Persistence** - Workers maintain conversation context
- ✅ **Smart Routing** - Auto-route tasks based on patterns
- ✅ **Lightweight** - Single Python file per worker
- ✅ **No Authentication** - Designed for trusted LANs
- ✅ **Bilingual** - Supports English and Chinese patterns

## API Reference

### Worker Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/task` | POST | Execute task |
| `/session` | GET | Get session info |
| `/session/new` | POST | Start new session |
| `/history` | GET | Get task history |

### Task Request

```json
POST /task
{
  "task": "Check Docker containers",
  "new_session": false,
  "timeout": 300
}
```

### Task Response

```json
{
  "success": true,
  "result": "...",
  "session_id": "abc123",
  "execution_time": 2.3,
  "timestamp": "2024-12-25T12:00:00"
}
```

## License

MIT License - see [LICENSE](LICENSE)

---

# 概述

Claude-Hive 是一个轻量级框架，让局域网内的多台设备各自运行 Claude Code，通过 HTTP API 协调工作。每个 Worker 维护自己的会话上下文，实现真正的分布式 AI Agent 管理。

### 为什么需要 Claude-Hive？

| 问题 | 解决方案 |
|------|----------|
| SSH/expect 开销 (400-700ms) | HTTP API (25-50ms) - **快 15 倍** |
| Token 消耗大 | 本地执行，只返回结果 - **减少 50 倍** |
| 调用之间无记忆 | 每个 Worker 持久化 Session |
| expect 脚本复杂 | 简单 HTTP 调用 |

## 快速开始

### 1. 安装 Worker（在远程机器上）

```bash
# 一键安装
curl -sSL https://raw.githubusercontent.com/Genius-Cai/claude-hive/main/scripts/install-worker.sh | bash

# 或手动安装
pip install fastapi uvicorn pydantic
python worker/server.py --port 8765 --name docker-vm
```

### 2. 安装 Controller（在你的机器上）

```bash
git clone https://github.com/Genius-Cai/claude-hive.git
cd claude-hive
pip install -e .
```

### 3. 配置 Workers

创建 `~/.claude-hive/config.yaml`:

```yaml
workers:
  docker-vm:
    host: 192.168.50.80
    port: 8765
    capabilities: [docker, containers]

  gpu-worker:
    host: 192.168.50.92
    port: 8765
    capabilities: [gpu, ollama]

routing:
  - pattern: "docker|容器|服务"
    worker: docker-vm
  - pattern: "gpu|ollama|模型"
    worker: gpu-worker
  - default: docker-vm
```

### 4. 开始使用！

```bash
# 检查 Worker 状态
hive status

# 发送任务到特定 Worker
hive send docker-vm "检查 Docker 容器状态"

# 自动路由
hive ask "重启 Jellyfin 服务"
# → 自动路由到 docker-vm

# 广播到所有 Workers
hive broadcast "检查系统状态"

# Session 管理
hive session list
hive session new docker-vm
```

## 特性

- ✅ **分布式执行** - 每个 Worker 本地运行 Claude Code
- ✅ **Session 持久化** - Worker 保持对话上下文
- ✅ **智能路由** - 根据模式自动路由任务
- ✅ **轻量级** - 每个 Worker 只需一个 Python 文件
- ✅ **无需认证** - 为可信局域网设计
- ✅ **双语支持** - 支持中英文匹配模式

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
