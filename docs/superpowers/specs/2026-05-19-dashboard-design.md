# Dashboard 可视化面板设计

## 目标

为加密货币交易机器人提供一个 Web 可视化面板，用户可通过浏览器查看：运行状态、账户余额变化、净值曲线、交易记录、每日统计。

## 架构

```
docker-compose.yml
├── bot (已有)        — 交易机器人，写 trading.db
└── dashboard (新增)   — FastAPI + 静态页面，读 trading.db
         ↓
    bot_data (Docker volume)
         ↓
    /app/data/trading.db (SQLite, 两个容器共享)
```

- 独立 FastAPI 容器（不嵌入 bot 进程）
- 通过 Docker volume `bot_data` 共享数据库
- 仪表盘只读取数据，不写入（只读监控面板）
- 前端每 30 秒轮询 API

## 技术选型

| 层 | 选型 | 原因 |
|---|---|---|
| 后端 | FastAPI + uvicorn | 轻量、异步、Python 生态一致 |
| 数据库访问 | 直接读 SQLite | 与 bot 共享 volume，无需额外配置 |
| 图表 | Chart.js (CDN) | 轻量、无需 npm、适合曲线图 |
| 前端 | 单 HTML + Vanilla JS | 无框架依赖，体积小，加载快 |
| 样式 | 纯 CSS 暗色主题 | 类似 TradingView 风格 |

## API 端点

| 端点 | 返回 |
|---|---|
| `GET /api/status` | `{mode, running, start_time, loop_count, last_loop_time}` |
| `GET /api/balances` | `{latest: {USDT, BTC, ETH}, history: [{time, USDT}...]}` |
| `GET /api/trades?page=1&size=20` | `{trades: [...], total, page, size}` |
| `GET /api/stats` | `{today: {pnl, pnl_pct, trades, wins, losses}, all: {...}}` |
| `GET /api/positions` | `[{symbol, entry_price, qty, pnl_pct, entry_time}...]` |

状态判断逻辑：最近一个 balance 记录的时间戳距现在 < 90 秒 → "运行中"，否则 → "可能停止"。

## 前端页面

```
┌─────────────────────────────────────────────────┐
│ 🤖 Crypto Trading Bot    🟢 运行中  13:20:45    │  ← 顶部栏
├──────────┬──────────┬──────────┬────────────────┤
│ 账户余额  │ 当前持仓  │ 今日盈亏  │ 运行状态        │  ← 四张指标卡
│ 5000.00  │ 0 / 2   │ +0.00    │ 🟢 正常        │
├────────────────────┬─────────────────────────────┤
│ 📈 净值曲线 (Chart) │ 💎 持仓明细                  │  ← 图表 + 持仓
├────────────────────┴─────────────────────────────┤
│ 📋 交易记录表（分页）                               │  ← 交易列表
│ 时间 | 币种 | 方向 | 价格 | 数量 | 盈亏 | 原因     │
└─────────────────────────────────────────────────┘
```

## 文件结构

```
dashboard/
├── Dockerfile              # FROM python:3.11-slim
├── requirements.txt        # fastapi, uvicorn, pandas
├── main.py                 # FastAPI app + endpoints
└── static/
    ├── index.html          # 单页仪表盘
    ├── app.js              # API 轮询 + Chart.js 绑定
    └── style.css           # 暗色主题样式
```

## 部署改动

1. `docker-compose.yml` 新增 `dashboard` 服务，端口 `8080:8080`
2. 共用 `bot_data` volume
3. `Dockerfile` 在项目根目录新增 `dashboard/` 的构建
4. 阿里云安全组需要开放 8080 端口（TCP）

## 非目标

- 不含用户认证（仅建议内网/VPN 访问，或加 Cloudflare Tunnel）
- 不含交易操作（不下单、不改参数、不调资金）
- 不含 WebSocket 推送（30 秒轮询足够）
- 不含 Telegram 通知替代（通知仍由 bot 直接处理）
