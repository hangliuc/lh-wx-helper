# 📈 LH Finance-Sentinel

> 个人金融风控与盯盘助手 · SRE 级高可用版

一个轻量级的个人金融监控机器人。它消除盘中噪音，每日定点把"大盘指数 + 我的持仓"汇总成一张飞书互动卡片推送到你的手机；同时 7×24 盯紧国际现货黄金，触发关键风控阈值时第一时间报警。所有逻辑围绕一个理念展开：**只在需要做决策时打扰你**。

---

## ✨ 核心特性

- **📊 收盘日报卡片**：顶部三连指标（上证 / 中证A500 / 纳斯达克100），下方持仓列表按当日涨跌幅由大到小排序，红涨绿跌一眼可读。
- **🚨 黄金智能风控**：基于"非对称网格"策略，伦敦金日内波动每跨过 ±1.0% 触发一次报警，自动累计已报警档位避免重复打扰。
- **🧠 断电记忆**：黄金基准价持久化到本地 `data/gold_state.json`，容器重启或重新部署都不会丢锚点。
- **😴 节假日防骚扰**：内置 `chinesecalendar`，按 A 股真实日历过滤法定节假日、周末调休。
- **🎨 飞书原生卡片**：使用 `column_set` Grid 布局做出对齐严谨的金融数据看板，告别杂乱无章的纯文本。
- **🔔 双 Webhook 隔离**：日报和黄金报警走两个独立机器人，互不干扰。

---

## 🧱 项目结构

```
lh-finance-sentinel/
├── main.py                       # 入口：装配 Notifier + Task，注册定时调度
├── app/
│   ├── core/
│   │   └── notifier.py           # 飞书互动卡片推送 (含指数退避重试)
│   └── tasks/
│       ├── daily_reporter.py     # 收盘日报任务
│       └── gold_watcher.py       # 黄金 5 分钟轮询 + 网格风控
├── config/
│   └── config.yaml               # Webhook、指数、持仓、调度时刻
├── strategy/                     # 个人投资手册 (Markdown 笔记)
├── Dockerfile
├── requirements.txt
└── .github/workflows/deploy.yml  # GitHub Actions → SSH 部署
```

---

## 📡 数据来源

为了对抗云服务器 IP 封锁、保证可用性，数据源经过精挑：

| 模块 | 数据源 | 接口 |
| :--- | :--- | :--- |
| **A股 / ETF / 宽基指数** | 腾讯财经 | `qt.gtimg.cn/q=` |
| **国际现货黄金 (XAU/USD)** | Swissquote (瑞讯银行) | `forex-data-feed.swissquote.com` |
| **离岸人民币汇率 (USD/CNH)** | Swissquote (瑞讯银行) | 同上 |
| **交易日历** | `chinesecalendar` | 本地离线库 |

腾讯接口是国内延迟最低的公共行情之一；瑞讯对海外/云节点极其友好，没有反爬限制，毫秒级响应。

---

## ⏰ 调度策略

- **日报**：默认在 `12:00 / 14:30 / 16:00` 各推一次，时间点可在 `config.yaml` 的 `schedules.times` 中自由增删。
- **黄金**：每 `gold_monitor_interval` 分钟轮询一次（默认 5 分钟）。
- **启动自检**：进程启动时会立即各跑一次任务，确保配置和网络都是通的，再进入守候模式。

---

## 💡 常见问题：为什么计算出的"国内金价"和京东金融/支付宝不一样？

工具推送的 **国内折合价 (元/克)** 采用国际标准换算：

```
au9999 ≈ XAU(USD/oz) ÷ 31.1035 × USD/CNH
```

它和国内 App 显示的绝对价格通常会有差异，原因如下：

1. **在岸 (CNY) vs 离岸 (CNH) 汇率差**：国内软件用受央行指导的 CNY，本工具用国际自由市场的 CNH，两者有几十个基点的正常价差，极端行情下会拉大。
2. **中间价 vs 挂牌价**：瑞讯给的是国际外汇市场的实时中间价，国内平台显示的是已经包含点差的报价。
3. **核心：上海溢价 (Shanghai Premium)**：国内黄金进口配额受限，AU9999 长期比国际金价贵 1~3 元/克，极端时甚至超过 10 元。本工具算的是"无水分的纯理论折合价"。

> **风控视角**：盯盘看的是波动率（百分比）而不是绝对价格。理论折合价能更干净地反映趋势，还能顺便判断当前国内金价是否存在高溢价泡沫。

---

## 🚀 部署与使用

### 1. 配置 `config/config.yaml`

```yaml
notification:
  webhook:
    url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"      # 日报机器人
  gold_webhook:
    url: "https://open.feishu.cn/open-apis/bot/v2/hook/yyy"      # 黄金报警机器人

schedules:
  times: ["12:00", "14:30", "16:00"]

gold_monitor_interval: 5

# 顶部大盘指数 (固定顺序，不参与排序)
indices:
  - { name: "上证指数",    symbol_ref: "sh000001", flag: "🇨🇳" }
  - { name: "中证A500",    symbol_ref: "sh000510", flag: "🇨🇳" }
  - { name: "纳斯达克100", symbol_ref: "usNDX",    flag: "🇺🇸" }

# 我的持仓 (按当日涨跌幅由大到小排序后展示)
holdings:
  - { name: "南方中证A500ETF",  symbol_ref: "sz159352" }
  - { name: "天弘恒生科技",      symbol_ref: "sh520920" }
  - { name: "黄金ETF",          symbol_ref: "sh518880" }
  # ... 自由扩展
```

`symbol_ref` 沿用腾讯财经规则：A 股 `sh`/`sz` + 6 位代码，美股 `us` + 代码。

### 2. 本地运行（开发调试）

```bash
pip install -r requirements.txt
python main.py
```

### 3. Docker 部署

```bash
docker build -t lh-finance-sentinel:latest .

docker run -d \
  --name lh-finance-sentinel \
  --restart always \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  -e TZ=Asia/Shanghai \
  lh-finance-sentinel:latest
```

挂载 `config/` 让 Webhook 和持仓改动免重建；挂载 `data/` 让黄金基准价跨重启持久化。

### 4. CI/CD：GitHub Actions 一键部署

仓库已内置 `.github/workflows/deploy.yml`，`push` 到 `master` 后自动：

1. 通过 `ssh-deploy` 把代码 rsync 到服务器（保留 `data/`）
2. 在服务器上 `docker build` 新镜像
3. 停掉旧容器并启动新容器

需要在仓库 Secrets 配置 `SSH_PRIVATE_KEY` / `SERVER_HOST` / `SERVER_USER`。

---

## 📦 依赖

| 包 | 作用 |
| :--- | :--- |
| `requests` | 行情接口调用 |
| `schedule` | 进程内定时调度 |
| `PyYAML` | 配置解析 |
| `chinesecalendar` | 中国法定节假日判定 |

---

## 🛡️ 设计哲学

- **高信噪比 > 全量推送**：宁可一天不打扰，也不发"还在区间内震荡"这种废话。
- **依赖注入 + 单一职责**：`main.py` 只负责装配，`Notifier` 只管推送，`Task` 只管业务逻辑，互不耦合。
- **失败可恢复**：网络异常和飞书限流走指数退避重试；状态用 JSON 落盘，容器随时可挂。
- **数据自洽**：日报红涨绿跌、黄金卡片整张红/绿，颜色语言和金融语义保持一致。

> 💡 风控纪律：优质资产越跌越买，做时间的朋友。
