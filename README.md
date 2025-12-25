# Claude-Hive

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

### Key Features

- **Distributed Execution** - Each worker runs Claude Code locally
- **Session Persistence** - Workers maintain conversation context
- **Smart Routing** - Auto-route tasks based on patterns
- **Network Discovery** - Auto-detect devices in your LAN
- **One-Click Deploy** - Deploy workers with a single command
- **Claude Code Native** - Built-in CLAUDE.md and AGENTS.md for AI-assisted deployment
- **Bilingual Support** - Supports English and Chinese patterns

### Architecture

```
                    ┌─────────────────────────────┐
                    │  Hive Controller            │
                    │  (Your Mac/PC)              │
                    └──────────────┬──────────────┘
                                   │ HTTP API (~25ms)
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │ Worker A    │         │ Worker B    │         │ Worker C    │
    │ Docker VM   │         │ GPU Node    │         │ Dev Server  │
    │             │         │             │         │             │
    │ Claude Code │         │ Claude Code │         │ Claude Code │
    │ + Session   │         │ + Session   │         │ + Session   │
    └─────────────┘         └─────────────┘         └─────────────┘
```

---

## Claude Code Integration

Claude-Hive is designed to be deployed using Claude Code itself. Just clone the repo and let Claude Code read the built-in `CLAUDE.md` to understand how to deploy!

### Deploy with Claude Code (Recommended)

1. Clone the repository
2. Open Claude Code in the project directory
3. Say: *"Help me deploy claude-hive to my homelab"*

Claude Code will:
- Read `CLAUDE.md` and understand the project
- Ask for your network details
- Discover devices in your LAN
- Deploy workers automatically
- Configure routing rules

### Example Prompts

```
# Basic deployment
"Deploy claude-hive workers to 192.168.1.100 and 192.168.1.101"

# Network discovery
"Scan my network 192.168.50.0/24 and deploy workers to all Linux servers"

# Homelab setup
"Set up claude-hive for my homelab:
 - Docker VM at .80 for container management
 - GPU server at .92 for AI/ML tasks
 - Dev server at .100 for development"

# Status check
"Check the status of all my claude-hive workers"
```

---

## Quick Start

### Option 1: Automatic Deployment

```bash
# Clone and install
git clone https://github.com/Genius-Cai/claude-hive.git
cd claude-hive
pip install -e .

# Discover devices on your network
hive discover 192.168.50.0/24 -u your_user -p your_pass

# Deploy to discovered devices
hive deploy 192.168.50.80 --name docker-vm -u your_user -p your_pass
hive deploy 192.168.50.92 --name gpu-worker -u your_user -p your_pass

# Verify deployment
hive status
```

### Option 2: Manual Installation

#### On Controller (your machine):
```bash
git clone https://github.com/Genius-Cai/claude-hive.git
cd claude-hive
pip install -e .
```

#### On Workers (remote machines):
```bash
# Install dependencies
pip3 install fastapi uvicorn httpx pydantic

# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Download and run worker
mkdir -p ~/claude-hive-worker
curl -o ~/claude-hive-worker/server.py https://raw.githubusercontent.com/Genius-Cai/claude-hive/main/worker/server.py
python3 ~/claude-hive-worker/server.py --name my-worker --port 8765
```

### Configuration

Create `~/.claude-hive/config.yaml`:

```yaml
workers:
  docker-vm:
    host: 192.168.50.80
    port: 8765
    capabilities: [docker, containers, services]

  gpu-worker:
    host: 192.168.50.92
    port: 8765
    capabilities: [gpu, ollama, ml]

  dev-server:
    host: 192.168.50.100
    port: 8765
    capabilities: [git, build, test]

routing:
  - pattern: "docker|container|service|compose"
    worker: docker-vm
  - pattern: "gpu|ollama|model|inference|train"
    worker: gpu-worker
  - pattern: "git|code|build|test|compile"
    worker: dev-server

default_worker: docker-vm
```

---

## Usage

### CLI Commands

| Command | Description |
|---------|-------------|
| `hive status` | Check all worker status |
| `hive send <worker> <task>` | Send task to specific worker |
| `hive ask <task>` | Auto-route task based on content |
| `hive broadcast <task>` | Send task to all workers |
| `hive session list` | List all sessions |
| `hive session new <worker>` | Start new session on worker |
| `hive discover <subnet>` | Scan network for devices |
| `hive deploy <ip>` | Deploy worker to remote machine |
| `hive workers` | List configured workers |
| `hive routes` | Show routing rules |

