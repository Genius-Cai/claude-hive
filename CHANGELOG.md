# Changelog

All notable changes to Claude-Hive will be documented in this file.

## [0.2.0] - 2025-12-26

### Added

#### Smart Routing (`hive do`)
- **Natural language task input**: Just describe what you want, system auto-detects execution method
- **Intelligent SSH/AI routing**:
  - Simple commands (list, status, ps) → SSH direct execution (~2s)
  - Complex tasks (debug, fix, configure) → Claude AI reasoning (~30s+)
- **Keyword-based worker selection**: Automatically routes to appropriate worker based on task keywords

#### SSH Direct Execution (`hive run`)
- **New `run` command**: Force SSH execution for any command
- **SSH credentials in config**: `ssh_user` and `ssh_pass` per worker
- **No AI overhead**: Instant command execution

#### Worker Improvements
- **Graceful error handling**: All exceptions caught, no more 500 errors
- **Autonomous mode**: Remote Claude attempts to fix issues before reporting failure
- **Result validation**: Ensures valid output even when Claude returns nothing

### Changed
- `ask` command now clearly documented as AI-only
- Config schema updated to support SSH credentials
- Skill file updated with smart routing documentation

### Fixed
- Worker 500 errors now return proper error messages
- None result handling in task responses
- Windows compatibility for worker server

## [0.1.0] - 2025-12-25

### Added
- Initial release
- Worker deployment via SSH
- Network discovery
- Task routing by patterns
- Session management
- Claude Code CLI wrapper

---

## Usage Quick Reference

```bash
# Smart routing (recommended)
hive do "列出 Ollama 模型"        # → SSH
hive do "调试 Docker 容器问题"    # → AI

# Explicit SSH
hive run docker-vm "docker ps"

# Explicit AI
hive send docker-vm "帮我调试网络问题"

# Status
hive status
```
