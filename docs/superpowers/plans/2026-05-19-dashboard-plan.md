# Dashboard 可视化面板实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个独立 Docker 容器的 Web 仪表盘，显示交易机器人的运行状态、余额、净值曲线、交易记录。

**Architecture:** FastAPI 后端读取共享 SQLite 数据库，提供 5 个 REST API 端点。前端为纯 HTML + Chart.js 单页面，暗色主题，每 30 秒轮询更新。

**Tech Stack:** FastAPI 0.100+, uvicorn 0.23+, Chart.js 4.x (CDN), Python 3.11-slim Docker

---

### Task 1: 创建 dashboard 目录和 Dockerfile

**Files:**
- Create: `dashboard/Dockerfile`
- Create: `dashboard/requirements.txt`

- [ ] **Step 1: 创建 requirements.txt**

```txt
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
```

- [ ] **Step 2: 创建 Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dashboard/ /app/dashboard/
WORKDIR /app/dashboard
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 3: 验证 Dockerfile 构建**

```bash
docker build -f dashboard/Dockerfile -t dashboard-test .
```
Expected: 构建成功

- [ ] **Step 4: 提交**

```bash
git add dashboard/Dockerfile dashboard/requirements.txt
git commit -m "feat: add dashboard Dockerfile and requirements"
```

---

### Task 2: 创建 FastAPI 后端

**Files:**
- Create: `dashboard/main.py`

- [ ] **Step 1: 编写 main.py — FastAPI app 和 5 个端点**

```python
"""Crypto Trading Bot Dashboard — FastAPI backend."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Crypto Bot Dashboard")

DB_PATH = Path("/app/data/trading.db")


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@app.get("/api/status")
async def get_status():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT timestamp FROM balances ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"running": False, "mode": "unknown", "last_update": None}

    last_time = datetime.fromisoformat(row["timestamp"])
    now = datetime.now(timezone.utc)
    seconds_ago = (now - last_time).total_seconds()
    running = seconds_ago < 90

    return {
        "running": running,
        "mode": "paper",
        "last_update": row["timestamp"],
        "seconds_ago": round(seconds_ago, 1),
    }


@app.get("/api/balances")
async def get_balances():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT asset, free, used, total
            FROM balances
            WHERE (asset, timestamp) IN (
                SELECT asset, MAX(timestamp) FROM balances GROUP BY asset
            )
        """).fetchall()

        latest = {
            r["asset"]: {
                "free": round(r["free"], 2),
                "used": round(r["used"], 2),
                "total": round(r["total"], 2),
            }
            for r in rows
        }

        history = conn.execute("""
            SELECT timestamp, total FROM balances
            WHERE asset = 'USDT'
            ORDER BY timestamp DESC LIMIT 200
        """).fetchall()
    finally:
        conn.close()

    return {
        "latest": latest,
        "history": [
            {"time": r["timestamp"], "value": round(r["total"], 2)}
            for r in reversed(history)
        ],
    }


@app.get("/api/trades")
async def get_trades(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)
):
    conn = get_db()
    try:
        offset = (page - 1) * size
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, symbol, entry_time, exit_time, entry_price, exit_price,
                   quantity, side, status, exit_reason, pnl, pnl_pct
            FROM trades
            ORDER BY entry_time DESC
            LIMIT ? OFFSET ?
            """,
            (size, offset),
        ).fetchall()
    finally:
        conn.close()

    trades = []
    for r in rows:
        t = dict(r)
        if t["pnl"] is not None:
            t["pnl"] = round(t["pnl"], 2)
        if t["pnl_pct"] is not None:
            t["pnl_pct"] = round(t["pnl_pct"], 2)
        trades.append(t)

    return {"trades": trades, "total": total, "page": page, "size": size}


@app.get("/api/stats")
async def get_stats():
    conn = get_db()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_stats = conn.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (today,)
        ).fetchone()

        all_time = conn.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM trades WHERE status = 'closed'
        """).fetchone()
    finally:
        conn.close()

    total_trades = all_time["total_trades"] or 0
    wins = all_time["wins"] or 0

    return {
        "today": dict(today_stats) if today_stats else None,
        "all_time": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": total_trades - wins,
            "total_pnl": round(all_time["total_pnl"], 2),
            "win_rate": round(wins / total_trades * 100, 1) if total_trades else 0,
        },
    }


@app.get("/api/positions")
async def get_positions():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, symbol, entry_price, quantity, entry_time, side "
            "FROM trades WHERE status = 'open'"
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": r["id"],
            "symbol": r["symbol"],
            "entry_price": r["entry_price"],
            "quantity": r["quantity"],
            "entry_time": r["entry_time"],
            "side": r["side"],
        }
        for r in rows
    ]


# Mount static files AFTER all API routes
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
```

- [ ] **Step 2: 本地语法验证**

```bash
python -c "import ast; ast.parse(open('dashboard/main.py').read()); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add dashboard/main.py
git commit -m "feat: add dashboard FastAPI backend with 5 API endpoints"
```

---

### Task 3: 创建前端暗色主题样式

**Files:**
- Create: `dashboard/static/style.css`