### Examples

```bash
# Check Docker containers on docker-vm
hive send docker-vm "List all running Docker containers"

# Auto-route (routes to docker-vm based on keywords)
hive ask "Restart the Jellyfin service"

# GPU task (routes to gpu-worker)
hive ask "Run inference with Ollama using llama3"

# Development task (routes to dev-server)
hive ask "Pull latest code and run tests"

# Check all servers
hive broadcast "Check disk space and memory usage"

# Session with memory
hive send docker-vm "What containers did I ask about earlier?"
# Worker remembers previous conversation!
```

---

## /hive Skill for Claude Code

Install the `/hive` skill to use Claude-Hive commands directly in Claude Code:

```bash
hive install-skill
# Or manually copy:
cp skills/hive.md ~/.claude/commands/hive.md
```

Now in Claude Code:
```
/hive status
/hive ask "check docker containers"
/hive send gpu-worker "run ollama inference"
```

---

## API Reference

### Worker Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with session info |
| `/task` | POST | Execute task |
| `/session` | GET | Get current session |
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

---

## Troubleshooting

### Worker Shows Offline

```bash
# Check service status
ssh user@worker-ip "sudo systemctl status claude-hive-worker"

# View logs
ssh user@worker-ip "sudo journalctl -u claude-hive-worker -f"

# Restart service
ssh user@worker-ip "sudo systemctl restart claude-hive-worker"
```

### Connection Timeout

```bash
# Check port is listening
ssh user@worker-ip "ss -tlnp | grep 8765"

# Check firewall
ssh user@worker-ip "sudo ufw status"
```

### Claude Code Not Found

```bash
# Install Claude Code CLI
ssh user@worker-ip "sudo npm install -g @anthropic-ai/claude-code"

# Verify installation
ssh user@worker-ip "which claude"
```

---

## Project Structure

```
claude-hive/
├── CLAUDE.md           # Instructions for Claude Code
├── AGENTS.md           # Agent behavior guidelines
├── hive/               # Controller package
│   ├── cli.py          # CLI commands
│   ├── client.py       # Worker communication
│   ├── config.py       # Configuration management
│   ├── controller.py   # Task orchestration
│   ├── router.py       # Smart routing
│   ├── discovery.py    # Network scanning
│   └── deploy.py       # Remote deployment
├── worker/             # Worker package
│   ├── server.py       # FastAPI server
│   ├── executor.py     # Claude Code executor
│   └── session.py      # Session management
├── skills/             # Claude Code skills
│   └── hive.md         # /hive skill definition
├── prompts/            # Deployment prompts
│   ├── deploy-basic.md
│   └── deploy-homelab.md
└── examples/           # Example configurations
    └── homelab.yaml
```

---

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

### 核心特性

- **分布式执行** - 每个 Worker 本地运行 Claude Code
- **Session 持久化** - Worker 保持对话上下文
- **智能路由** - 根据模式自动路由任务
- **网络发现** - 自动检测局域网内设备
- **一键部署** - 单命令部署 Worker
- **Claude Code 原生** - 内置 CLAUDE.md 和 AGENTS.md 支持 AI 辅助部署
- **双语支持** - 支持中英文匹配模式

---

## Claude Code 集成

Claude-Hive 设计为可以使用 Claude Code 本身来部署。只需克隆仓库，让 Claude Code 读取内置的 `CLAUDE.md` 即可理解如何部署！

### 使用 Claude Code 部署（推荐）

1. 克隆仓库
2. 在项目目录打开 Claude Code
3. 说：*"帮我部署 claude-hive 到我的 homelab"*

Claude Code 会：
- 读取 `CLAUDE.md` 理解项目
- 询问你的网络信息
- 发现局域网内的设备
- 自动部署 Worker
- 配置路由规则

### 示例提示词

```
# 基础部署
"把 claude-hive worker 部署到 192.168.1.100 和 192.168.1.101"

# 网络发现
"扫描我的网络 192.168.50.0/24，把 worker 部署到所有 Linux 服务器"

# Homelab 设置
"为我的 homelab 设置 claude-hive：
 - .80 的 Docker VM 用于容器管理
 - .92 的 GPU 服务器用于 AI/ML 任务
 - .100 的开发服务器用于开发工作"

# 状态检查
"检查所有 claude-hive worker 的状态"
```

