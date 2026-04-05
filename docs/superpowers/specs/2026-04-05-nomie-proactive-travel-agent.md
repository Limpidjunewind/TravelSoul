# Nomie — Proactive AI Travel Concierge Spec

**版本**：OpenClaw Hackathon Pivot
**日期**：2026-04-05
**核心概念**：Your AI travel concierge that knows your schedule and hunts deals silently

---

## 1. 产品定位

Nomie 从"**用户主动聊天的旅行规划工具**"转型为"**24/7 自主运行的主动式数字旅行管家**"。

**一句话 pitch**：
> Nomie watches your calendar, silently searches flights and hotels when you have free time, and only reaches out when it finds something worth your attention.

**关键差异**（对比市面产品如 iMean AI）：

| | 传统旅行 AI（iMean 等） | Nomie（本项目） |
|---|------------------------|----------------|
| 触发方式 | 用户主动提问 | Agent 后台自主运行 |
| 日程感知 | ❌ | ✅ 读取 Google Calendar |
| 打扰频率 | 每次提问都回复 | 只在发现机会时推送 |
| 交互界面 | 单一 Web 聊天 | Web（设置+详情） + Telegram（推送） |
| 产品形态 | 在线工具 | Digital Employee |

---

## 2. 核心架构

```
┌──────────────────────────────────────────────────────┐
│  Web 前端（独立 spec，不在本文档范围）                  │
│  - Onboarding（收集偏好 + Google Calendar OAuth）     │
│  - /proposals/:uuid 详情展示                         │
│  - Confirm / Reject 操作                             │
│  - Settings（编辑偏好、阈值等）                        │
└──────────────────────────────────────────────────────┘
                       ↓ 写入 preferences
┌──────────────────────────────────────────────────────┐
│  Nomie Backend（复用 IT5007 项目的基础）              │
│  Lead Agent + 4 Sub-agents + Agnes Claw Model        │
│  + Duffel API (flights) + LiteAPI (hotels, backup)   │
│         ↑                                            │
│  作为"旅行规划引擎"被调度器调用                        │
└──────────────────────────────────────────────────────┘
      ↑                           ↓
      │                           │
┌────────────────────┐  ┌─────────────────────────┐
│  定时扫描器（新）    │  │  Telegram Bot（新）       │
│  - 每天 1 次        │  │  - 仅推送通知             │
│  - 读 Calendar      │  │  - 不做 onboarding        │
│  - 发现空档+生成计划 │  │  - 不做命令/查看          │
└────────────────────┘  └─────────────────────────┘
                                    ↓ 用户点链接
                             回到 Web 前端
                                    ↓ Confirm
                        ┌─────────────────────────┐
                        │  Google Calendar         │
                        │  （写入最小信息的 event）  │
                        └─────────────────────────┘
```

**三个 surface 各司其职**：
- **Web 前端** = 重交互（onboarding、详情展示、settings、confirm/reject）—— 独立 spec
- **后台扫描** = 自主思考的"大脑"
- **Telegram bot** = **纯推送通道**，不做任何对话交互

---

## 3. 数据模型

### 3.1 user_preferences 表

```sql
CREATE TABLE user_preferences (
  telegram_user_id     TEXT PRIMARY KEY,
  origin_city          TEXT,          -- e.g. "Singapore"
  destinations         JSON,          -- ["Japan", "Korea", "Southeast Asia"]
  vague_preferences    TEXT,          -- e.g. "喜欢看海、自然风光、想放松"
  budget_per_person    INTEGER,       -- in SGD
  travelers            INTEGER,       -- default 1
  min_gap_days         INTEGER,       -- default 5
  price_drop_threshold INTEGER,       -- default 20 (percent)
  google_tokens        JSON,          -- OAuth access_token, refresh_token
  created_at           TIMESTAMP,
  updated_at           TIMESTAMP
);
```

**字段说明**：
- `destinations`：可以是国家/地区级（"Japan"）或城市级（"Tokyo"），两者都允许
- `vague_preferences`：自由文本，用户对旅行的模糊需求（风景偏好、心情、活动类型）
- `google_tokens`：OAuth 授权后的 token，用于后续读取 calendar

### 3.2 proposals 表