- [ ] **Step 1: 编写 style.css**

```css
:root {
    --bg-primary: #1a1a2e;
    --bg-card: #16213e;
    --bg-hover: #1c2a4a;
    --text-primary: #e0e0e0;
    --text-secondary: #888;
    --accent-green: #00d4aa;
    --accent-red: #ff4757;
    --accent-blue: #4da6ff;
    --accent-orange: #ffaa00;
    --border: #2a2a4a;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.5;
}

.header {
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
}

.header h1 {
    font-size: 18px;
    font-weight: 700;
}

.header-right {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 13px;
    color: var(--text-secondary);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
}
.status-dot.online { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); }
.status-dot.offline { background: var(--accent-red); }

.container {
    max-width: 1280px;
    margin: 0 auto;
    padding: 20px 24px;
}

.stat-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 20px;
}

.stat-card {
    background: var(--bg-card);
    border-radius: 10px;
    padding: 16px 20px;
    border-left: 3px solid transparent;
}

.stat-card.balance { border-color: var(--accent-green); }
.stat-card.positions { border-color: var(--accent-blue); }
.stat-card.pnl { border-color: var(--accent-orange); }
.stat-card.status { border-color: var(--accent-green); }

.stat-label {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--text-secondary);
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}

.stat-value {
    font-size: 24px;
    font-weight: 700;
}
.stat-value .unit {
    font-size: 13px;
    color: var(--text-secondary);
    font-weight: 400;
    margin-left: 4px;
}

.pnl-positive { color: var(--accent-green); }
.pnl-negative { color: var(--accent-red); }

.chart-row {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 14px;
    margin-bottom: 20px;
}

.chart-panel, .positions-panel {
    background: var(--bg-card);
    border-radius: 10px;
    padding: 16px 20px;
}

.panel-title {
    font-size: 12px;
    text-transform: uppercase;
    color: var(--text-secondary);
    letter-spacing: 0.5px;
    margin-bottom: 12px;
}

.chart-container {
    position: relative;
    height: 240px;
}

.positions-panel .position-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
}
.positions-panel .position-item:last-child { border-bottom: none; }
.position-symbol { font-weight: 600; }
.position-detail { font-size: 13px; color: var(--text-secondary); }

.empty-state {
    text-align: center;
    color: var(--text-secondary);
    padding: 48px 0;
    font-size: 14px;
}

.trades-panel {
    background: var(--bg-card);
    border-radius: 10px;
    padding: 16px 20px;
}

.trades-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.trades-table th {
    text-align: left;
    padding: 10px 12px;
    color: var(--text-secondary);
    font-weight: 500;
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.trades-table td {
    padding: 10px 12px;
    border-bottom: 1px solid rgba(42, 42, 74, 0.5);
}

.trades-table tr:hover { background: var(--bg-hover); }

.trade-buy { color: var(--accent-green); }
.trade-sell { color: var(--accent-red); }

.pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
    font-size: 13px;
}

.pagination button {
    background: var(--bg-hover);
    color: var(--text-primary);
    border: 1px solid var(--border);
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
}
.pagination button:hover { background: var(--border); }
.pagination button:disabled { opacity: 0.3; cursor: default; }
.pagination span { color: var(--text-secondary); }

.loading { opacity: 0.6; }

@media (max-width: 768px) {
    .stat-cards { grid-template-columns: repeat(2, 1fr); }
    .chart-row { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: 提交**

```bash
git add dashboard/static/style.css
git commit -m "feat: add dashboard dark theme CSS"
```

---

### Task 4: 创建前端 HTML 页面

**Files:**
- Create: `dashboard/static/index.html`

- [ ] **Step 1: 编写 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Bot Dashboard</title>
<link rel="stylesheet" href="/style.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>
<body>

<div class="header">
  <h1>🤖 Crypto Trading Bot</h1>
  <div class="header-right">
    <span><span class="status-dot" id="statusDot"></span><span id="statusText">检测中...</span></span>
    <span>更新于 <span id="updateTime">--</span></span>
  </div>
</div>

<div class="container">

  <div class="stat-cards">
    <div class="stat-card balance">
      <div class="stat-label">账户余额</div>
      <div class="stat-value" id="cardBalance">-- <span class="unit">USDT</span></div>
    </div>
    <div class="stat-card positions">
      <div class="stat-label">当前持仓</div>
      <div class="stat-value" id="cardPositions">-- <span class="unit">/ 2 max</span></div>
    </div>
    <div class="stat-card pnl">
      <div class="stat-label">今日盈亏</div>
      <div class="stat-value" id="cardPnl">--</div>
    </div>
    <div class="stat-card status">
      <div class="stat-label">运行模式</div>
      <div class="stat-value" id="cardMode">--</div>
    </div>
  </div>

  <div class="chart-row">
    <div class="chart-panel">
      <div class="panel-title">📈 净值曲线 (USDT)</div>
      <div class="chart-container">
        <canvas id="equityChart"></canvas>
      </div>
    </div>
    <div class="positions-panel">
      <div class="panel-title">💎 当前持仓</div>
      <div id="positionsList">
        <div class="empty-state">暂无持仓</div>
      </div>
    </div>
  </div>

  <div class="trades-panel">
    <div class="panel-title">📋 交易记录</div>
    <table class="trades-table">
      <thead>
        <tr>
          <th>时间</th><th>币种</th><th>方向</th>
          <th>入场价</th><th>出场价</th><th>数量</th>
          <th>盈亏</th><th>收益率</th><th>状态</th><th>原因</th>
        </tr>
      </thead>
      <tbody id="tradesBody">
        <tr><td colspan="10" class="empty-state">暂无交易记录</td></tr>
      </tbody>
    </table>
    <div class="pagination" id="pagination"></div>
  </div>

</div>

<script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 提交**

```bash
git add dashboard/static/index.html
git commit -m "feat: add dashboard HTML page"
```

---

### Task 5: 创建前端 JS 逻辑

**Files:**
- Create: `dashboard/static/app.js`

- [ ] **Step 1: 编写 app.js**

```javascript
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
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
        document.getElementById('cardBalance').innerHTML = `${fmt(usdt.total)} <span class="unit">USDT</span>`;
    }

    // Equity chart
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

    // Positions count
    const posData = await fetchAPI(API.positions);
    const posCount = posData ? posData.length : 0;
    document.getElementById('cardPositions').innerHTML = `${posCount} <span class="unit">/ 2 max</span>`;

    // Daily PnL
    if (data.today) {
        const pnl = data.today.pnl || 0;
        const pnlPct = data.today.pnl_pct || 0;
        const cls = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        document.getElementById('cardPnl').innerHTML = `<span class="${cls}">${fmtPct(pnlPct)}</span> <span class="unit">(${fmt(pnl)} USDT)</span>`;
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

    // Pagination
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
    document.getElementById('updateTime').textContent = new Date().toLocaleTimeString('zh-CN');
    await Promise.all([
        updateStatus(),
        updateBalances(),
        updateStats(),
        updatePositions(),
        updateTrades(currentTradePage),
    ]);
}