---

## 快速开始

### 方式 1：自动部署

```bash
# 克隆并安装
git clone https://github.com/Genius-Cai/claude-hive.git
cd claude-hive
pip install -e .

# 发现网络中的设备
hive discover 192.168.50.0/24 -u 用户名 -p 密码

# 部署到发现的设备
hive deploy 192.168.50.80 --name docker-vm -u 用户名 -p 密码
hive deploy 192.168.50.92 --name gpu-worker -u 用户名 -p 密码

# 验证部署
hive status
```

### 方式 2：手动安装

#### 在 Controller（你的机器）：
```bash
git clone https://github.com/Genius-Cai/claude-hive.git
cd claude-hive
pip install -e .
```

#### 在 Workers（远程机器）：
```bash
# 安装依赖
pip3 install fastapi uvicorn httpx pydantic

# 安装 Claude Code CLI
npm install -g @anthropic-ai/claude-code

# 下载并运行 worker
mkdir -p ~/claude-hive-worker
curl -o ~/claude-hive-worker/server.py https://raw.githubusercontent.com/Genius-Cai/claude-hive/main/worker/server.py
python3 ~/claude-hive-worker/server.py --name my-worker --port 8765
```

### 配置文件

创建 `~/.claude-hive/config.yaml`：

```yaml
workers:
  docker-vm:
    host: 192.168.50.80
    port: 8765
    capabilities: [docker, containers, services]

  gpu-worker:
    host: 192.168.50.92
    port: 8765
    capabilities: [gpu, ollama, ml]

  dev-server:
    host: 192.168.50.100
    port: 8765
    capabilities: [git, build, test]

routing:
  - pattern: "docker|容器|服务|compose"
    worker: docker-vm
  - pattern: "gpu|ollama|模型|推理|训练"
    worker: gpu-worker
  - pattern: "git|代码|编译|测试"
    worker: dev-server

default_worker: docker-vm
```

---

## 使用方法

### CLI 命令

| 命令 | 说明 |
|------|------|
| `hive status` | 检查所有 worker 状态 |
| `hive send <worker> <task>` | 发送任务到指定 worker |
| `hive ask <task>` | 根据内容自动路由任务 |
| `hive broadcast <task>` | 发送任务到所有 worker |
| `hive session list` | 列出所有 session |
| `hive session new <worker>` | 在 worker 上开始新 session |
| `hive discover <subnet>` | 扫描网络发现设备 |
| `hive deploy <ip>` | 部署 worker 到远程机器 |
| `hive workers` | 列出配置的 workers |
| `hive routes` | 显示路由规则 |

### 使用示例

```bash
# 检查 Docker 容器
hive send docker-vm "列出所有运行中的 Docker 容器"

# 自动路由（根据关键词路由到 docker-vm）
hive ask "重启 Jellyfin 服务"

# GPU 任务（路由到 gpu-worker）
hive ask "用 Ollama 运行 llama3 推理"

# 开发任务（路由到 dev-server）
hive ask "拉取最新代码并运行测试"

# 检查所有服务器
hive broadcast "检查磁盘空间和内存使用"

# 带记忆的 Session
hive send docker-vm "我之前问了什么容器？"
# Worker 记得之前的对话！
```

---

## /hive Skill

安装 `/hive` skill 以在 Claude Code 中直接使用 Claude-Hive 命令：

```bash
hive install-skill
# 或手动复制：
cp skills/hive.md ~/.claude/commands/hive.md
```

现在在 Claude Code 中：
```
/hive status
/hive ask "检查 docker 容器"
/hive send gpu-worker "运行 ollama 推理"
```

---

## 故障排除

### Worker 显示离线

```bash
# 检查服务状态
ssh 用户@worker-ip "sudo systemctl status claude-hive-worker"

# 查看日志
ssh 用户@worker-ip "sudo journalctl -u claude-hive-worker -f"

# 重启服务
ssh 用户@worker-ip "sudo systemctl restart claude-hive-worker"
```

### 连接超时

```bash
# 检查端口监听
ssh 用户@worker-ip "ss -tlnp | grep 8765"

# 检查防火墙
ssh 用户@worker-ip "sudo ufw status"
```

### Claude Code 未找到

```bash
# 安装 Claude Code CLI
ssh 用户@worker-ip "sudo npm install -g @anthropic-ai/claude-code"

# 验证安装
ssh 用户@worker-ip "which claude"
```

---

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