```sql
CREATE TABLE proposals (
  proposal_id         TEXT PRIMARY KEY,    -- UUID
  telegram_user_id    TEXT NOT NULL,
  slot_start_date     DATE NOT NULL,
  slot_end_date       DATE NOT NULL,
  status              TEXT NOT NULL,       -- 'pending' | 'confirmed' | 'rejected'
  bundle_data         JSON NOT NULL,       -- 多目的地的完整数据，见 3.3
  confirmed_option    TEXT,                -- 如果 confirmed，选的哪个目的地
  baseline_price      INTEGER,             -- confirmed 时的 snapshot 价格
  last_price          INTEGER,             -- 最近一次扫描的价格
  calendar_event_id   TEXT,                -- 写入 Google Calendar 后的 event id
  created_at          TIMESTAMP,
  updated_at          TIMESTAMP,
  FOREIGN KEY (telegram_user_id) REFERENCES user_preferences(telegram_user_id)
);
```

### 3.3 bundle_data JSON 结构

```json
{
  "destinations": [
    {
      "name": "Tokyo, Japan",
      "reasoning": "樱花季末期，价格相对便宜，符合用户 relaxing 偏好",
      "flights": [
        {"airline": "SQ", "flight_no": "SQ12", "price": 850, "link": "..."}
      ],
      "hotels": [
        {"name": "Shinjuku Granbell", "price_per_night": 120, "rating": 8.5, "link": "..."}
      ],
      "itinerary": [
        {"day": 1, "plan": "Senso-ji, Asakusa, Ueno"}
      ],
      "tips": ["Visa-free for SG passport", "JR Pass recommended"],
      "total_price": 1870
    },
    {
      "name": "Busan, Korea",
      "reasoning": "海边城市，符合用户喜欢看海的需求",
      "flights": [...],
      ...
    }
  ]
}
```

---

## 4. Onboarding 流程

**Onboarding 完全由 Web 前端负责**，本 spec 不涵盖。详见 Web 前端 spec。

Web 前端负责：
- 收集所有用户偏好并写入 `user_preferences` 表
- 让用户把自己的 Telegram 账号跟该偏好记录关联（具体方式由 Web spec 定义）

**Google Calendar OAuth 不由 Web 前端完成**（见 §9），而是由本地一次性脚本产出 tokens 并写入 `user_preferences.google_tokens`。Web 前端上**没有** "Connect Google Calendar" 按钮。

**本 spec 的假设前提**：`user_preferences` 表里已经有有效的用户记录（包含 `telegram_user_id`、`google_tokens` 和所有偏好字段）。后台扫描器和 Telegram bot 都是基于这个前提运行。

---

## 5. 定时扫描逻辑（每天 1 次）

### 扫描流程

```
for each user in user_preferences:
  1. 用 google_tokens 读取该用户未来 1-2 个月的 calendar events
  2. 计算空档（consecutive free days ≥ min_gap_days）
  3. for each 空档:
     a. 检查 proposals 表：这个空档是否已有 pending/rejected 状态的 proposal？
        - 如果有 rejected: 跳过（永久拒绝）
        - 如果有 pending: 只更新价格，不生成新的
        - 如果没有: 继续 b
     b. 调用 Nomie Lead Agent:
        - input: 用户偏好 + 空档日期 + 模糊需求
        - Lead Agent 基于 destinations + vague_preferences + 季节等推理，决定具体搜哪些城市
        - 派发 4 个 sub-agents（flight-search / hotel-search / itinerary-planner / travel-tips）
        - Sub-agents 调用 Duffel / LiteAPI / web_search / web_fetch
     c. 打包成 bundle_data，插入 proposals 表（status=pending）
     d. 生成 Web 前端链接：https://nomie.app/proposals/{proposal_id}
     e. Telegram 发一条通知（只发这一次）

  4. for each confirmed proposal of this user:
     a. 用 Duffel 重新 quote 原来的航班/酒店
     b. 计算新价格 vs baseline_price 的下跌幅度
     c. 如果下跌 ≥ price_drop_threshold:
        - 发 Telegram 通知
        - 重置 baseline_price = 新价格（避免同一次降价重复通知）
     d. 更新 last_price
```

### 什么情况不扫描/不生成？
- 用户 google_tokens 失效（需要重新授权）
- 空档已有 rejected proposal
- 空档在过去（出发日期 < 今天）

### Demo 时的扫描触发
- 真定时调度可选（APScheduler）
- 或者通过一个内部命令 `/admin/scan` 手动触发（只给演示用）
- 具体实现时再定

---

## 6. Proposal 状态机

```
               生成
  (空档发现) ────────→ pending
                        │
              用户 reject │   用户 confirm
                        │         │
                        ↓         ↓
                    rejected   confirmed
                    (永久)      │
                                │ 每天追踪价格
                                │
                                │ 价格大跌
                                ↓
                            confirmed + 通知
                            (baseline 重置)
```

