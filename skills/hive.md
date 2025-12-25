---
name: hive
description: Claude-Hive distributed task management - control multiple Claude Code workers across your LAN
---

Execute claude-hive commands for distributed Claude Code orchestration.

## Prerequisites

Ensure claude-hive is installed:
```bash
cd /path/to/claude-hive && pip install -e .
```

## Available Commands

Parse the user's input and execute the appropriate command using the Bash tool:

| User Input | Command to Execute |
|------------|-------------------|
| `status` | `python3 -m hive.cli status` |
| `send <worker> <task>` | `python3 -m hive.cli send <worker> "<task>"` |
| `ask <task>` | `python3 -m hive.cli ask "<task>"` |
| `broadcast <task>` | `python3 -m hive.cli broadcast "<task>"` |
| `discover <subnet>` | `python3 -m hive.cli discover <subnet> -u <user> -p <pass>` |
| `deploy <ip>` | `python3 -m hive.cli deploy <ip> -n <name> -u <user> -p <pass>` |
| `session list` | `python3 -m hive.cli session list` |
| `session new <worker>` | `python3 -m hive.cli session new <worker>` |
| `workers` | `python3 -m hive.cli workers` |
| `routes` | `python3 -m hive.cli routes` |

## Behavior

1. **Parse user input** to determine the command
2. **Execute** using the Bash tool
3. **Format output** for readability
4. **Handle errors** gracefully with suggestions

## Error Handling

| Error | Suggestion |
|-------|------------|
| Worker offline | Check service: `ssh <ip> "sudo systemctl status claude-hive-worker"` |
| Timeout | Increase timeout: add `--timeout 600` |
| Claude not found | Install: `ssh <ip> "sudo npm install -g @anthropic-ai/claude-code"` |
| Connection refused | Check firewall and port 8765 |

## Examples

### Check worker status
```
User: /hive status
Execute: python3 -m hive.cli status
```

### Send task with auto-routing
```
User: /hive ask "check docker containers"
Execute: python3 -m hive.cli ask "check docker containers"
```

### Send to specific worker
```
User: /hive send gpu-worker "run inference on model"
Execute: python3 -m hive.cli send gpu-worker "run inference on model"
```

### Discover network devices
```
User: /hive discover 192.168.50.0/24
Execute: python3 -m hive.cli discover 192.168.50.0/24 -u <ssh_user> -p <ssh_pass>
(Ask user for SSH credentials if not provided)
```

### Deploy to new machine
```
User: /hive deploy 192.168.50.92 as gpu-worker
Execute: python3 -m hive.cli deploy 192.168.50.92 -n gpu-worker -u <user> -p <pass>
(Ask user for SSH credentials and worker name if not provided)
```

## Installation

Copy this file to `~/.claude/commands/hive.md` to enable the /hive command in Claude Code.

Or run:
```bash
python3 -m hive.cli install-skill
```
