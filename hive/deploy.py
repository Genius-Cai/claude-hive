"""
Deployment module for claude-hive.

Handles remote deployment of worker nodes via SSH.
"""

import subprocess
import shutil
from dataclasses import dataclass
from typing import Optional, List, Callable
from enum import Enum


class DeployStep(Enum):
    """Deployment step identifiers."""
    CHECK_PYTHON = "check_python"
    INSTALL_DEPS = "install_deps"
    CHECK_NODE = "check_node"
    INSTALL_NODE = "install_node"
    INSTALL_CLAUDE = "install_claude"
    CREATE_WORKER_DIR = "create_worker_dir"
    DOWNLOAD_WORKER = "download_worker"
    CREATE_SERVICE = "create_service"
    START_SERVICE = "start_service"
    VERIFY = "verify"


@dataclass
class DeployResult:
    """Result of a deployment operation."""
    success: bool
    step: DeployStep
    message: str
    output: Optional[str] = None


class WorkerDeployer:
    """Deploys worker nodes to remote machines."""

    WORKER_URL = "https://raw.githubusercontent.com/Genius-Cai/claude-hive/main/worker/server.py"
    DEFAULT_PORT = 8765

    def __init__(
        self,
        ssh_user: str,
        ssh_pass: str,
        ssh_timeout: int = 30,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.ssh_timeout = ssh_timeout
        self.progress_callback = progress_callback or (lambda step, msg: None)

    def deploy(
        self,
        ip: str,
        name: str,
        port: int = DEFAULT_PORT,
        capabilities: Optional[List[str]] = None
    ) -> List[DeployResult]:
        """
        Deploy a worker to a remote machine.

        Args:
            ip: Target IP address
            name: Worker name
            port: Port to run worker on
            capabilities: List of worker capabilities

        Returns:
            List of deployment step results
        """
        results = []
        caps = capabilities or []

        # Check if expect is available
        if not shutil.which("expect"):
            return [DeployResult(
                success=False,
                step=DeployStep.CHECK_PYTHON,
                message="'expect' command not found. Please install: brew install expect (macOS) or apt install expect (Linux)"
            )]

        # Step 1: Check Python
        self.progress_callback("check_python", "Checking Python installation...")
        result = self._ssh_exec(ip, "python3 --version")
        if not result or "Python" not in result:
            results.append(DeployResult(
                success=False,
                step=DeployStep.CHECK_PYTHON,
                message="Python3 not found on target machine"
            ))
            return results
        results.append(DeployResult(
            success=True,
            step=DeployStep.CHECK_PYTHON,
            message=f"Python found: {result.strip()}"
        ))

        # Step 2: Install Python dependencies
        self.progress_callback("install_deps", "Installing Python dependencies...")
        result = self._ssh_exec(
            ip,
            "pip3 install fastapi uvicorn httpx --break-system-packages 2>&1 || pip3 install fastapi uvicorn httpx 2>&1",
            timeout=120
        )
        results.append(DeployResult(
            success=True,
            step=DeployStep.INSTALL_DEPS,
            message="Python dependencies installed",
            output=result
        ))

        # Step 3: Check Node.js
        self.progress_callback("check_node", "Checking Node.js installation...")
        result = self._ssh_exec(ip, "which node && node --version")
        if not result or "node" not in result.lower():
            # Step 3b: Install Node.js
            self.progress_callback("install_node", "Installing Node.js...")
            install_cmd = """
            if command -v apt-get &> /dev/null; then
                curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs
            elif command -v yum &> /dev/null; then
                curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash - && sudo yum install -y nodejs
            else
                echo "Unsupported package manager"
                exit 1
            fi
            """
            result = self._ssh_exec_sudo(ip, install_cmd, timeout=180)
            if not result or "error" in result.lower():
                results.append(DeployResult(
                    success=False,
                    step=DeployStep.INSTALL_NODE,
                    message="Failed to install Node.js",
                    output=result
                ))
                return results
            results.append(DeployResult(
                success=True,
                step=DeployStep.INSTALL_NODE,
                message="Node.js installed"
            ))
        else:
            results.append(DeployResult(
                success=True,
                step=DeployStep.CHECK_NODE,
                message=f"Node.js found: {result.strip()}"
            ))

        # Step 4: Install Claude Code CLI
        self.progress_callback("install_claude", "Installing Claude Code CLI...")
        result = self._ssh_exec_sudo(ip, "npm install -g @anthropic-ai/claude-code", timeout=120)
        results.append(DeployResult(
            success=True,
            step=DeployStep.INSTALL_CLAUDE,
            message="Claude Code CLI installed",
            output=result
        ))

        # Step 5: Create worker directory
        self.progress_callback("create_dir", "Creating worker directory...")
        self._ssh_exec(ip, "mkdir -p ~/claude-hive-worker")
        results.append(DeployResult(
            success=True,
            step=DeployStep.CREATE_WORKER_DIR,
            message="Worker directory created"
        ))

        # Step 6: Download worker code
        self.progress_callback("download", "Downloading worker code...")
        result = self._ssh_exec(ip, f"curl -o ~/claude-hive-worker/server.py {self.WORKER_URL}")
        results.append(DeployResult(
            success=True,
            step=DeployStep.DOWNLOAD_WORKER,
            message="Worker code downloaded"
        ))

        # Step 7: Create systemd service
        self.progress_callback("create_service", "Creating systemd service...")
        service_content = self._generate_service_file(name, port)
        create_cmd = f'''cat << 'SERVICEEOF' | sudo tee /etc/systemd/system/claude-hive-worker.service
{service_content}
SERVICEEOF'''
        result = self._ssh_exec_sudo(ip, create_cmd)
        results.append(DeployResult(
            success=True,
            step=DeployStep.CREATE_SERVICE,
            message="Systemd service created"
        ))

        # Step 8: Start service
        self.progress_callback("start_service", "Starting worker service...")
        result = self._ssh_exec_sudo(ip, "systemctl daemon-reload && systemctl enable claude-hive-worker && systemctl restart claude-hive-worker")
        results.append(DeployResult(
            success=True,
            step=DeployStep.START_SERVICE,
            message="Worker service started"
        ))

        # Step 9: Verify
        self.progress_callback("verify", "Verifying deployment...")
        import time
        time.sleep(2)  # Wait for service to start

        result = self._ssh_exec(ip, f"curl -s http://localhost:{port}/health")
        if result and "ok" in result.lower():
            results.append(DeployResult(
                success=True,
                step=DeployStep.VERIFY,
                message="Deployment verified successfully!",
                output=result
            ))
        else:
            results.append(DeployResult(
                success=False,
                step=DeployStep.VERIFY,
                message="Verification failed - worker may not be running correctly",
                output=result
            ))

        return results

    def _generate_service_file(self, name: str, port: int) -> str:
        """Generate systemd service file content."""
        return f'''[Unit]
Description=Claude-Hive Worker
After=network.target

[Service]
Type=simple
User={self.ssh_user}
WorkingDirectory=/home/{self.ssh_user}/claude-hive-worker
Environment="HIVE_WORKER_NAME={name}"
Environment="PATH=/usr/local/bin:/home/{self.ssh_user}/.local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/python3 /home/{self.ssh_user}/claude-hive-worker/server.py --port {port} --name {name}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target'''

    def _ssh_exec(self, ip: str, command: str, timeout: int = None) -> Optional[str]:
        """Execute command via SSH."""
        timeout = timeout or self.ssh_timeout
        expect_script = f'''
spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {self.ssh_user}@{ip} "{command}"
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
            return '\n'.join(clean_lines).strip()
        except Exception as e:
            return None

    def _ssh_exec_sudo(self, ip: str, command: str, timeout: int = None) -> Optional[str]:
        """Execute sudo command via SSH."""
        timeout = timeout or self.ssh_timeout
        # Wrap command with sudo
        sudo_cmd = f'sudo -S bash -c "{command}"'
        expect_script = f'''
spawn ssh -tt -o StrictHostKeyChecking=no -o ConnectTimeout=10 {self.ssh_user}@{ip} "{sudo_cmd}"
expect {{
    "password:" {{ send "{self.ssh_pass}\\r"; exp_continue }}
    "Password:" {{ send "{self.ssh_pass}\\r"; exp_continue }}
    "password for" {{ send "{self.ssh_pass}\\r"; exp_continue }}
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
            lines = result.stdout.split('\n')
            clean_lines = [
                l for l in lines
                if not l.startswith('spawn ')
                and 'password' not in l.lower()
                and not l.startswith('Connection to')
                and '[sudo]' not in l
            ]
            return '\n'.join(clean_lines).strip()
        except Exception as e:
            return None


def deploy_worker(
    ip: str,
    name: str,
    ssh_user: str,
    ssh_pass: str,
    port: int = 8765,
    progress_callback: Optional[Callable[[str, str], None]] = None
) -> List[DeployResult]:
    """
    Convenience function to deploy a worker.

    Args:
        ip: Target IP address
        name: Worker name
        ssh_user: SSH username
        ssh_pass: SSH password
        port: Port to run worker on
        progress_callback: Optional callback for progress updates

    Returns:
        List of deployment step results
    """
    deployer = WorkerDeployer(
        ssh_user=ssh_user,
        ssh_pass=ssh_pass,
        progress_callback=progress_callback
    )
    return deployer.deploy(ip, name, port)


def format_deploy_results(results: List[DeployResult]) -> str:
    """Format deployment results for display."""
    lines = []
    lines.append("=" * 60)
    lines.append("Deployment Results")
    lines.append("-" * 60)

    all_success = True
    for r in results:
        status = "[OK]" if r.success else "[FAIL]"
        if not r.success:
            all_success = False
        lines.append(f"{status} {r.step.value}: {r.message}")

    lines.append("-" * 60)
    if all_success:
        lines.append("Deployment completed successfully!")
    else:
        lines.append("Deployment failed. Check errors above.")
    lines.append("=" * 60)

    return "\n".join(lines)
