"""
Network discovery module for claude-hive.

Scans local network to find potential worker devices.
"""

import asyncio
import ipaddress
import subprocess
import socket
from dataclasses import dataclass
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor
import shutil


@dataclass
class DiscoveredDevice:
    """Represents a discovered network device."""
    ip: str
    hostname: Optional[str] = None
    os_type: Optional[str] = None
    ssh_available: bool = False
    claude_version: Optional[str] = None
    capabilities: List[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []


class NetworkDiscovery:
    """Discovers devices on the local network."""

    def __init__(
        self,
        ssh_user: Optional[str] = None,
        ssh_pass: Optional[str] = None,
        ssh_timeout: int = 5,
        max_workers: int = 20
    ):
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.ssh_timeout = ssh_timeout
        self.max_workers = max_workers

    async def discover(self, subnet: str) -> List[DiscoveredDevice]:
        """
        Discover devices on the specified subnet.

        Args:
            subnet: CIDR notation subnet (e.g., '192.168.50.0/24')

        Returns:
            List of discovered devices
        """
        # Parse subnet
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid subnet: {subnet}") from e

        # Get list of IPs to scan
        ips = [str(ip) for ip in network.hosts()]

        # Phase 1: Ping sweep to find alive hosts
        alive_hosts = await self._ping_sweep(ips)

        if not alive_hosts:
            return []

        # Phase 2: Gather details for alive hosts
        devices = await self._gather_device_info(alive_hosts)

        return devices

    async def _ping_sweep(self, ips: List[str]) -> List[str]:
        """Ping all IPs to find alive hosts."""
        alive = []

        # Use concurrent pings
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                loop.run_in_executor(executor, self._ping_host, ip)
                for ip in ips
            ]
            results = await asyncio.gather(*futures)

        for ip, is_alive in zip(ips, results):
            if is_alive:
                alive.append(ip)

        return alive

    def _ping_host(self, ip: str) -> bool:
        """Ping a single host."""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "1", ip],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    async def _gather_device_info(self, ips: List[str]) -> List[DiscoveredDevice]:
        """Gather detailed info for each alive host."""
        devices = []

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=min(10, len(ips))) as executor:
            futures = [
                loop.run_in_executor(executor, self._probe_device, ip)
                for ip in ips
            ]
            results = await asyncio.gather(*futures)

        for device in results:
            if device:
                devices.append(device)

        return devices

    def _probe_device(self, ip: str) -> Optional[DiscoveredDevice]:
        """Probe a single device for details."""
        device = DiscoveredDevice(ip=ip)

        # Get hostname
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            device.hostname = hostname.split('.')[0]  # Short name
        except socket.herror:
            device.hostname = None

        # Check SSH availability
        device.ssh_available = self._check_ssh(ip)

        # If SSH available and credentials provided, get more details
        if device.ssh_available and self.ssh_user and self.ssh_pass:
            self._ssh_probe(device)

        return device

    def _check_ssh(self, ip: str) -> bool:
        """Check if SSH port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip, 22))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _ssh_probe(self, device: DiscoveredDevice) -> None:
        """Probe device via SSH for capabilities."""
        # Check if expect is available
        if not shutil.which("expect"):
            return

        # Commands to probe
        probes = [
            ("uname -s", self._parse_os),
            ("which docker", lambda r: device.capabilities.append("docker") if r.strip() else None),
            ("nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1",
             lambda r: device.capabilities.append("gpu") if r.strip() else None),
            ("which ollama", lambda r: device.capabilities.append("ollama") if r.strip() else None),
            ("which git", lambda r: device.capabilities.append("git") if r.strip() else None),
            ("which node", lambda r: device.capabilities.append("nodejs") if r.strip() else None),
            ("claude --version 2>/dev/null", lambda r: setattr(device, 'claude_version', r.strip()) if r.strip() else None),
        ]

        for cmd, handler in probes:
            try:
                result = self._ssh_exec(device.ip, cmd)
                if result:
                    if cmd == "uname -s":
                        device.os_type = result.strip()
                    else:
                        handler(result)
            except Exception:
                pass

    def _parse_os(self, result: str) -> str:
        """Parse OS type from uname output."""
        os_map = {
            "Linux": "Linux",
            "Darwin": "macOS",
            "FreeBSD": "FreeBSD",
        }
        return os_map.get(result.strip(), result.strip())

    def _ssh_exec(self, ip: str, command: str) -> Optional[str]:
        """Execute command via SSH using expect."""
        expect_script = f'''
spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout={self.ssh_timeout} {self.ssh_user}@{ip} "{command}"
expect {{
    "password:" {{ send "{self.ssh_pass}\\r"; exp_continue }}
    "Password:" {{ send "{self.ssh_pass}\\r"; exp_continue }}
    timeout {{ exit 1 }}
    eof
}}
'''
        try:
            result = subprocess.run(
                ["expect", "-c", expect_script],
                capture_output=True,
                text=True,
                timeout=self.ssh_timeout + 5
            )
            if result.returncode == 0:
                # Parse output, skip the spawn and password lines
                lines = result.stdout.strip().split('\n')
                # Filter out expect noise
                output_lines = [
                    l for l in lines
                    if not l.startswith('spawn ')
                    and 'password' not in l.lower()
                    and not l.startswith('Connection to')
                ]
                return '\n'.join(output_lines).strip()
        except Exception:
            pass
        return None


async def discover_network(
    subnet: str,
    ssh_user: Optional[str] = None,
    ssh_pass: Optional[str] = None
) -> List[DiscoveredDevice]:
    """
    Convenience function to discover network devices.

    Args:
        subnet: CIDR notation subnet
        ssh_user: SSH username for probing
        ssh_pass: SSH password for probing

    Returns:
        List of discovered devices
    """
    discovery = NetworkDiscovery(ssh_user=ssh_user, ssh_pass=ssh_pass)
    return await discovery.discover(subnet)


def format_discovery_table(devices: List[DiscoveredDevice]) -> str:
    """Format discovered devices as a table."""
    if not devices:
        return "No devices found."

    lines = []
    lines.append("=" * 80)
    lines.append(f"{'IP':<16} {'Hostname':<20} {'OS':<10} {'SSH':<5} {'Claude':<12} {'Capabilities'}")
    lines.append("-" * 80)

    for d in sorted(devices, key=lambda x: x.ip):
        ssh_status = "Yes" if d.ssh_available else "No"
        claude_status = d.claude_version[:10] if d.claude_version else "-"
        caps = ", ".join(d.capabilities) if d.capabilities else "-"
        hostname = d.hostname or "-"
        os_type = d.os_type or "-"

        lines.append(
            f"{d.ip:<16} {hostname:<20} {os_type:<10} {ssh_status:<5} {claude_status:<12} {caps}"
        )

    lines.append("=" * 80)
    lines.append(f"Total: {len(devices)} devices found")

    return "\n".join(lines)


def generate_config_suggestion(devices: List[DiscoveredDevice]) -> str:
    """Generate suggested config.yaml content based on discovered devices."""
    workers = []
    routing = []

    for device in devices:
        if not device.ssh_available:
            continue

        # Generate worker name
        name = device.hostname or f"worker-{device.ip.split('.')[-1]}"
        name = name.replace('-', '_').replace('.', '_')

        # Determine capabilities and routing
        caps = device.capabilities or []

        workers.append({
            "name": name,
            "host": device.ip,
            "capabilities": caps
        })

        # Add routing rules
        if "docker" in caps:
            routing.append({"pattern": "docker|container|容器", "worker": name})
        if "gpu" in caps:
            routing.append({"pattern": "gpu|cuda|模型|训练", "worker": name})
        if "git" in caps:
            routing.append({"pattern": "git|代码|编译", "worker": name})

    # Generate YAML
    lines = ["# Generated by hive discover", "# Edit as needed", "", "workers:"]

    for w in workers:
        lines.append(f"  {w['name']}:")
        lines.append(f"    host: {w['host']}")
        lines.append(f"    port: 8765")
        if w['capabilities']:
            lines.append(f"    capabilities: [{', '.join(w['capabilities'])}]")
        lines.append("")

    if routing:
        lines.append("routing:")
        for r in routing:
            lines.append(f"  - pattern: \"{r['pattern']}\"")
            lines.append(f"    worker: {r['worker']}")
        lines.append("")

    if workers:
        lines.append(f"default_worker: {workers[0]['name']}")

    return "\n".join(lines)
