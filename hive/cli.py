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
@click.argument("task")
@click.option("--new", "-n", is_flag=True, help="Start new session")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
@click.pass_context
def send(ctx, worker: str, task: str, new: bool, timeout: int):
    """Send task to a specific worker"""
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

@cli.command()
@click.argument("task")
@click.option("--new", "-n", is_flag=True, help="Start new session")
@click.option("--timeout", "-t", default=300, help="Timeout in seconds")
@click.pass_context
def ask(ctx, task: str, new: bool, timeout: int):
    """Auto-route task to appropriate worker"""
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
