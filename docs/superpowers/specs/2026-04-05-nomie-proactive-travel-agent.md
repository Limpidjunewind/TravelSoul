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
| 交互界面 | Web 聊天 | Telegram + Web（双 surface） |
| 产品形态 | 在线工具 | Digital Employee |

---

## 2. 核心架构

```
┌──────────────────────────────────────────────────────┐
│  Nomie Backend（复用 IT5007 项目的基础）              │
│  Lead Agent + 4 Sub-agents + Agnes Claw Model        │
│  + Duffel API (flights) + LiteAPI (hotels, backup)   │
│         ↑                                            │
│  作为"旅行规划引擎"被调度器调用                        │
└──────────────────────────────────────────────────────┘
      ↑                           ↑
      │                           │
┌────────────────────┐  ┌─────────────────────────┐
│  定时扫描器（新）    │  │  Telegram Bot（新）       │
│  - 每天 1 次        │  │  - Onboarding 对话        │
│  - 读 Calendar      │  │  - 主动推送通知           │
│  - 发现空档+生成计划 │  │  - 不做查看命令           │
└────────────────────┘  └─────────────────────────┘
                                    ↓ 用户点链接
                        ┌─────────────────────────┐
                        │  Web 前端（新，另起文档）  │
                        │  - /proposals/:uuid      │
                        │  - Confirm / Reject       │
                        └─────────────────────────┘
                                    ↓ Confirm
                        ┌─────────────────────────┐
                        │  Google Calendar         │
                        │  （写入最小信息的 event）  │
                        └─────────────────────────┘
```

**三个 surface 各司其职**：
- **后台扫描** = 自主思考的"大脑"
- **Telegram bot** = 轻量 onboarding + 通知
- **Web 前端** = 计划详情展示 + 最终确认（独立 spec 文档）

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

## 4. Onboarding 流程（Telegram 对话式）

用户第一次向 Bot 发送 `/start` 时触发。Bot 通过自然语言对话收集必要信息。

### 必须收集
1. **出发城市**："你从哪里出发？"
2. **想去的地方**："你想去哪些地方？可以是国家、地区或具体城市"
   - 如果用户说很模糊（如"东南亚"），bot 追问细化（"马来西亚、泰国、印尼都可以？"）
3. **预算**："预算大概多少（每人）？"
4. **同行人数**："几个人一起？"
5. **最小空档天数**："最少几天连续空档才帮你规划？"（默认 5）
6. **模糊旅行偏好**："喜欢什么样的旅行？自然风光？城市探索？放松？看海？"
7. **Google Calendar 授权**：Bot 生成一个 OAuth 链接，引导用户点击授权

### 不在 onboarding 收集（放到 web 前端的 settings）
- 酒店星级
- 航班偏好（直飞/转机、红眼航班）
- 价格下跌通知阈值（默认 20%）

### Onboarding 完成的标志
用户完成 Google Calendar 授权，token 存入数据库。Bot 回复："All set! I'll watch your calendar and reach out when I find something good for you. 🌏"

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
**轻量级工具**，只做 onboarding 和推送，不做查看/管理命令。

### 支持的 commands
- `/start` — 开始 onboarding（新用户）或重新开始对话（老用户）
- 其他命令**不做**（包括 /proposals, /trips, /preferences, /settings 等）

### 用户主动消息
- 如果用户在聊天里发自由文本，bot 视为 onboarding 的一部分或追问，LLM 理解后更新 preferences
- 不支持"查看已有 proposals"这类请求，bot 会回复"请到你的日历或 web 端查看"

### 推送消息形态
**优先形态 B（inline buttons）**，失败降级到形态 A（纯文本 + 链接）：

**形态 B（preferred）：**
```
🎉 Hey Jamie! I found a trip plan for you.

📅 Apr 20 - Apr 27 (7 days, you're free!)
🌏 2 destinations: Tokyo, Busan

[ 🇯🇵 View Tokyo ]  [ 🇰🇷 View Busan ]
[ 👀 View All Details ]
```

**形态 A（fallback）：**
```
🎉 Hey Jamie! I found a trip plan for you.

📅 Apr 20 - Apr 27 (7 days, you're free!)
🌏 Tokyo or Busan

👉 View details: https://nomie.app/proposals/abc123
```

---

## 9. Google Calendar 集成

### OAuth 流程
1. Onboarding 时 bot 发送一个 auth link：`https://{your-domain}/oauth/google?tg_user={id}`
2. 用户点击 → 跳到 Google OAuth 授权页
3. 授权后回调到后端 `/oauth/google/callback?code={code}&state={tg_user}`
4. 后端用 code 换 access_token + refresh_token，存入 `user_preferences.google_tokens`
5. 后端发消息给对应 tg_user："Calendar connected! 🎉"

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
- **Telegram**：Jamie 的个人账号
- **Google Calendar**：Jamie 的个人日历，提前填一些真实日程 + 故意留一个 7 天空档
- **preferences**：提前填好（如：新加坡出发、想去日本/韩国、预算 5000 SGD、喜欢看海）

### Demo 流程
1. 展示当前 calendar（有明显的空档）
2. 触发扫描（/admin/scan 或手动按钮）
3. 等待 agent 工作（30 秒~1 分钟）
4. Telegram 弹出通知
5. 点击通知里的链接，跳到 web 前端
6. Web 前端展示 proposal bundle（多目的地选项）
7. 选一个，点 Confirm
8. 跳回 Telegram 显示"已加入日历"
9. 切回 Google Calendar 展示新增的 event

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

## Appendix: 现有代码资产（从 IT5007 项目继承）

- `backend/src/agents/lead_agent/` — Lead Agent（已定制为 Nomie 旅行规划身份）
- `backend/src/subagents/builtins/` — 4 个 travel sub-agents（flight-search / hotel-search / itinerary-planner / travel-tips）
- `backend/config.yaml` — 已配置为 Agnes Claw Model
- `backend/src/tools/` — tools 框架，可以扩展加 Duffel、LiteAPI、Open-Meteo 等新 tool

**新增代码位置建议：**
- `backend/src/bot/` — Telegram bot 逻辑
- `backend/src/scheduler/` — 定时扫描
- `backend/src/calendar/` — Google Calendar OAuth + API
- `backend/src/db/` — SQLite 数据访问层
- `backend/src/tools/builtins/duffel_tool.py` — Duffel 封装为 LangChain tool
- `backend/src/tools/builtins/liteapi_tool.py` — LiteAPI 封装