**状态转换规则**：
- `pending → rejected`：用户在 web 前端点 Reject，永久拒绝，同空档不再生成
- `pending → confirmed`：用户在 web 前端点 Confirm 并选择一个目的地选项，系统写入 Google Calendar
- `confirmed → confirmed`：价格追踪，不改变状态，只更新 `baseline_price` 和 `last_price`
- `rejected → *`：rejected 是终态，不再变化
- `confirmed → *`：confirmed 后不会回退（即使日历冲突也不回退，用户自己处理）

---

## 7. 通知规则

**核心原则**：**静默优先，只在真正有价值时才打扰用户**

| 场景 | Telegram 通知？ |
|------|---------------|
| ① 新空档发现 + 生成新 proposal（pending） | ✅ 必通知（核心功能） |
| ② pending proposal 价格小幅波动 | ❌ 静默 |
| ③ pending proposal 价格大跌 | ❌ 静默（用户还没 commit） |
| ④ pending proposal 对应空档被新会议占用 | ❌ 静默（用户自己知道） |
| ⑤ confirmed trip 价格大跌 ≥ 阈值 | ✅ 通知 + 重置 baseline |
| ⑥ confirmed trip 价格上涨 | ❌ 静默（不 actionable） |
| ⑦ confirmed trip 日历冲突 | ❌ 静默（用户自己负责） |
| ⑧ 例行扫描无变化 | ❌ 静默 |

---

## 8. Telegram Bot 设计

### 定位
**纯推送通道**。Bot 不做 onboarding、不支持查看命令、不跟用户对话。

### 不做的事
- ❌ Onboarding 对话（由 Web 前端负责）
- ❌ `/proposals`、`/trips`、`/preferences` 等查看命令
- ❌ 响应用户的自由文本消息（或只回一句"Please use the web app"）

### 做的事
- ✅ 收到后台扫描器的指令后，给指定的 `telegram_user_id` 推送消息
- ✅ 推送"新 proposal 生成"通知
- ✅ 推送"confirmed trip 大幅降价"通知

### Bot 初始化
- 通过 BotFather 创建 bot 拿到 bot token
- Bot token 存入 `.env`
- 用户在 Web 前端 onboarding 时，需要提供自己的 Telegram username 或 user_id，存入 `user_preferences.telegram_user_id`
- Bot 推送消息时根据 `telegram_user_id` 发送

### 推送消息形态

**核心原则：Telegram 消息极简，只负责"叮咚一声 + 链接"，所有细节在 Web 前端呈现。**

不显示目的地名字、不显示机票/酒店信息、不显示数量提示。用户想看就点链接跳 Web，在 Web 前端从 `proposals.bundle_data` 读取完整的多目的地方案（A/B/C/D/E）并自己选。

**① 新 proposal 通知**
```
🎉 Hey Jamie! I've planned a trip for you.

📅 Apr 20 – Apr 27 (7 days)

👉 View details: {LINK}
```

**② Confirmed trip 降价通知**（仅对已 confirm 并已写入 Google Calendar 的行程）
```
💰 Good news! Your trip (Apr 20 – Apr 27) just dropped 20%+

👉 View update: {LINK}
```

- 不写具体价格数字，只说 "dropped X%+"，X = `user_preferences.price_drop_threshold`（默认 20）
- Pending proposal **不发**降价通知（§7 规则 ③）

`{LINK}` 在实现时用 `PROPOSAL_URL_BASE` 环境变量拼接，比如 `{PROPOSAL_URL_BASE}/proposals/{uuid}`。等 Web 前端部署地址确定后改这一个 env 即可。

---

## 9. Google Calendar 集成

### OAuth 流程
OAuth 授权由**本地一次性脚本**完成，**Web 前端完全不碰 OAuth**。

流程：
1. 开发者（Jamie）在 Google Cloud Console 建 OAuth 2.0 client（Desktop app 类型），下载 `client_secret.json`
2. 本地跑 `scripts/google_oauth_setup.py`，脚本启动一个本地 HTTP server + 打开浏览器 → 用户在浏览器里授权 → 脚本拿到 access_token + refresh_token
3. 脚本把 tokens 直接写入目标 `user_preferences` 记录的 `google_tokens` 字段

这个脚本是一次性工具，demo 前跑一次就够，不进 runtime 主流程。

