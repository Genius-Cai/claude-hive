#!/usr/bin/env python3
"""
Claude-Hive CLI

Command-line interface for the Hive controller.

Usage:
    hive status              # Check all workers
    hive send <worker> <task> # Send task to specific worker
    hive ask <task>          # Auto-route task
    hive broadcast <task>    # Send to all workers
    hive discover <subnet>   # Scan network for devices
    hive deploy <ip>         # Deploy worker to remote machine
"""

import asyncio
import sys
import os
from typing import Optional
from pathlib import Path

import click

from .config import load_config, TaskRouter
from .client import HiveClient, TaskResult, WorkerStatus

# ============================================================================
# Helpers
# ============================================================================

def run_async(coro):
    """Run async function in sync context"""
    return asyncio.get_event_loop().run_until_complete(coro)

def print_status(status: WorkerStatus) -> None:
    """Print worker status"""
    if status.online:
        icon = click.style("●", fg="green")
        state = click.style("online", fg="green")
        info = f"session: {status.session_id or 'none'}"
        if status.uptime:
            hours = int(status.uptime // 3600)
            mins = int((status.uptime % 3600) // 60)
            info += f", uptime: {hours}h{mins}m"
    else:
        icon = click.style("●", fg="red")
        state = click.style("offline", fg="red")
        info = status.error or "unreachable"

    click.echo(f"  {icon} {status.name:<15} {state:<10} {status.url:<30} {info}")

def print_result(result: TaskResult) -> None:
    """Print task result"""
    if result.success:
        icon = click.style("✓", fg="green")
    else:
        icon = click.style("✗", fg="red")

    click.echo(f"\n{icon} [{result.worker}] ({result.execution_time:.2f}s)")
    click.echo("-" * 60)
    click.echo(result.result)

# ============================================================================
# CLI Commands
# ============================================================================

@click.group()
@click.option("--config", "-c", "config_path", help="Path to config file")
@click.pass_context
def cli(ctx, config_path: Optional[str]):
    """🐝 Claude-Hive: Distributed Claude Code Orchestration"""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)
    ctx.obj["router"] = TaskRouter(ctx.obj["config"])
    ctx.obj["client"] = HiveClient(ctx.obj["config"].workers)

@cli.command()
@click.pass_context
def status(ctx):
    """Check status of all workers"""
    config = ctx.obj["config"]
    client = ctx.obj["client"]

    if not config.workers:
        click.echo("No workers configured. Create ~/.claude-hive/config.yaml")
        return

    click.echo("\n🐝 Claude-Hive Workers\n")

    async def check():
        statuses = await client.status_all()
        for s in statuses:
            print_status(s)
        await client.close()

    run_async(check())
    click.echo()

@cli.command()
@click.argument("worker")
@click.argument("command")
@click.option("--timeout", "-t", default=30, help="Timeout in seconds")
@click.pass_context
def run(ctx, worker: str, command: str, timeout: int):
    """Run a simple command via SSH (no AI, fast execution)

    Use this for simple commands like 'ollama list', 'docker ps', etc.
    For complex tasks that need AI reasoning, use 'send' instead.
    """
    config = ctx.obj["config"]

    if worker not in config.workers:
        click.echo(f"Worker '{worker}' not found. Available: {', '.join(config.workers.keys())}")
        return

    worker_config = config.workers[worker]

    # Import SSH executor
    import subprocess
    import shutil

    if not shutil.which("expect"):
        click.echo("'expect' command not found. Install with: brew install expect")
        return

    # Get SSH credentials from config or use defaults
    ssh_user = getattr(worker_config, 'ssh_user', 'geniuscai')
    ssh_pass = getattr(worker_config, 'ssh_pass', 'Shangzhensteven2024!')
    host = worker_config.host

    click.echo(f"⚡ [{worker}] Running: {command}")

    expect_script = f'''
spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {ssh_user}@{host} "{command}"
expect {{
    "password:" {{ send "{ssh_pass}\\r"; exp_continue }}
    "Password:" {{ send "{ssh_pass}\\r"; exp_continue }}
    timeout {{ exit 1 }}
    eof
}}
'''
    try:
        result = subprocess.run(
            ["expect", "-c", expect_script],
            capture_output=True,
            text=True,
            timeout=timeout + 10
        )
        # Clean output
        lines = result.stdout.split('\n')
        clean_lines = [
            l for l in lines
            if not l.startswith('spawn ')
            and 'password' not in l.lower()
            and not l.startswith('Connection to')
        ]
        output = '\n'.join(clean_lines).strip()

        click.echo("-" * 60)
        click.echo(output)
        click.echo("-" * 60)

    except subprocess.TimeoutExpired:
        click.echo(f"✗ Command timed out after {timeout}s")
    except Exception as e:
        click.echo(f"✗ Error: {e}")


@cli.command()
@click.argument("worker")
@click.argument("task")
@click.option("--new", "-n", is_flag=True, help="Start new session")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
@click.pass_context
def send(ctx, worker: str, task: str, new: bool, timeout: int):
    """Send task to a specific worker (uses Claude AI for reasoning)"""
    config = ctx.obj["config"]
    client = ctx.obj["client"]

    if worker not in config.workers:
        click.echo(f"Worker '{worker}' not found. Available: {', '.join(config.workers.keys())}")
        return

    async def execute():
        result = await client.execute(worker, task, new_session=new, timeout=timeout)
        print_result(result)
        await client.close()

    run_async(execute())

def is_simple_command(task: str) -> tuple[bool, str]:
    """
    Analyze task to determine if it's a simple command (SSH) or complex task (AI).

    Returns:
        (is_simple, command_or_task): If simple, returns the shell command to run.
                                       If complex, returns the original task.
    """
    task_lower = task.lower()

    # Simple command patterns - direct shell commands
    simple_patterns = [
        # Ollama commands
        (r"(列出|list|查看).*(ollama|模型|model)", "ollama list"),
        (r"ollama\s+(list|ps|show|pull|run)", None),  # Direct ollama command

        # Docker commands
        (r"(列出|list|查看).*(docker|容器|container)", "docker ps --format 'table {{.Names}}\t{{.Status}}'"),
        (r"docker\s+(ps|images|logs|stats)", None),  # Direct docker command

        # System commands
        (r"(查看|check|show).*(磁盘|disk|空间|space)", "df -h"),
        (r"(查看|check|show).*(内存|memory|ram)", "free -h"),
        (r"(查看|check|show).*(cpu|负载|load)", "uptime"),
        (r"(服务|service).*(状态|status)", None),  # Need context

        # Git commands
        (r"git\s+(status|log|branch|diff)", None),  # Direct git command

        # Network
        (r"(ping|curl|wget)\s+", None),  # Direct network command
    ]

    import re
    for pattern, command in simple_patterns:
        if re.search(pattern, task_lower):
            if command:
                return True, command
            else:
                # Extract the actual command from the task
                # If it looks like a shell command, use it directly
                if re.match(r'^(ollama|docker|git|systemctl|ping|curl|df|free|uptime|ls|cat|head|tail)\s', task_lower):
                    return True, task
                return True, task

    # Complex task indicators - need AI reasoning
    complex_indicators = [
        r"(为什么|why|怎么|how|debug|调试|修复|fix|问题|problem|error|错误)",
        r"(帮我|help|请|please|分析|analyze|优化|optimize)",
        r"(设置|setup|配置|configure|安装|install|部署|deploy)",
        r"(创建|create|编写|write|生成|generate)",
    ]

    for pattern in complex_indicators:
        if re.search(pattern, task_lower):
            return False, task

    # Default: if it looks like a direct command, use SSH; otherwise use AI
    if re.match(r'^[a-z]+\s', task_lower) and len(task.split()) <= 5:
        return True, task

    return False, task


@cli.command()
@click.argument("task")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
@click.pass_context
def do(ctx, task: str, timeout: int):
    """Smart execution - auto-detect simple command vs complex task

    Examples:
        hive do docker-vm "列出 Docker 容器"     # → SSH (simple)
        hive do docker-vm "docker ps"            # → SSH (simple)
        hive do docker-vm "调试 Jellyfin 问题"   # → AI (complex)
    """
    config = ctx.obj["config"]
    router = ctx.obj["router"]
    client = ctx.obj["client"]

    if not config.workers:
        click.echo("No workers configured.")
        return

    # Route to appropriate worker
    worker = router.route(task)
    if not worker:
        worker = config.default_worker
    if not worker:
        click.echo("No matching worker found.")
        return

    worker_config = config.workers.get(worker)
    if not worker_config:
        click.echo(f"Worker '{worker}' not found.")
        return

    # Analyze task complexity
    is_simple, command = is_simple_command(task)

    if is_simple:
        # Use SSH for simple commands
        click.echo(f"⚡ [{worker}] SSH: {command}")

        import subprocess
        import shutil

        if not shutil.which("expect"):
            click.echo("'expect' not found. Falling back to AI mode.")
            is_simple = False
        else:
            ssh_user = worker_config.ssh_user or 'geniuscai'
            ssh_pass = worker_config.ssh_pass or 'Shangzhensteven2024!'
            host = worker_config.host

            expect_script = f'''
spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {ssh_user}@{host} "{command}"
expect {{
    "password:" {{ send "{ssh_pass}\\r"; exp_continue }}
    "Password:" {{ send "{ssh_pass}\\r"; exp_continue }}
    timeout {{ exit 1 }}
    eof
}}
'''
            try:
                result = subprocess.run(
                    ["expect", "-c", expect_script],
                    capture_output=True,
                    text=True,
                    timeout=min(timeout, 60) + 10
                )
                lines = result.stdout.split('\n')
                clean_lines = [
                    l for l in lines
                    if not l.startswith('spawn ')
                    and 'password' not in l.lower()
                    and not l.startswith('Connection to')
                ]
                output = '\n'.join(clean_lines).strip()
                click.echo("-" * 60)
                click.echo(output)
                click.echo("-" * 60)
                return
            except subprocess.TimeoutExpired:
                click.echo(f"SSH timeout. Falling back to AI mode.")
                is_simple = False
            except Exception as e:
                click.echo(f"SSH error: {e}. Falling back to AI mode.")
                is_simple = False

    # Use AI for complex tasks
    click.echo(f"🧠 [{worker}] AI: {task}")

    async def execute():
        result = await client.execute(worker, task, new_session=True, timeout=timeout)
        print_result(result)
        await client.close()

    run_async(execute())


@cli.command()
@click.argument("task")
@click.option("--new", "-n", is_flag=True, help="Start new session")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
@click.pass_context
def ask(ctx, task: str, new: bool, timeout: int):
    """Auto-route task to appropriate worker (uses AI)"""
    config = ctx.obj["config"]
    router = ctx.obj["router"]
    client = ctx.obj["client"]

    if not config.workers:
        click.echo("No workers configured.")
        return

    worker = router.route(task)
    if not worker:
        click.echo("No matching worker found for this task.")
        return

    click.echo(f"🔀 Routing to: {worker}")

    async def execute():
        result = await client.execute(worker, task, new_session=new, timeout=timeout)
        print_result(result)
        await client.close()

    run_async(execute())

@cli.command()
@click.argument("task")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
@click.pass_context
def broadcast(ctx, task: str, timeout: int):
    """Send task to all workers"""
    config = ctx.obj["config"]
    client = ctx.obj["client"]

    if not config.workers:
        click.echo("No workers configured.")
        return

    click.echo(f"📡 Broadcasting to {len(config.workers)} workers...")

    async def execute():
        results = await client.broadcast(task, timeout=timeout)
        for result in results:
            print_result(result)
        await client.close()

    run_async(execute())

@cli.group()
def session():
    """Session management commands"""
    pass

@session.command("list")
@click.pass_context
def session_list(ctx):
    """List sessions on all workers"""
    config = ctx.obj["config"]
    client = ctx.obj["client"]

    if not config.workers:
        click.echo("No workers configured.")
        return

    click.echo("\n📋 Worker Sessions\n")

    async def check():
        statuses = await client.status_all()
        for s in statuses:
            if s.online:
                icon = click.style("●", fg="green")
                session = s.session_id or click.style("no session", dim=True)
            else:
                icon = click.style("●", fg="red")
                session = click.style("offline", fg="red")
            click.echo(f"  {icon} {s.name:<15} {session}")
        await client.close()

    run_async(check())
    click.echo()

@session.command("new")
@click.argument("worker")
@click.pass_context
def session_new(ctx, worker: str):
    """Start new session on a worker"""
    config = ctx.obj["config"]

    if worker not in config.workers:
        click.echo(f"Worker '{worker}' not found.")
        return

    from .client import WorkerClient

    async def reset():
        wc = WorkerClient(config.workers[worker])
        success = await wc.new_session()
        await wc.close()
        if success:
            click.echo(f"✓ New session started on {worker}")
        else:
            click.echo(f"✗ Failed to start new session on {worker}")

    run_async(reset())

@cli.command()
@click.pass_context
def workers(ctx):
    """List configured workers"""
    config = ctx.obj["config"]

    if not config.workers:
        click.echo("No workers configured. Create ~/.claude-hive/config.yaml")
        return

    click.echo("\n📋 Configured Workers\n")
    for name, worker in config.workers.items():
        caps = ", ".join(worker.capabilities) if worker.capabilities else "none"
        click.echo(f"  {name:<15} {worker.url:<30} [{caps}]")
    click.echo()

@cli.command()
@click.pass_context
def routes(ctx):
    """Show routing rules"""
    config = ctx.obj["config"]

    click.echo("\n🔀 Routing Rules\n")
    if config.routing:
        for rule in config.routing:
            click.echo(f"  /{rule.pattern}/ → {rule.worker}")
    else:
        click.echo("  No routing rules configured")

    if config.default_worker:
        click.echo(f"\n  Default: {config.default_worker}")
    click.echo()

# ============================================================================
# Discovery & Deployment Commands
# ============================================================================

@cli.command()
@click.argument("subnet")
@click.option("--ssh-user", "-u", help="SSH username for probing")
@click.option("--ssh-pass", "-p", help="SSH password for probing")
@click.option("--save", "-s", is_flag=True, help="Save suggested config to ~/.claude-hive/config.yaml")
def discover(subnet: str, ssh_user: Optional[str], ssh_pass: Optional[str], save: bool):
    """
    Discover devices on the local network.

    SUBNET should be in CIDR notation, e.g., 192.168.50.0/24
    """
    from .discovery import NetworkDiscovery, format_discovery_table, generate_config_suggestion

    click.echo(f"\n🔍 Scanning {subnet}...\n")

    async def scan():
        discovery = NetworkDiscovery(ssh_user=ssh_user, ssh_pass=ssh_pass)
        devices = await discovery.discover(subnet)
        return devices

    devices = run_async(scan())

    if not devices:
        click.echo("No devices found.")
        return

    # Display results
    click.echo(format_discovery_table(devices))

    # Filter to SSH-accessible Linux devices
    deployable = [d for d in devices if d.ssh_available and d.os_type in ("Linux", None)]

    if deployable:
        click.echo(f"\n📦 {len(deployable)} devices available for worker deployment:\n")
        for d in deployable:
            claude_status = click.style("✓", fg="green") if d.claude_version else click.style("✗", fg="red")
            click.echo(f"  {d.ip:<16} {d.hostname or '-':<20} Claude: {claude_status}")

        # Generate config suggestion
        click.echo("\n📝 Suggested configuration:\n")
        config_yaml = generate_config_suggestion(devices)
        click.echo(config_yaml)

        if save:
            config_dir = Path.home() / ".claude-hive"
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / "config.yaml"

            if config_file.exists():
                if not click.confirm(f"\n{config_file} exists. Overwrite?"):
                    return

            config_file.write_text(config_yaml)
            click.echo(f"\n✓ Config saved to {config_file}")
        else:
            click.echo("\nUse --save to write this configuration to ~/.claude-hive/config.yaml")

    click.echo()


@cli.command()
@click.argument("ip")
@click.option("--name", "-n", required=True, help="Worker name")
@click.option("--ssh-user", "-u", required=True, help="SSH username")
@click.option("--ssh-pass", "-p", required=True, help="SSH password")
@click.option("--port", default=8765, help="Worker port (default: 8765)")
def deploy(ip: str, name: str, ssh_user: str, ssh_pass: str, port: int):
    """
    Deploy a worker to a remote machine.

    IP is the target machine's IP address.
    """
    from .deploy import deploy_worker, format_deploy_results

    click.echo(f"\n🚀 Deploying worker '{name}' to {ip}...\n")

    def progress(step: str, message: str):
        click.echo(f"  [{step}] {message}")

    results = deploy_worker(
        ip=ip,
        name=name,
        ssh_user=ssh_user,
        ssh_pass=ssh_pass,
        port=port,
        progress_callback=progress
    )

    click.echo()
    click.echo(format_deploy_results(results))

    # Check if successful
    all_success = all(r.success for r in results)
    if all_success:
        click.echo(f"\n✅ Worker '{name}' deployed successfully!")
        click.echo(f"   URL: http://{ip}:{port}")
        click.echo(f"\n   Add to config.yaml:")
        click.echo(f"     {name}:")
        click.echo(f"       host: {ip}")
        click.echo(f"       port: {port}")
        click.echo(f"       capabilities: []")
    else:
        click.echo(f"\n❌ Deployment failed. Check errors above.")

    click.echo()


@cli.command()
@click.option("--force", "-f", is_flag=True, help="Overwrite existing skill")
def install_skill(force: bool):
    """Install the /hive skill for Claude Code."""
    skill_dir = Path.home() / ".claude" / "commands"
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_file = skill_dir / "hive.md"

    if skill_file.exists() and not force:
        click.echo(f"Skill already exists at {skill_file}")
        click.echo("Use --force to overwrite.")
        return

    skill_content = '''---
name: hive
description: Claude-Hive distributed task management
---

Execute claude-hive commands for distributed Claude Code orchestration.

## Available Commands

Parse the user's input and execute the appropriate command:

- `status` → Execute: `python3 -m hive.cli status`
- `send <worker> <task>` → Execute: `python3 -m hive.cli send <worker> "<task>"`
- `ask <task>` → Execute: `python3 -m hive.cli ask "<task>"`
- `broadcast <task>` → Execute: `python3 -m hive.cli broadcast "<task>"`
- `discover <subnet>` → Execute: `python3 -m hive.cli discover <subnet>`
- `deploy <ip> --name <name> --ssh-user <user> --ssh-pass <pass>` → Execute deployment
- `session list` → Execute: `python3 -m hive.cli session list`
- `session new <worker>` → Execute: `python3 -m hive.cli session new <worker>`

## Execution

Use the Bash tool to execute commands. Parse and format the output for the user.

## Error Handling

- If worker is offline, suggest checking the service status
- If timeout occurs, suggest increasing the --timeout value
- If Claude Code not found, suggest installing on the worker

## Examples

User: /hive status
→ Run: python3 -m hive.cli status

User: /hive ask "check docker containers"
→ Run: python3 -m hive.cli ask "check docker containers"

User: /hive send gpu-worker "run inference"
→ Run: python3 -m hive.cli send gpu-worker "run inference"
'''

    skill_file.write_text(skill_content)
    click.echo(f"✓ Skill installed to {skill_file}")
    click.echo("\nYou can now use /hive in Claude Code!")


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Main entry point"""
    cli(obj={})

if __name__ == "__main__":
    main()
