# Claude-Hive Agent Instructions

This document provides detailed instructions for AI agents (Claude Code, etc.) working with the claude-hive project.

## Agent Capabilities

When working with claude-hive, you can:

1. **Deploy workers** to remote Linux machines via SSH
2. **Manage workers** using the `hive` CLI
3. **Route tasks** to appropriate workers based on content
4. **Monitor health** of the distributed system
5. **Discover devices** on the local network

## Deployment Workflow

### Step 1: Gather Information

When user requests deployment, ask for:
- Network subnet (e.g., `192.168.50.0/24`)
- SSH username (default: current user)
- SSH password or key path
- Device roles (which machine does what)

### Step 2: Network Discovery

Execute network scan to find available devices:

```bash
# Using nmap (if available)
nmap -sn 192.168.50.0/24 --open

# Or using ping sweep
for i in {1..254}; do ping -c1 -W1 192.168.50.$i &>/dev/null && echo "192.168.50.$i"; done

# Or using hive discover
hive discover 192.168.50.0/24 --ssh-user <user> --ssh-pass <pass>
```

### Step 3: Deploy Workers

For each target machine, deploy worker using expect+SSH:

```bash
# Template for SSH with password
expect -c '
spawn ssh -tt -o StrictHostKeyChecking=no <user>@<ip> "<command>"
expect "password:"
send "<password>\r"
expect {
    "password for" { send "<password>\r"; exp_continue }
    eof
}
'
```

Deployment commands sequence:
1. Install Python dependencies: `pip3 install fastapi uvicorn httpx --break-system-packages`
2. Install Node.js if missing: `curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs`
3. Install Claude Code: `sudo npm install -g @anthropic-ai/claude-code`
4. Download worker code: `curl -o ~/claude-hive-worker/server.py <raw-github-url>`
5. Create systemd service with correct PATH including `/usr/local/bin`
6. Enable and start service

### Step 4: Configure Controller

Generate `~/.claude-hive/config.yaml` based on discovered workers:

```yaml
workers:
  <worker-name>:
    host: <ip>
    port: 8765
    capabilities: [<detected-capabilities>]

routing:
  - pattern: "<keywords>"
    worker: <worker-name>

default_worker: <first-worker>
```

### Step 5: Verify Deployment

```bash
hive status
```

All workers should show "online".

## Capability Detection

When deploying, detect worker capabilities:

| Check | Capability | Command |
|-------|------------|---------|
| Docker installed | `docker` | `which docker` |
| GPU available | `gpu` | `nvidia-smi` or `lspci | grep -i nvidia` |
| Ollama running | `ollama` | `curl localhost:11434/api/tags` |
| Git installed | `git` | `which git` |
| Node.js installed | `nodejs` | `which node` |

## Task Routing Logic

When user sends a task via `hive ask`, apply routing:

```python
patterns = {
    r"docker|container|容器|服务|compose": "docker-vm",
    r"gpu|cuda|nvidia|ollama|模型|训练|推理": "gpu-worker",
    r"git|code|代码|编译|build|test|测试": "dev-server",
}

for pattern, worker in patterns.items():
    if re.search(pattern, task, re.IGNORECASE):
        return worker
return default_worker
```

## Session Management

Each worker maintains its own Claude Code session:

- **Session persists** across multiple tasks
- **Reset session** with `hive session new <worker>`
- **Session ID** stored in `/tmp/claude-hive-session` on worker

Use session continuity for follow-up questions:
```
Task 1: "检查 Docker 容器状态"
Task 2: "重启刚才那个停止的容器"  # Worker remembers context!
```

## Error Handling

### Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `worker offline` | Service not running | `ssh <ip> "sudo systemctl restart claude-hive-worker"` |
| `Claude Code CLI not found` | Not installed or PATH issue | Install Claude Code, add `/usr/local/bin` to service PATH |
| `Connection refused` | Firewall or port issue | Check `ufw status`, ensure port 8765 open |
| `timeout` | Task taking too long | Increase `--timeout` value |
| `session expired` | Long idle time | Run `hive session new <worker>` |

### Debugging Commands

```bash
# Check worker logs
ssh <ip> "sudo journalctl -u claude-hive-worker -n 50"

# Test worker API directly
curl http://<ip>:8765/health

# Check Claude Code version
ssh <ip> "claude --version"

# Test Claude Code execution
ssh <ip> "claude -p 'echo hello' --output-format json"
```

## Security Notes

1. **No authentication**: This system assumes trusted LAN
2. **Passwords in commands**: Use environment variables when possible
3. **SSH keys**: Prefer SSH keys over passwords for production

## Best Practices

1. **Name workers meaningfully**: Use names like `docker-vm`, `gpu-worker`, `dev-server`
2. **Set appropriate capabilities**: Helps with intelligent routing
3. **Monitor regularly**: Use `hive status` to check health
4. **Session management**: Reset sessions when switching contexts
5. **Timeout values**: Set appropriate timeouts for long-running tasks

## Example Interaction Patterns

### User wants to deploy
```
User: 帮我部署 claude-hive 到我的局域网
Agent:
1. 询问网段和 SSH 凭据
2. 执行 hive discover
3. 显示发现的设备
4. 确认后执行 hive deploy
5. 验证 hive status
```

### User wants to run a task
```
User: 检查我所有服务器的磁盘空间
Agent:
1. 执行 hive broadcast "检查磁盘空间 df -h"
2. 汇总所有 worker 的响应
3. 格式化显示结果
```

### User wants to manage sessions
```
User: docker-vm 好像记错东西了，重置一下
Agent:
1. 执行 hive session new docker-vm
2. 确认 session 已重置
```

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| Config | `~/.claude-hive/config.yaml` | Worker 配置 |
| Session | `/tmp/claude-hive-session` (worker) | Session ID |
| Logs | `journalctl -u claude-hive-worker` | 服务日志 |
| Worker code | `~/claude-hive-worker/server.py` | Worker 服务 |

## Integration with Claude Code Skills

This project provides skills for `/hive` command:

- `/hive status` - Show all workers
- `/hive send <worker> <task>` - Send task
- `/hive ask <task>` - Auto-route task
- `/hive discover <subnet>` - Scan network
- `/hive deploy <ip>` - Deploy worker

Skills are installed to `~/.claude/commands/hive.md`.