后台扫描器（runtime）只负责从 DB 读 tokens 使用，并在 access_token 过期时用 refresh_token 刷新、写回 DB。

**为什么不做 Web OAuth**：demo 只有 1 个演示用户（Jamie 自己），Web OAuth 的 callback 路由 / HTTPS / redirect URI 对齐等工作量不划算。Pitch 时口头说 "in production this is embedded in the Web signup flow" 即可。

### Scopes
- `https://www.googleapis.com/auth/calendar.readonly` — 读取 calendar 找空档
- `https://www.googleapis.com/auth/calendar.events` — 写入 confirmed trip 的 event

### Demo 环境
- 本地跑 OAuth，redirect URI 用 `http://localhost:8080/oauth/google/callback`
- Google Cloud Console 建一个 OAuth client，测试用户列表里加自己的 Gmail
- 不需要 Google 审核（测试模式下最多 100 个测试用户）

### 读取 Calendar
- 每天扫描时，拉取未来 60 天的 events
- 用 events.list API：`timeMin=now, timeMax=now+60d, singleEvents=true, orderBy=startTime`
- 计算连续 free days（两个 event 之间的空隙）

### 写入 Calendar（Confirm 后）
```
事件标题：🏝 Jeju Trip（或根据目的地）
事件时间：按日期（例如 4/1 00:00 - 4/10 23:59），all-day event
事件位置：Jeju, Korea
事件描述：最小信息，例如 "Nomie planned trip"
```

**不在 event 里放：**
- 机票细节
- 酒店细节
- Web 前端链接（隐私：同事能看到 calendar）

**理由**：用户的 calendar 可能被同事看到，敏感信息放在 Telegram 和 web 前端即可。用户一旦 confirm 就代表已决定，之后不需要再回看细节。

---

## 10. 价格追踪（Confirmed Trips）

### Baseline 机制
- 用户 confirm 的那一刻，snapshot 当前选中选项的总价格（flight + hotel），存入 `baseline_price`
- 之后每天扫描，通过 Duffel 重新 quote 同一个航班 + 同一个酒店的当前价格
- 计算下跌百分比：`(baseline - new) / baseline * 100`
- 如果下跌 ≥ `price_drop_threshold`（默认 20%）：
  - 发 Telegram 通知："Your Tokyo trip dropped by 22%! New price: SGD 1,450"
  - **重置 baseline_price = 新价格**（防止重复通知同一次降价）

### 涨价处理
- 涨价不通知（不 actionable，骚扰用户）
- 但仍更新 `last_price` 字段（web 前端显示当前价格）

### 航班/酒店不可用
- 如果 Duffel 返回原航班已售完或酒店已订满
- 更新 proposal 状态为"stale"？还是直接通知用户？
- **Demo 先不处理这个边界情况，生产再考虑**

---

## 11. 技术栈

| 层 | 技术 | 状态 |
|---|------|------|
| LLM | Agnes Claw Model (via ZenMux) | ✅ 已配置 |
| Agent Framework | LangGraph + DeerFlow base | ✅ 已有 |
| Flight API | Duffel | ✅ Token 已拿到 |
| Hotel API | LiteAPI (sandbox) | ✅ Token 已拿到 |
| Affiliate backup | Travelpayouts | ✅ Token 已拿到 |
| Web search | Tavily | ✅ 已有 |
| Web fetch | Jina AI | ✅ 已有 |
| Weather | Open-Meteo | ✅ 无需 key |
| Telegram bot | python-telegram-bot | ⏳ 待集成 |
| Scheduler | APScheduler | ⏳ 待集成 |
| Calendar | Google Calendar API + OAuth | ⏳ 待集成 |
| 数据存储 | SQLite（新增 user_preferences + proposals 表） | ⏳ 待集成 |

---

## 12. Demo 设置

### 演示账号
- **Telegram**：Jamie 的个人账号（user_id 提前存进 user_preferences）
- **Google Calendar**：Jamie 的个人日历，提前填一些真实日程 + 故意留一个 7 天空档
- **preferences**：通过 Web 前端 onboarding 预先填好（新加坡出发、想去日本/韩国、预算 5000 SGD、喜欢看海...）

### Demo 流程
1. 展示 Web 前端已完成的 onboarding（或快速过一遍）
2. 展示当前 calendar（有明显的空档）
3. 触发扫描（/admin/scan 或手动按钮）
4. 等待 agent 工作（30 秒~1 分钟）
5. Telegram 弹出通知
6. 点击通知里的链接，跳到 web 前端
7. Web 前端展示 proposal bundle（多目的地选项）
8. 选一个，点 Confirm
9. 切回 Google Calendar 展示新增的 event
10. （可选）再次触发扫描，模拟"价格下跌"，展示降价通知

