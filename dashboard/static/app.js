const API = {
    status: '/api/status',
    balances: '/api/balances',
    trades: '/api/trades',
    stats: '/api/stats',
    positions: '/api/positions',
};

let equityChart = null;
let currentTradePage = 1;
const TRADE_PAGE_SIZE = 10;

function fmt(n) {
    if (n == null) return '--';
    return Number(n).toFixed(2);
}

function fmtPct(n) {
    if (n == null) return '--';
    return (n >= 0 ? '+' : '') + Number(n).toFixed(2) + '%';
}

function timeShort(iso) {
    if (!iso) return '--';
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
}

async function fetchAPI(url) {
    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(resp.statusText);
        return await resp.json();
    } catch (e) {
        console.error(`Fetch ${url} failed:`, e);
        return null;
    }
}

async function updateStatus() {
    const data = await fetchAPI(API.status);
    if (!data) return;
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (data.running) {
        dot.className = 'status-dot online';
        text.textContent = `运行中 (${data.mode})`;
        text.style.color = '#00d4aa';
    } else {
        dot.className = 'status-dot offline';
        text.textContent = '可能已停止';
        text.style.color = '#ff4757';
    }
}

async function updateBalances() {
    const data = await fetchAPI(API.balances);
    if (!data || !data.latest) return;

    const usdt = data.latest['USDT'];
    if (usdt) {
        document.getElementById('cardBalance').innerHTML =
            `${fmt(usdt.total)} <span class="unit">USDT</span>`;
    }

    if (data.history && data.history.length > 0) {
        const labels = data.history.map(h => timeShort(h.time));
        const values = data.history.map(h => h.value);

        if (equityChart) {
            equityChart.data.labels = labels;
            equityChart.data.datasets[0].data = values;
            equityChart.update('none');
        } else {
            const ctx = document.getElementById('equityChart').getContext('2d');
            equityChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: '净值 USDT',
                        data: values,
                        borderColor: '#00d4aa',
                        backgroundColor: 'rgba(0, 212, 170, 0.08)',
                        fill: true,
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: {
                            ticks: { color: '#888', maxTicksLimit: 8, font: { size: 10 } },
                            grid: { color: 'rgba(42, 42, 74, 0.5)' }
                        },
                        y: {
                            ticks: { color: '#888', font: { size: 10 }, callback: v => v.toFixed(0) },
                            grid: { color: 'rgba(42, 42, 74, 0.5)' }
                        }
                    },
                    interaction: { intersect: false, mode: 'index' }
                }
            });
        }
    }
}

async function updateStats() {
    const data = await fetchAPI(API.stats);
    if (!data) return;

    const posData = await fetchAPI(API.positions);
    const posCount = posData ? posData.length : 0;
    document.getElementById('cardPositions').innerHTML =
        `${posCount} <span class="unit">/ 2 max</span>`;

    if (data.today) {
        const pnl = data.today.pnl || 0;
        const pnlPct = data.today.pnl_pct || 0;
        const cls = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        document.getElementById('cardPnl').innerHTML =
            `<span class="${cls}">${fmtPct(pnlPct)}</span> <span class="unit">(${fmt(pnl)} USDT)</span>`;
    }

    document.getElementById('cardMode').textContent = 'Paper';
}

async function updatePositions() {
    const data = await fetchAPI(API.positions);
    const container = document.getElementById('positionsList');
    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无持仓</div>';
        return;
    }

    container.innerHTML = data.map(p => `
        <div class="position-item">
            <div>
                <div class="position-symbol">${p.symbol}</div>
                <div class="position-detail">入场 ${fmt(p.entry_price)} · ${fmt(p.quantity)} 张</div>
            </div>
            <div>
                <div class="position-detail">${p.side === 'buy' ? '做多' : '做空'}</div>
                <div class="position-detail">${timeShort(p.entry_time)}</div>
            </div>
        </div>
    `).join('');
}

async function updateTrades(page) {
    const data = await fetchAPI(`${API.trades}?page=${page}&size=${TRADE_PAGE_SIZE}`);
    if (!data) return;

    const tbody = document.getElementById('tradesBody');
    if (data.trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-state">暂无交易记录</td></tr>';
        document.getElementById('pagination').innerHTML = '';
        return;
    }

    tbody.innerHTML = data.trades.map(t => {
        const sideCls = t.side === 'buy' ? 'trade-buy' : 'trade-sell';
        const pnlCls = (t.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
        return `<tr>
            <td>${timeShort(t.entry_time)}</td>
            <td><strong>${t.symbol}</strong></td>
            <td class="${sideCls}">${t.side === 'buy' ? '买入' : '卖出'}</td>
            <td>${fmt(t.entry_price)}</td>
            <td>${t.exit_price ? fmt(t.exit_price) : '--'}</td>
            <td>${fmt(t.quantity)}</td>
            <td class="${pnlCls}">${t.pnl != null ? fmt(t.pnl) : '--'}</td>
            <td class="${pnlCls}">${t.pnl_pct != null ? fmtPct(t.pnl_pct) : '--'}</td>
            <td>${t.status === 'open' ? '🟢 持仓中' : '已平仓'}</td>
            <td>${t.exit_reason || '--'}</td>
        </tr>`;
    }).join('');

    const totalPages = Math.ceil(data.total / TRADE_PAGE_SIZE);
    const pag = document.getElementById('pagination');
    if (totalPages <= 1) { pag.innerHTML = ''; return; }
    pag.innerHTML = `
        <button onclick="changePage(${page - 1})" ${page <= 1 ? 'disabled' : ''}>上一页</button>
        <span>${page} / ${totalPages}</span>
        <button onclick="changePage(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>下一页</button>
    `;
}

function changePage(page) {
    currentTradePage = page;
    updateTrades(page);
}

async function refresh() {
    document.getElementById('updateTime').textContent =
        new Date().toLocaleTimeString('zh-CN');
    await Promise.all([
        updateStatus(),
        updateBalances(),
        updateStats(),
        updatePositions(),
        updateTrades(currentTradePage),
    ]);
}

refresh();
setInterval(refresh, 30000);
