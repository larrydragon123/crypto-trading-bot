# 加密货币全自动交易机器人 — 设计文档

## 概述

一个基于均值回归策略的加密货币自动交易机器人，运行在 OKX 交易所，交易 BTC/ETH 现货，目标跑赢持币被动收益。

## 约束条件

- **交易所**：OKX
- **交易品种**：BTC/USDT、ETH/USDT 现货
- **资金规模**：< $5,000
- **策略风格**：保守型均值回归
- **技术栈**：Python 3.11+，CCXT，Pandas + TA-Lib
- **部署**：Docker 容器化，云服务器 7×24 运行
- **风险**：无杠杆、无合约、仅现货

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    主调度器 (APScheduler)              │
│                   每分钟执行一次主循环                   │
└─────────────────────────────────────────────────────┘
         │              │              │
    ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
    │ 数据采集 │   │ 信号引擎 │   │ 风险管理 │
    │  Feed   │──▶│ Signals │──▶│  Risk   │
    └─────────┘   └─────────┘   └────┬────┘
                                     │
         ┌───────────────────────────┤
         │              │            │
    ┌────▼────┐   ┌────▼────┐   ┌───▼────┐
    │执行引擎  │   │  监控   │   │  存储   │
    │Execution│   │ Monitor │   │ Storage │
    └─────────┘   └─────────┘   └────────┘
```

### 模块职责

| 模块 | 职责 | 关键依赖 |
|------|------|---------|
| `data/feed.py` | OKX WebSocket 实时行情 + REST K线数据 | ccxt.pro |
| `data/storage.py` | SQLite 交易记录、信号日志、余额快照 | sqlite3 |
| `strategy/indicators.py` | BB(20,2)、RSI(14)、EMA(200)、ATR(14) 计算 | pandas, pandas-ta |
| `strategy/signals.py` | 入场/出场条件判断 | indicators |
| `risk/manager.py` | 仓位计算、止损触发、冷却检查、日亏损限额 | signals |
| `execution/base.py` | Broker 抽象基类（统一接口） | — |
| `execution/paper.py` | PaperBroker：模拟成交，真实行情 | base |
| `execution/live.py` | LiveBroker：真实 OKX API 下单 | base, ccxt |
| `notify/telegram.py` | Telegram Bot 实时推送 | python-telegram-bot |
| `backtest/engine.py` | 历史回测引擎 | pandas |

---

## 策略逻辑

### 主时间框架
- **主周期**：1h K线（信号生成）
- **趋势确认**：4h K线（EMA 200 趋势过滤）

### 入场条件（需同时满足）

1. **超卖确认**：价格 ≤ Bollinger 下轨(20,2) 且 RSI(14) < 35
2. **趋势过滤**：4h 收盘价 > EMA(200)，长期趋势向上
3. **成交量确认**：当前1h成交量 > 过去20根1h均量 × 1.2

### 出场条件（满足任一）

1. **止盈**：价格 ≥ Bollinger 中轨(SMA20) 且 RSI(14) > 55
2. **硬止损**：价格 ≤ 入场价 − 2×ATR(14)
3. **时间止损**：持仓 > 72小时未触发止盈

---

## 风控参数

| 参数 | 值 |
|------|-----|
| 单笔仓位 | 总资金 10%–20%（ATR 越大仓位越小） |
| 最大同时持仓 | 2 笔（BTC+ETH 各一或同币种不开重复仓） |
| 每日最大亏损 | 总资金 5%，触发后当日停止交易 |
| 连续止损冷却 | 连续 3 次止损 → 暂停 4 小时 |
| 最低 USDT 保留 | 始终 ≥ 30% 总资金 |
| 滑点保护 | > 0.3% 不成交 |
| 极端行情熔断 | 1h 涨跌 > 10% → 暂停开仓，仅检查止损 |

---

## 双模式设计

### 模拟模式 (Paper Trading)

- 使用真实 OKX WebSocket 行情数据
- 订单在本地模拟成交（市价 + 0.1% 滑点）
- 按 OKX 真实费率扣除手续费（Maker 0.08% / Taker 0.10%）
- 虚拟余额和持仓存储在独立 SQLite 表
- 日志和 Telegram 通知与实盘完全一致

### 实盘模式 (Live Trading)

- 通过 CCXT 调用 OKX API 真实下单
- 限价单优先（吃 Maker 费率）
- 双重安全确认：`config.yaml` 设置 `mode: live` + 环境变量 `PAPER_TRADING_ONLY=false`

### 切换方式

```yaml
# config.yaml
mode: paper  # paper | live
```

### 上线流程

1. **阶段1**：模拟交易 ≥ 2 周，验证信号频率/胜率/最大回撤与回测一致
2. **阶段2**：实盘小资金（$100-200），验证滑点/成交速度/API稳定性
3. **阶段3**：逐步加仓至目标资金比例

---

## 项目结构

```
crypto_bot/
├── config.yaml          # 策略参数、API密钥路径、风控参数
├── main.py              # 入口：启动调度器、初始化各模块
├── data/
│   ├── feed.py          # OKX WebSocket + REST 数据源
│   └── storage.py       # SQLite CRUD 操作
├── strategy/
│   ├── indicators.py    # BB, RSI, EMA, ATR 计算
│   └── signals.py       # 入场/出场条件判断
├── risk/
│   └── manager.py       # 仓位计算、止损、冷却检查
├── execution/
│   ├── base.py          # Broker 抽象基类
│   ├── paper.py         # 模拟交易 Broker
│   └── live.py          # 实盘交易 Broker
├── notify/
│   └── telegram.py      # Telegram Bot 消息推送
├── backtest/
│   └── engine.py        # 历史回测引擎
├── Dockerfile
└── requirements.txt
```

---

## 异常处理

| 场景 | 处理 |
|------|------|
| OKX API 断连 | 指数退避重试（5s→10s→20s→60s上限），3次失败后 Telegram 告警 |
| 订单被拒 | 记录错误原因，余额不足跳过本轮，其余重试 1 次 |
| WebSocket 断线 | 自动重连，降级为 REST 轮询（30s间隔） |
| 交易所维护 | 检测到维护公告后暂停交易，Telegram 通知，维护后自动恢复 |
| 程序崩溃 | Docker `--restart=always`，启动时从 SQLite 恢复持仓状态 |
| 极端行情熔断 | 1h 涨跌 > 10% 暂停开仓，仅检查止损出场 |

---

## 部署

- **服务器**：云服务商 1核2G 轻量服务器
- **容器化**：Dockerfile + `docker run --restart=always`
- **密钥安全**：API Key/Secret 通过环境变量注入，不入配置文件
- **监控**：Telegram Bot 实时推送 + 每日 PnL/胜率/夏普比率汇总
