#!/usr/bin/env python3
"""
Claude-Hive CLI

Command-line interface for the Hive controller.

Usage:
    hive status              # Check all workers
    hive send <worker> <task> # Send task to specific worker
    hive ask <task>          # Auto-route task
    hive broadcast <task>    # Send to all workers
"""

import asyncio
import sys
from typing import Optional

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
# Entry Point
# ============================================================================

def main():
    """Main entry point"""
    cli(obj={})

if __name__ == "__main__":
    main()