### Pitch 5 分钟结构
- **0:00-0:30** 痛点：用户每次要规划旅行都要花大量时间搜比价
- **0:30-3:30** Live demo（上面的 1-9 步）
- **3:30-4:00** 技术架构：Agnes + Multi-agent + Duffel + Calendar + Telegram
- **4:00-4:30** 差异化：对比 iMean 等被动工具，Nomie 是主动的
- **4:30-5:00** Future work & Q&A

---

## 13. 范围界定（这个 spec 不包含）

- **Web 前端具体实现** —— 另起 spec 文档
- **具体代码实现** —— 不在 spec 层面，实施时写 plan
- **Production-ready 的安全性** —— Demo UUID 做访问凭证就够了，正式部署另议
- **多用户 scale** —— Demo 只支持 1-2 个用户
- **错误重试机制** —— 简化处理
- **国际化/多语言** —— Telegram bot 和通知默认英文

---

## 14. 待决策 / 开放问题

这些问题 spec 阶段没有定死，实施时再决定：

1. **Demo 时扫描是真定时还是手动触发？** —— 两种都做，手动触发作为 demo safety net
2. **Duffel 搜不到的目的地怎么办？** —— 测试时再看，可能 fallback 到 Tavily
3. **Multiple destinations 的智能推理**，Lead Agent 怎么决定搜哪几个城市？—— 用 prompt engineering 调，先做简单版（直接把用户的 destinations + vague_preferences 丢给 LLM 推理）
4. **Telegram inline buttons 的跳转处理** —— 是直接跳 web 前端 URL，还是通过 bot 的 callback 再跳转？取决于实现便利性

---

## Appendix A: 现有代码资产（从 IT5007 项目继承）

- `backend/src/agents/lead_agent/` — Lead Agent（已定制为 Nomie 旅行规划身份）
- `backend/src/subagents/builtins/` — 4 个 travel sub-agents（flight-search / hotel-search / itinerary-planner / travel-tips）
- `backend/config.yaml` — 已配置为 Agnes Claw Model
- `backend/src/tools/` — tools 框架，可以扩展加 Duffel、LiteAPI、Open-Meteo 等新 tool

## Appendix B: Sub-Agent Tool 增强

Nomie 本身的检索质量不强化，但**把真实的 travel API 封装成 LangChain tools 挂到现有 sub-agent 上**，让它们从"Tavily web 搜索"升级为"GDS 级真实数据"。

| Sub-agent | 现有 tools | 新挂 tools |
|-----------|-----------|-----------|
| `flight-search` | web_search, web_fetch | **`duffel_tool`**（查航班、返回真实 offer） |
| `hotel-search` | web_search, web_fetch | **`liteapi_tool`**（查酒店 sandbox 数据） |
| `itinerary-planner` | web_search, web_fetch | （保持不变，用搜索 + LLM 推理） |
| `travel-tips` | web_search, web_fetch | （保持不变，可选加 `open_meteo_tool` 查天气） |

**Tool 挂载方式**：在对应 sub-agent 的定义文件里（`backend/src/subagents/builtins/flight_search.py` 等），把新 tool 加进 tools 列表。Sub-agent 的 system prompt 里提一句"Prefer duffel_tool for flight queries, fallback to web_search if duffel fails"，让 LLM 自己学会优先调用。

**为什么做这个**：纯 web_search 返回的航班/酒店数据质量参差且经常过时，接上 Duffel/LiteAPI 之后 Nomie 输出的 `bundle_data` 里是真实可订航班，pitch 时 demo 效果天差地别。

## Appendix C: 新增代码位置建议

- `backend/src/pipeline/` — 主流程（scan_and_notify + telegram_sender 都放这里）
- `backend/src/calendar_svc/` — Google Calendar API 封装（`calendar` 是 Python 标准库名，避免冲突）
- `backend/src/db/` — SQLite 数据访问层
- `backend/src/tools/builtins/duffel_tool.py` — Duffel 封装为 LangChain tool
- `backend/src/tools/builtins/liteapi_tool.py` — LiteAPI 封装
- `scripts/google_oauth_setup.py` — 一次性 OAuth 脚本（不在 src 下，因为不是 runtime 代码）
- `scripts/trigger_scan.py` — demo 用的手动触发入口
