# Deploy Claude-Hive

Please help me deploy claude-hive to my local network.

## My Environment

- **Network Subnet**: [e.g., 192.168.1.0/24]
- **SSH Username**: [your username]
- **SSH Password**: [your password]

## Steps to Execute

### Step 1: Install Controller (on this machine)

```bash
git clone https://github.com/Genius-Cai/claude-hive
cd claude-hive
pip install -e .
```

### Step 2: Discover Network Devices

```bash
hive discover [SUBNET] --ssh-user [USER] --ssh-pass [PASS]
```

This will:
- Scan the network for alive hosts
- Check SSH availability
- Detect installed software (Docker, GPU, Git, etc.)
- Suggest a configuration

### Step 3: Deploy Workers

For each Linux server you want to use:

```bash
hive deploy [IP] --name [WORKER_NAME] --ssh-user [USER] --ssh-pass [PASS]
```

This will:
- Install Python dependencies
- Install Node.js if needed
- Install Claude Code CLI
- Create and start systemd service

### Step 4: Configure

Create `~/.claude-hive/config.yaml`:

```yaml
workers:
  [worker-name]:
    host: [IP]
    port: 8765
    capabilities: [list, of, capabilities]

routing:
  - pattern: "[keywords]"
    worker: [worker-name]

default_worker: [first-worker]
```

### Step 5: Verify

```bash
hive status
```

### Step 6: Test

```bash
hive ask "Hello, which worker am I talking to?"
```

## My Devices

Please list your devices below so I can help configure:

| Device Name | IP Address | Purpose | Notes |
|-------------|------------|---------|-------|
| | | | |
| | | | |
| | | | |

## Questions

If you're unsure about anything, I can help you:
- Identify your network subnet
- Choose which devices to use as workers
- Configure routing rules based on your use case
