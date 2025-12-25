#!/bin/bash
#
# Claude-Hive Worker Installation Script
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/Genius-Cai/claude-hive/main/scripts/install-worker.sh | bash
#
# Or with options:
#   bash install-worker.sh --port 8765 --name my-worker
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Defaults
PORT=8765
WORKER_NAME=$(hostname)
INSTALL_DIR="$HOME/claude-hive-worker"
REPO_URL="https://raw.githubusercontent.com/Genius-Cai/claude-hive/main"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --name)
            WORKER_NAME="$2"
            shift 2
            ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           🐝 Claude-Hive Worker Installer                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check for Claude Code
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v claude &> /dev/null; then
    echo -e "${RED}Error: Claude Code CLI not found.${NC}"
    echo "Please install it first: npm install -g @anthropic-ai/claude-code"
    exit 1
fi
echo -e "${GREEN}✓ Claude Code CLI found${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 not found.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 3 found${NC}"

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ $(echo "$PYTHON_VERSION < 3.10" | bc -l) -eq 1 ]]; then
    echo -e "${RED}Error: Python 3.10+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"

# Create install directory
echo -e "${YELLOW}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Download worker files
echo -e "${YELLOW}Downloading worker files...${NC}"
curl -sSL "$REPO_URL/worker/server.py" -o server.py
curl -sSL "$REPO_URL/requirements.txt" -o requirements.txt

# Install dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
pip3 install --user fastapi uvicorn pydantic

# Create systemd service (Linux only)
if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl &> /dev/null; then
    echo -e "${YELLOW}Creating systemd service...${NC}"

    SERVICE_FILE="/etc/systemd/system/claude-hive-worker.service"

    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Claude-Hive Worker
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment="HIVE_WORKER_NAME=$WORKER_NAME"
ExecStart=$(which python3) $INSTALL_DIR/server.py --port $PORT --name $WORKER_NAME
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable claude-hive-worker
    sudo systemctl start claude-hive-worker

    echo -e "${GREEN}✓ Systemd service created and started${NC}"
else
    echo -e "${YELLOW}Note: Manual startup required (systemd not available)${NC}"
    echo "  Run: python3 $INSTALL_DIR/server.py --port $PORT --name $WORKER_NAME"
fi

# Create hive directory
mkdir -p "$HOME/.claude-hive"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           🐝 Installation Complete!                          ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Worker Name: $WORKER_NAME${NC}"
echo -e "${GREEN}║  Port:        $PORT${NC}"
echo -e "${GREEN}║  URL:         http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):$PORT${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Test with:"
echo "  curl http://localhost:$PORT/health"
echo ""
