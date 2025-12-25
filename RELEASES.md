# Release Notes for GitHub

Copy these to GitHub when creating releases at:
https://github.com/Genius-Cai/claude-hive/releases/new

---

## v0.1.0 - Initial Release

**Tag:** `v0.1.0`
**Title:** `v0.1.0 - Initial Release`

### Release Notes:

```markdown
# Claude-Hive v0.1.0 - Initial Release 🐝

The first release of Claude-Hive, a distributed Claude Code orchestration framework for LAN environments.

## Features

- **Worker Deployment** - Deploy Claude Code workers to remote machines via SSH
- **Network Discovery** - Scan and discover devices in your LAN
- **Task Routing** - Pattern-based routing to appropriate workers
- **Session Management** - Persistent sessions per worker
- **Claude Code CLI Wrapper** - Execute Claude Code tasks remotely

## Installation

```bash
git clone https://github.com/Genius-Cai/claude-hive.git
cd claude-hive
pip install -e .
```

## Quick Start

```bash
# Discover devices
hive discover 192.168.50.0/24 -u user -p pass

# Deploy worker
hive deploy 192.168.50.80 --name docker-vm -u user -p pass

# Send task
hive send docker-vm "检查 Docker 容器状态"
```

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## v0.2.0 - Smart Routing

**Tag:** `v0.2.0`
**Title:** `v0.2.0 - Smart Routing`

### Release Notes:

```markdown
# Claude-Hive v0.2.0 - Smart Routing 🚀

Major update with intelligent SSH/AI auto-detection for optimal task execution.

## New Features

### Smart `do` Command
- **Natural language input**: Just describe what you want
- **Intelligent routing**:
  - Simple commands (list, status, ps) → SSH direct (~2s)
  - Complex tasks (debug, fix, configure) → Claude AI (~30s+)

### SSH Direct Execution (`hive run`)
- Force SSH execution for any command
- SSH credentials configurable per worker
- No AI overhead for simple commands

### Worker Improvements
- Graceful error handling (no more 500 errors)
- Autonomous mode: Remote Claude attempts fixes before reporting
- Result validation ensures valid output

## Usage

```bash
# Smart routing (recommended)
hive do "列出 Ollama 模型"        # → SSH
hive do "调试 Docker 容器问题"    # → AI

# Explicit SSH
hive run docker-vm "docker ps"

# Explicit AI
hive send docker-vm "帮我调试网络问题"
```

## Breaking Changes
- Config schema updated: added `ssh_user` and `ssh_pass` per worker

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```
