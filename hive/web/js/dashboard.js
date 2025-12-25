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
                    connected: false
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
                // Keep last output for reference
                break;

            case 'task_error':
                worker.status = 'error';
                worker.lastOutput = event.error;
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
        let outputDisplay = '';
        if (!worker.connected) {
            outputDisplay = 'Connecting to worker...';
        } else if (worker.lastOutput) {
            outputDisplay = this.escapeHtml(worker.lastOutput);
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

        // Show full output log
        const outputText = worker.outputLog.join('\n') || worker.lastOutput || '(No output)';
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
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new HiveDashboard();
});
