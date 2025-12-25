# Claude-Hive

分布式 Claude Code 协调框架 - 让局域网内的多台设备各自运行 Claude Code，通过 HTTP API 协调工作。

## 项目概述

Claude-Hive 解决了使用 SSH/expect 远程管理 Claude Code 的痛点：
- **延迟**: SSH 400-700ms → HTTP 25-50ms (15x 提升)
- **Token**: 5000+/请求 → 100-300/请求 (50x 节省)
- **记忆**: 无 → 每个 Worker 维护持久 Session

## 快速开始

### 方式 1: 自动部署（推荐）

如果用户说 "帮我部署 claude-hive"，执行以下步骤：

```bash
# 1. 安装 Controller
cd /path/to/claude-hive
pip install -e .

# 2. 扫描网络发现设备
hive discover <subnet> --ssh-user <user> --ssh-pass <pass>
# 例: hive discover 192.168.50.0/24 --ssh-user geniuscai --ssh-pass xxx

# 3. 部署 Worker 到发现的设备
hive deploy <ip> --name <worker-name> --ssh-user <user> --ssh-pass <pass>

# 4. 验证部署
hive status
```

### 方式 2: 手动部署

#### 在 Controller 机器（本地）：
```bash
pip install -e .
cp examples/homelab.yaml ~/.claude-hive/config.yaml
# 编辑配置文件，添加你的 worker 信息
```

#### 在 Worker 机器（远程）：
```bash
# 安装依赖
pip3 install fastapi uvicorn httpx

# 安装 Claude Code CLI
npm install -g @anthropic-ai/claude-code

# 下载 worker 代码
mkdir -p ~/claude-hive-worker
curl -o ~/claude-hive-worker/server.py https://raw.githubusercontent.com/Genius-Cai/claude-hive/main/worker/server.py

# 创建 systemd 服务
sudo tee /etc/systemd/system/claude-hive-worker.service << 'EOF'
[Unit]
Description=Claude-Hive Worker
After=network.target

[Service]
User=$USER
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/python3 ~/claude-hive-worker/server.py --name <worker-name>
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now claude-hive-worker
```

## 命令参考

| 命令 | 作用 | 示例 |
|------|------|------|
| `hive status` | 查看所有 worker 状态 | `hive status` |
| `hive send <worker> <task>` | 发送任务到指定 worker | `hive send docker-vm "检查容器"` |
| `hive ask <task>` | 自动路由任务 | `hive ask "重启 Jellyfin"` |
| `hive broadcast <task>` | 广播到所有 worker | `hive broadcast "检查磁盘空间"` |
| `hive session new <worker>` | 重置 worker 会话 | `hive session new docker-vm` |
| `hive discover <subnet>` | 扫描网络发现设备 | `hive discover 192.168.50.0/24` |
| `hive deploy <ip>` | 部署 worker 到远程 | `hive deploy 192.168.50.92 --name gpu` |

## 配置文件

配置文件位于 `~/.claude-hive/config.yaml`：

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

routing:
  - pattern: "docker|容器|服务"
    worker: docker-vm
  - pattern: "gpu|ollama|模型"
    worker: gpu-worker

default_worker: docker-vm
```

## 路由规则

任务会根据关键词自动路由到合适的 worker：

| 关键词 | 路由到 | 说明 |
|--------|--------|------|
| docker, 容器, 服务, compose | docker-vm | Docker 相关任务 |
| gpu, ollama, 模型, 训练 | gpu-worker | GPU/AI 任务 |
| git, 代码, 编译, 测试 | dev-server | 开发任务 |

## 故障排除

### Worker 显示 offline
```bash
# 检查 worker 服务状态
ssh user@worker-ip "sudo systemctl status claude-hive-worker"

# 查看日志
ssh user@worker-ip "sudo journalctl -u claude-hive-worker -f"
```

### Claude Code 未安装
```bash
# 在 worker 上安装
ssh user@worker-ip "sudo npm install -g @anthropic-ai/claude-code"

# 重启服务
ssh user@worker-ip "sudo systemctl restart claude-hive-worker"
```

### 连接超时
```bash
# 检查防火墙
ssh user@worker-ip "sudo ufw status"

# 检查端口监听
ssh user@worker-ip "ss -tlnp | grep 8765"
```

## 开发

```bash
# 克隆仓库
git clone https://github.com/Genius-Cai/claude-hive
cd claude-hive

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/
```

## API 端点

Worker 提供以下 HTTP API：

| 端点 | 方法 | 作用 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/task` | POST | 执行任务 |
| `/session` | GET | 获取当前 session |
| `/session/new` | POST | 创建新 session |
| `/history` | GET | 获取对话历史 |

## 注意事项

1. **网络安全**: 本项目假设在可信的局域网内运行，不包含认证机制
2. **Claude Code 版本**: Worker 需要 Claude Code CLI v2.0+
3. **Session 持久化**: 每个 Worker 独立维护 session，重启服务会重置
4. **并发限制**: 每个 Worker 同时只能执行一个任务
