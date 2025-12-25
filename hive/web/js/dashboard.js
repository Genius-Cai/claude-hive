/**
 * Claude-Hive Dashboard
 *
 * Connects directly to each worker's SSE endpoint for real-time monitoring.
 * Does NOT go through Controller Claude - zero token overhead.
 */

class HiveDashboard {
    constructor() {
        this.workers = {};
        this.eventSources = {};
        this.selectedWorker = null;
        this.autoRefresh = true;

        this.init();
    }

    async init() {
        // Get config from API
        await this.loadConfig();

        // Set up UI event listeners
        this.setupEventListeners();

        // Connect to all workers
        this.connectAll();

        // Start polling for offline workers
        setInterval(() => this.checkOfflineWorkers(), 10000);

        // Periodically refresh cards to check idle timeout (every minute)
        setInterval(() => this.refreshIdleCards(), 60000);
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();

            // Initialize worker state from config
            for (const [name, workerConfig] of Object.entries(config.workers || {})) {
                this.workers[name] = {
                    name,
                    host: workerConfig.host,
                    port: workerConfig.port || 8765,
                    status: 'offline',
                    currentTask: null,
                    lastOutput: '',
                    outputLog: [],
                    elapsed: null,
                    connected: false,
                    lastTaskTime: null  // Track when last task completed
                };
            }

            this.renderWorkers();
        } catch (error) {
            console.error('Failed to load config:', error);
            // Show error state
            document.getElementById('connection-status').className = 'status-badge offline';
            document.getElementById('connection-status').textContent = 'Config Error';
        }
    }

    setupEventListeners() {
        // Auto-refresh toggle
        document.getElementById('auto-refresh').addEventListener('change', (e) => {
            this.autoRefresh = e.target.checked;
            if (this.autoRefresh) {
                this.connectAll();
            } else {
                this.disconnectAll();
            }
        });

        // Modal close
        document.getElementById('modal-close').addEventListener('click', () => {
            this.closeModal();
        });

        // Close modal on backdrop click
        document.getElementById('worker-modal').addEventListener('click', (e) => {
            if (e.target.id === 'worker-modal') {
                this.closeModal();
            }
        });

        // Close modal on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });
    }

    connectAll() {
        for (const name of Object.keys(this.workers)) {
            this.connectWorker(name);
        }
    }

    disconnectAll() {
        for (const name of Object.keys(this.eventSources)) {
            if (this.eventSources[name]) {
                this.eventSources[name].close();
                delete this.eventSources[name];
            }
        }
    }

    connectWorker(name) {
        const worker = this.workers[name];
        if (!worker) return;

        // Close existing connection
        if (this.eventSources[name]) {
            this.eventSources[name].close();
        }

        const url = `http://${worker.host}:${worker.port}/stream`;

        try {
            const eventSource = new EventSource(url);
            this.eventSources[name] = eventSource;

            eventSource.onopen = () => {
                const wasOffline = !worker.connected;
                worker.connected = true;
                this.updateWorkerCard(name, wasOffline);
                this.updateConnectionStatus();
            };

            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWorkerEvent(name, data);
                } catch (e) {
                    console.error('Failed to parse event:', e);
                }
            };

            eventSource.onerror = () => {
                const wasOnline = worker.connected;
                worker.connected = false;
                worker.status = 'offline';
                this.updateWorkerCard(name, wasOnline);
                this.updateConnectionStatus();

                // Reconnect after delay
                eventSource.close();
                delete this.eventSources[name];

                if (this.autoRefresh) {
                    setTimeout(() => this.connectWorker(name), 5000);
                }
            };
        } catch (error) {
            console.error(`Failed to connect to ${name}:`, error);
            const wasOnline = worker.connected;
            worker.connected = false;
            worker.status = 'offline';
            this.updateWorkerCard(name, wasOnline);
        }
    }

    handleWorkerEvent(name, event) {
        const worker = this.workers[name];
        if (!worker) return;

        worker.connected = true;

        switch (event.type) {
            case 'status':
                worker.status = event.status || 'idle';
                worker.currentTask = event.current_task;
                worker.lastOutput = event.last_output || '';
                worker.elapsed = event.elapsed;
                break;

            case 'task_start':
                worker.status = 'executing';
                worker.currentTask = event.task;
                worker.outputLog = [];
                worker.elapsed = 0;
                break;

            case 'output':
                worker.lastOutput = event.line;
                worker.outputLog.push(event.line);
                worker.elapsed = event.elapsed;
                // Keep output log manageable
                if (worker.outputLog.length > 500) {
                    worker.outputLog = worker.outputLog.slice(-500);
                }
                break;

            case 'task_complete':
                worker.status = 'idle';
                worker.elapsed = event.elapsed;
                worker.lastTaskTime = Date.now();  // Track completion time
                break;

            case 'task_error':
                worker.status = 'error';
                worker.lastOutput = event.error;
                worker.lastTaskTime = Date.now();  // Track completion time
                break;
        }

        this.updateWorkerCard(name);

        // Update modal if this worker is selected
        if (this.selectedWorker === name) {
            this.updateModal();
        }
    }

    async checkOfflineWorkers() {
        for (const [name, worker] of Object.entries(this.workers)) {
            if (!worker.connected && this.autoRefresh) {
                // Try to reconnect
                this.connectWorker(name);
            }
        }
    }

    /**
     * Refresh idle worker cards to trigger timeout check
     */
    refreshIdleCards() {
        const IDLE_TIMEOUT = 5 * 60 * 1000; // 5 minutes
        for (const [name, worker] of Object.entries(this.workers)) {
            if (worker.status === 'idle' &&
                worker.lastTaskTime &&
                (Date.now() - worker.lastTaskTime > IDLE_TIMEOUT)) {
                // Clear old output and refresh card
                worker.currentTask = null;
                this.updateWorkerCard(name);
            }
        }
    }

    renderWorkers() {
        const grid = document.getElementById('workers-grid');
        grid.innerHTML = '';

        // Sort workers: online first, offline last
        const sortedWorkers = Object.entries(this.workers).sort(([, a], [, b]) => {
            if (a.connected === b.connected) return 0;
            return a.connected ? -1 : 1;
        });

        for (const [name, worker] of sortedWorkers) {
            const card = this.createWorkerCard(name, worker);
            grid.appendChild(card);
        }
    }

    createWorkerCard(name, worker) {
        const card = document.createElement('div');
        card.className = `worker-card ${worker.connected ? worker.status : 'offline'}`;
        card.id = `worker-${name}`;
        card.onclick = () => this.openModal(name);

        // Format output for display
        // Clear output after 5 minutes of idle to show ready state
        const IDLE_TIMEOUT = 5 * 60 * 1000; // 5 minutes
        const isIdleTooLong = worker.status === 'idle' &&
            worker.lastTaskTime &&
            (Date.now() - worker.lastTaskTime > IDLE_TIMEOUT);

        let outputDisplay = '';
        if (!worker.connected) {
            outputDisplay = 'Connecting to worker...';
        } else if (isIdleTooLong) {
            // Clear old output after 5 minutes of idle
            outputDisplay = 'Worker ready, waiting for tasks...';
        } else if (worker.lastOutput) {
            outputDisplay = this.parseOutput(worker.lastOutput);
        } else if (worker.status === 'idle') {
            outputDisplay = 'Worker ready, waiting for tasks...';
        } else {
            outputDisplay = 'Processing...';
        }

        // Status display
        let statusDisplay = '';
        if (!worker.connected) {
            statusDisplay = `<span style="color:#ef4444">Offline</span> - ${worker.host}`;
        } else if (worker.currentTask) {
            statusDisplay = worker.currentTask;
        } else {
            statusDisplay = `<span style="color:#4ade80">Online</span> - Ready`;
        }

        card.innerHTML = `
            <div class="worker-header">
                <div>
                    <div class="worker-name">${name}</div>
                    <div class="worker-ip">${worker.host}:${worker.port}</div>
                </div>
                <div class="worker-status-dot ${worker.connected ? worker.status : 'offline'}"></div>
            </div>
            <div class="worker-body">
                <div class="worker-task">${statusDisplay}</div>
                <div class="worker-output">${outputDisplay}</div>
            </div>
            <div class="worker-footer">
                <div class="worker-progress">
                    <div class="worker-progress-bar" style="width: ${this.getProgressWidth(worker)}%"></div>
                </div>
                <div class="worker-status-text ${worker.status}">
                    ${this.getStatusText(worker)}
                </div>
            </div>
        `;

        return card;
    }

    updateWorkerCard(name, connectionChanged = false) {
        const worker = this.workers[name];

        // Re-render entire grid if connection status changed (for sorting)
        if (connectionChanged) {
            this.renderWorkers();
            return;
        }

        const existingCard = document.getElementById(`worker-${name}`);
        if (existingCard) {
            const newCard = this.createWorkerCard(name, worker);
            existingCard.replaceWith(newCard);
        }
    }

    getProgressWidth(worker) {
        if (worker.status !== 'executing') return 0;
        // Simulate progress based on elapsed time (cap at 95%)
        if (!worker.elapsed) return 5;
        return Math.min(95, 5 + (worker.elapsed / 3)); // 3 seconds per % after initial 5%
    }

    getStatusText(worker) {
        if (!worker.connected) return 'Offline';
        if (worker.status === 'executing' && worker.elapsed) {
            return `${worker.elapsed.toFixed(1)}s`;
        }
        return worker.status.charAt(0).toUpperCase() + worker.status.slice(1);
    }

    updateConnectionStatus() {
        const connectedCount = Object.values(this.workers).filter(w => w.connected).length;
        const totalCount = Object.keys(this.workers).length;
        const statusEl = document.getElementById('connection-status');

        if (connectedCount === totalCount) {
            statusEl.className = 'status-badge online';
            statusEl.textContent = `${connectedCount}/${totalCount} Online`;
        } else if (connectedCount > 0) {
            statusEl.className = 'status-badge online';
            statusEl.textContent = `${connectedCount}/${totalCount} Online`;
        } else {
            statusEl.className = 'status-badge offline';
            statusEl.textContent = 'All Offline';
        }
    }

    openModal(name) {
        this.selectedWorker = name;
        document.getElementById('worker-modal').classList.remove('hidden');
        this.updateModal();
    }

    closeModal() {
        this.selectedWorker = null;
        document.getElementById('worker-modal').classList.add('hidden');
    }

    updateModal() {
        const worker = this.workers[this.selectedWorker];
        if (!worker) return;

        document.getElementById('modal-worker-name').textContent =
            `${this.selectedWorker} (${worker.host})`;

        document.getElementById('modal-task').textContent =
            `Task: ${worker.currentTask || '-'}`;

        document.getElementById('modal-duration').textContent =
            `Duration: ${worker.elapsed ? worker.elapsed.toFixed(1) + 's' : '-'}`;

        document.getElementById('modal-status').textContent =
            `Status: ${worker.status}`;

        // Show full output log (parse each line for JSON result)
        let outputText = '(No output)';
        if (worker.outputLog.length > 0) {
            outputText = worker.outputLog.map(line => this.parseOutputPlain(line)).join('\n');
        } else if (worker.lastOutput) {
            outputText = this.parseOutputPlain(worker.lastOutput);
        }
        document.getElementById('modal-output-text').textContent = outputText;

        // Auto-scroll to bottom
        const container = document.getElementById('modal-output');
        container.scrollTop = container.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Convert markdown to terminal-friendly format (Fluid Dark style)
     */
    mdToTerminal(text) {
        if (!text) return text;

        return text
            // Headers: ## Title → ◆ TITLE (uppercase, accent)
            .replace(/^#{1,2}\s+(.+)$/gm, (_, title) => `◆ ${title.toUpperCase()}`)
            // Subheaders: ### Title → ◇ Title
            .replace(/^#{3,6}\s+(.+)$/gm, '◇ $1')
            // Bold: **text** → 「text」
            .replace(/\*\*(.+?)\*\*/g, '「$1」')
            // Italic: *text* → text
            .replace(/\*(.+?)\*/g, '$1')
            // Table separators: |---|---| → remove
            .replace(/^\|[-:\s|]+\|$/gm, '')
            // 2-column tables: | key | value | → key: value
            .replace(/^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|$/gm, '  $1: $2')
            // 3-column tables: | a | b | c | → a: b (c)
            .replace(/^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|$/gm, '  $1: $2 ($3)')
            // 4+ column tables: simplify to comma separated
            .replace(/^\|\s*(.+?)\s*\|$/gm, (_, content) => {
                const cols = content.split('|').map(s => s.trim()).filter(s => s);
                if (cols.length >= 4) {
                    return '  ' + cols[0] + ': ' + cols.slice(1).join(', ');
                }
                return '  ' + cols.join(': ');
            })
            // List items: - item → › item
            .replace(/^-\s+/gm, '› ')
            // Checkboxes
            .replace(/^-\s*\[x\]/gm, '✓')
            .replace(/^-\s*\[\s*\]/gm, '○')
            // Status icons
            .replace(/✅/g, '●')
            .replace(/⚠️/g, '▲')
            .replace(/❌/g, '✕')
            // Clean up extra blank lines
            .replace(/\n{3,}/g, '\n\n')
            .trim();
    }

    /**
     * Extract result content from worker output
     * Handles JSON with escaped newlines (\n as literal characters)
     */
    extractResult(text) {
        if (!text) return text;

        // Method 1: Find "result":" and extract content
        const resultIndex = text.indexOf('"result":"');
        if (resultIndex !== -1) {
            let content = text.substring(resultIndex + 10); // Skip past "result":"

            // Find the closing - handle escaped quotes
            let end = content.length;
            let depth = 0;
            for (let i = 0; i < content.length; i++) {
                if (content[i] === '\\' && i + 1 < content.length) {
                    i++; // Skip escaped character
                    continue;
                }
                if (content[i] === '"' && depth === 0) {
                    end = i;
                    break;
                }
            }

            content = content.substring(0, end);

            // Unescape JSON string
            return content
                .replace(/\\n/g, '\n')
                .replace(/\\t/g, '\t')
                .replace(/\\"/g, '"')
                .replace(/\\\\/g, '\\');
        }

        // Method 2: Try standard JSON.parse
        try {
            const json = JSON.parse(text);
            if (json.result !== undefined) return json.result;
            if (json.error) return `[ERROR] ${json.error}`;
        } catch (e) {
            // Not valid JSON
        }

        return text;
    }

    /**
     * Parse output for card view (preview only)
     */
    parseOutput(text) {
        if (!text) return '';

        let content = this.extractResult(text);
        content = this.mdToTerminal(content);

        // Get first few lines for preview
        const lines = content.split('\n')
            .filter(line => line.trim())
            .slice(0, 5);

        return this.escapeHtml(lines.join('\n')).replace(/\n/g, '<br>');
    }

    /**
     * Parse output for modal view (full content)
     */
    parseOutputPlain(text) {
        if (!text) return '';
        const content = this.extractResult(text);
        return this.mdToTerminal(content);
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new HiveDashboard();
});
