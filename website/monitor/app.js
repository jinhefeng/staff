const DATA_URL = 'data.json';
const REFRESH_INTERVAL = 60; // seconds

let countdown = REFRESH_INTERVAL;

// DOM Elements
const elements = {
    time: document.getElementById('current-time'),
    date: document.getElementById('current-date'),
    refreshTimer: document.getElementById('refresh-timer'),
    lastSync: document.getElementById('last-sync'),
    statTickets: document.getElementById('stat-tickets'),
    statHeartbeat: document.getElementById('stat-heartbeat'),
    statSessions: document.getElementById('stat-sessions'),
    statDeferred: document.getElementById('stat-deferred'),
    statCron: document.getElementById('stat-cron'),
    ticketList: document.getElementById('ticket-list'),
    heartbeatList: document.getElementById('heartbeat-list'),
    sessionList: document.getElementById('session-list'),
    cronList: document.getElementById('cron-list'),
    eventList: document.getElementById('event-list')
};

function updateClock() {
    const now = new Date();
    elements.time.textContent = now.toLocaleTimeString('zh-CN', { hour12: false });
    elements.date.textContent = now.toLocaleDateString('zh-CN').replace(/\//g, '.');
}

async function fetchData() {
    try {
        const response = await fetch(DATA_URL + '?t=' + Date.now());
        const data = await response.json();
        renderDashboard(data);
        countdown = REFRESH_INTERVAL;
    } catch (error) {
        console.error('Failed to fetch data:', error);
    }
}

function renderDashboard(data) {
    // Stats
    elements.statTickets.textContent = data.tickets.total_active;
    elements.statHeartbeat.textContent = data.heartbeat.tasks.length;
    elements.statSessions.textContent = data.sessions.active_count;
    elements.statDeferred.textContent = data.deferred_tasks.length;
    elements.statCron.textContent = data.cron_jobs ? data.cron_jobs.length : 0;
    
    const syncDate = new Date(data.last_updated);
    elements.lastSync.textContent = syncDate.toLocaleTimeString('zh-CN', { hour12: false });

    // Render Tickets
    elements.ticketList.innerHTML = data.tickets.items.length ? '' : '<div class="loading-placeholder">暂无活跃工单</div>';
    data.tickets.items.forEach(ticket => {
        const isDeferred = ticket.content.includes('[DEFERRED TASK]');
        const html = `
            <div class="item ticket ${isDeferred ? 'deferred' : ''}">
                <div class="item-meta">
                    <span class="ticket-id">${ticket.id}</span>
                    <span class="ticket-guest">${ticket.guest}</span>
                    <span class="ticket-time">${formatTime(ticket.created_at)}</span>
                </div>
                <div class="item-content">${escapeHTML(ticket.content)}</div>
            </div>
        `;
        elements.ticketList.insertAdjacentHTML('beforeend', html);
    });

    // Render Heartbeat
    elements.heartbeatList.innerHTML = data.heartbeat.tasks.length ? '' : '<div class="loading-placeholder">无待办任务</div>';
    data.heartbeat.tasks.forEach(task => {
        const html = `
            <div class="hb-item">
                <span class="hb-status ${task.status}"></span>
                <span class="hb-text">${escapeHTML(task.text)}</span>
            </div>
        `;
        elements.heartbeatList.insertAdjacentHTML('beforeend', html);
    });

    // Render Sessions
    elements.sessionList.innerHTML = '';
    data.sessions.recent.forEach(session => {
        const html = `
            <div class="session-item">
                <span class="session-name">${session.name.replace('.jsonl', '')}</span>
                <span class="session-time">${formatTime(session.last_modified)}</span>
            </div>
        `;
        elements.sessionList.insertAdjacentHTML('beforeend', html);
    });

    // Render Cron Jobs
    if (elements.cronList) {
        elements.cronList.innerHTML = (data.cron_jobs && data.cron_jobs.length) ? '' : '<div class="loading-placeholder">暂无定时任务</div>';
        (data.cron_jobs || []).forEach(job => {
            let nextRunStr = "N/A";
            if (job.next_run_ms) {
                const nowMs = Date.now();
                const diffMs = job.next_run_ms - nowMs;
                if (diffMs <= 0) {
                    nextRunStr = "Running/Pending";
                } else if (diffMs < 60000) {
                    nextRunStr = `In ${Math.ceil(diffMs / 1000)}s`;
                } else if (diffMs < 3600000) {
                    nextRunStr = `In ${Math.ceil(diffMs / 60000)}m`;
                } else {
                    nextRunStr = new Date(job.next_run_ms).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
                }
            }
            
            const html = `
                <div class="cron-item ${!job.enabled ? 'disabled' : ''}">
                    <div class="cron-header">
                        <span class="cron-name">${escapeHTML(job.name || job.id)}</span>
                        <span class="cron-next">${nextRunStr}</span>
                    </div>
                    <div class="cron-details">
                        <span class="cron-schedule">${escapeHTML(job.schedule_text)}</span>
                        ${job.stop_condition ? `<span class="cron-stop" title="Stop Condition">🛑 ${escapeHTML(job.stop_condition)}</span>` : ''}
                    </div>
                </div>
            `;
            elements.cronList.insertAdjacentHTML('beforeend', html);
        });
    }

    // Render Events
    elements.eventList.innerHTML = data.events.length ? '' : '<div class="loading-placeholder">暂无系统动态</div>';
    data.events.forEach(event => {
        // Simple markdown strip for cleaner look in list
        const cleanContent = event.content.replace(/\*\*/g, '').replace(/###/g, '').trim();
        const html = `
            <div class="event-item ${event.is_silent ? 'silent' : ''}">
                <div class="event-meta">
                    <span class="event-tag">${event.is_silent ? 'SILENT_GUARD' : 'NOTIFICATION'}</span>
                    <span class="event-time">${formatDetailedTime(event.timestamp)}</span>
                </div>
                <div class="event-content">${escapeHTML(cleanContent)}</div>
            </div>
        `;
        elements.eventList.insertAdjacentHTML('beforeend', html);
    });
}

function formatDetailedTime(isoString) {
    if (!isoString) return '--:--:--';
    const date = new Date(isoString);
    return date.toLocaleTimeString('zh-CN', { hour12: false });
}

function formatTime(isoString) {
    if (!isoString) return '--:--';
    const date = new Date(isoString);
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function escapeHTML(str) {
    const p = document.createElement('p');
    p.textContent = str;
    return p.innerHTML;
}

// Timer Logic
setInterval(() => {
    updateClock();
    countdown--;
    if (countdown <= 0) {
        fetchData();
    }
    elements.refreshTimer.textContent = countdown;
}, 1000);

// Init
updateClock();
fetchData();