// Initial load
refresh();

// Auto refresh every 30 seconds
setInterval(refresh, 30000);
```

- [ ] **Step 2: 提交**

```bash
git add dashboard/static/app.js
git commit -m "feat: add dashboard JS with Chart.js and 30s auto-refresh"
```

---

### Task 6: 更新 docker-compose.yml 添加 dashboard 服务

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: 在 services 下添加 dashboard 服务**

Read the current docker-compose.yml and add `dashboard` service after the `bot` service.

```yaml
  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    container_name: crypto-dashboard
    restart: always
    ports:
      - "8080:8080"
    volumes:
      - bot_data:/app/data
    depends_on:
      - bot
```

最终 `docker-compose.yml`:

```yaml
services:
  bot:
    build: .
    container_name: crypto-bot
    restart: always
    environment:
      - OKX_API_KEY=${OKX_API_KEY}
      - OKX_SECRET=${OKX_SECRET}
      - OKX_PASSWORD=${OKX_PASSWORD}
      - TG_BOT_TOKEN=${TG_BOT_TOKEN}
      - TG_CHAT_ID=${TG_CHAT_ID}
      - PAPER_TRADING_ONLY=${PAPER_TRADING_ONLY:-true}
    volumes:
      - bot_data:/app/data
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    container_name: crypto-dashboard
    restart: always
    ports:
      - "8080:8080"
    volumes:
      - bot_data:/app/data
    depends_on:
      - bot

volumes:
  bot_data:
```

- [ ] **Step 2: 提交**

```bash
git add docker-compose.yml
git commit -m "feat: add dashboard service to docker-compose"
```

---

### Task 7: 部署并验证

- [ ] **Step 1: 推送代码到 GitHub**

```bash
git push origin master
```

- [ ] **Step 2: 服务器拉取代码**

```bash
ssh root@8.219.140.154 "cd /root/crypto-trading-bot && git pull"
```

- [ ] **Step 3: 重建并启动所有服务**

```bash
ssh root@8.219.140.154 "cd /root/crypto-trading-bot && docker compose up --build -d"
```

Expected: bot 和 dashboard 两个容器都启动成功。

- [ ] **Step 4: 验证 API 端点**

```bash
ssh root@8.219.140.154 "curl -s http://localhost:8080/api/status"
```
Expected: `{"running":true,"mode":"paper",...}`

```bash
ssh root@8.219.140.154 "curl -s http://localhost:8080/api/balances | head -c 200"
```
Expected: `{"latest":{"USDT":{"free":5000,...`

- [ ] **Step 5: 验证前端页面**

```bash
ssh root@8.219.140.154 "curl -s http://localhost:8080/ | head -5"
```
Expected: HTML 页面

- [ ] **Step 6: 检查容器日志**

```bash
ssh root@8.219.140.154 "cd /root/crypto-trading-bot && docker compose logs dashboard"
```

- [ ] **Step 7: 提醒开放阿里云安全组 8080 端口**

需要用户在阿里云控制台 → ECS → 安全组 → 入方向 → 添加规则：TCP 8080。
