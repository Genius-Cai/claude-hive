# Deploy Claude-Hive to My Homelab

Please help me deploy claude-hive distributed system to my local network.

## My Environment

- **Network Subnet**: 192.168.50.0/24
- **SSH Username**: geniuscai
- **SSH Password**: [YOUR_PASSWORD_HERE]

## My Devices

| Device | IP | Role | Capabilities |
|--------|-----|------|--------------|
| Docker VM | 192.168.50.80 | Main services | docker, containers |
| GPU Worker | 192.168.50.92 | AI/ML tasks | gpu, ollama |
| Dev Server | 192.168.50.100 | Development | git, build, test |

## Please Execute

1. **Clone the repository** (if not already done)
   ```bash
   git clone https://github.com/Genius-Cai/claude-hive
   cd claude-hive
   pip install -e .
   ```

2. **Scan my network** to discover all available devices
   ```bash
   hive discover 192.168.50.0/24 --ssh-user geniuscai --ssh-pass [PASSWORD]
   ```

3. **Deploy workers** to each Linux server
   ```bash
   hive deploy 192.168.50.80 --name docker-vm --ssh-user geniuscai --ssh-pass [PASSWORD]
   hive deploy 192.168.50.92 --name gpu-worker --ssh-user geniuscai --ssh-pass [PASSWORD]
   hive deploy 192.168.50.100 --name dev-server --ssh-user geniuscai --ssh-pass [PASSWORD]
   ```

4. **Generate configuration** file at `~/.claude-hive/config.yaml`
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
     - pattern: "docker|container|容器|服务"
       worker: docker-vm
     - pattern: "gpu|ollama|模型|训练"
       worker: gpu-worker
     - pattern: "git|代码|编译|测试"
       worker: dev-server

   default_worker: docker-vm
   ```

5. **Verify deployment**
   ```bash
   hive status
   ```
   All workers should show "online".

6. **Test with a sample task**
   ```bash
   hive ask "检查 Docker 容器状态"
   ```

## Success Criteria

- All workers show "online" in `hive status`
- Tasks can be executed via `hive send` and `hive ask`
- Session memory works (follow-up questions remember context)

## Notes

- Each worker runs Claude Code locally
- Sessions persist across multiple tasks
- Tasks are automatically routed based on keywords
